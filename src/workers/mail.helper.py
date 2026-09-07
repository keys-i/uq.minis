"""Microsoft 365 sign-in and the small Graph surface the worker needs"""

from __future__ import annotations

import base64
import json
import re
from contextlib import contextmanager
from urllib.parse import quote, urlsplit

import httpx

from uq_minis.helper.common import MiniError

SCOPES = ["Mail.ReadWrite", "Mail.Send"]
GRAPH = "https://graph.microsoft.com/v1.0"
REQUEST_SENDER = "pfeventapplication@uq.edu.au"
CLUBS_SENDER = "clubs@uqu.com.au"
RETURN_TO = "pfeventa@uq.edu.au"
BODY = """Please attach your risk assessment to this email and click send.

Do not change the subject line of this email as the Reference ID is linked to your event application.

Thank You.

Cheers,
Radhesh"""


@contextmanager
def connect(db):
    """Open the selected mail backend for one poll"""
    row = db.execute("SELECT value FROM settings WHERE name = 'account'").fetchone()
    config = json.loads(row[0]) if row else {}
    if config.get("backend") == "browser":
        from .outlook import Outlook

        with Outlook(db, config["mailbox"], username=config.get("username")) as mailbox:
            yield mailbox
    else:
        graph = Graph(token(db))
        try:
            yield graph
        finally:
            graph.client.close()


class GraphError(MiniError):
    """Keep HTTP status without exposing request headers or email bodies"""

    def __init__(self, status: int, retry_after: int = 60):
        """Retain a retry delay without keeping the HTTP response"""
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"Microsoft Graph returned HTTP {status}")


def token(db, *, interactive: bool = False) -> str:
    """Refresh the registered account's token and persist rotated credentials"""
    try:
        import msal
        import requests
    except ImportError as exc:
        raise MiniError("Install mail support with: uv sync --locked --extra agent") from exc

    row = db.execute("SELECT value FROM settings WHERE name = 'account'").fetchone()
    if row is None:
        raise MiniError("Run agent login with your client ID, tenant ID and mailbox first")
    config = json.loads(row[0])
    cache = msal.SerializableTokenCache()
    saved = db.execute("SELECT value FROM settings WHERE name = 'tokens'").fetchone()
    if saved:
        cache.deserialize(saved[0])
    try:
        app = msal.PublicClientApplication(
            config["client_id"],
            authority=f"https://login.microsoftonline.com/{config['tenant_id']}",
            token_cache=cache,
            timeout=30,
        )
        accounts = app.get_accounts(username=config["mailbox"])
        result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
        if not result and interactive:
            flow = app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise MiniError("Microsoft could not start sign-in; check the app registration")
            print(flow["message"], flush=True)
            result = app.acquire_token_by_device_flow(flow)
        if not result or "access_token" not in result:
            raise MiniError("Microsoft sign-in is required; run agent login again")
        if not app.get_accounts(username=config["mailbox"]):
            raise MiniError(
                "Signed into a different mailbox; repeat login with the registered account"
            )
        return result["access_token"]
    except requests.RequestException as exc:
        raise MiniError("Microsoft sign-in request failed; check the connection and retry") from exc
    finally:
        if cache.has_state_changed:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('tokens', ?)", (cache.serialize(),))


class Graph:
    """Use immutable message IDs and never retry a mail mutation automatically"""

    def __init__(self, access_token: str):
        """Create a bounded HTTP session for Microsoft Graph"""
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": 'IdType="ImmutableId", outlook.body-content-type="text"',
            },
            timeout=30,
            follow_redirects=False,
            trust_env=False,
        )

    def request(self, method: str, path: str, **kwargs):
        """Restrict bearer credentials to the Graph API, including pagination URLs"""
        url = path if path.startswith("https://") else GRAPH + path
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "graph.microsoft.com"
            or not parsed.path.startswith("/v1.0/me/")
        ):
            raise MiniError("Refusing a Graph URL outside the registered mailbox API")
        try:
            response = self.client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise MiniError(
                "Microsoft Graph connection failed; the worker will check again"
            ) from exc
        if not response.is_success:
            delay = response.headers.get("Retry-After", "60")
            raise GraphError(response.status_code, max(30, int(delay)) if delay.isdigit() else 60)
        return response.json() if response.content else {}

    def pages(self, path: str, **params):
        """Read every result page without interpreting server pagination tokens"""
        while path:
            page = self.request("GET", path, params=params or None)
            yield from page["value"]
            path, params = page.get("@odata.nextLink"), {}

    def messages(self, since: str):
        """Read metadata only for the two expected correspondents"""
        return list(
            self.pages(
                "/me/messages",
                **{
                    "$filter": (
                        f"receivedDateTime ge {since} and isDraft eq false and "
                        f"(from/emailAddress/address eq '{REQUEST_SENDER}' or "
                        f"from/emailAddress/address eq '{CLUBS_SENDER}')"
                    ),
                    "$select": "id,from,subject,conversationId,receivedDateTime",
                    "$top": "100",
                },
            )
        )

    def message(self, message_id: str):
        """Fetch a draft, sent message or reply by its saved immutable ID"""
        return self.request(
            "GET",
            f"/me/messages/{quote(message_id, safe='')}",
            params={
                "$select": "id,isDraft,sentDateTime,subject,toRecipients,ccRecipients,"
                "bccRecipients,uniqueBody,body,webLink,conversationId,from,receivedDateTime"
            },
        )

    def create_reply(self, request_id: str) -> str:
        """Create an unsent reply before storing its ID locally"""
        return self.request("POST", f"/me/messages/{quote(request_id, safe='')}/createReply")["id"]

    def prepare(self, draft_id: str, event_id: str, filename: str, document: bytes) -> None:
        """Set the exact return message and attach the registered form once"""
        path = f"/me/messages/{quote(draft_id, safe='')}"
        self.request(
            "PATCH",
            path,
            json={
                "subject": f"UQU Risk Assessment Return Ref ID: {event_id}",
                "body": {"contentType": "Text", "content": BODY},
                "toRecipients": [{"emailAddress": {"address": RETURN_TO}}],
                "ccRecipients": [],
                "bccRecipients": [],
            },
        )
        attachments = list(self.pages(path + "/attachments"))
        encoded = base64.b64encode(document).decode("ascii")
        if attachments:
            if len(attachments) != 1 or any(
                attachments[0].get(key) != value
                for key, value in {"name": filename, "contentBytes": encoded}.items()
            ):
                raise MiniError("The saved draft has unexpected attachments; inspect it in Outlook")
            return
        self.request(
            "POST",
            path + "/attachments",
            json={
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentType": (
                    "application/pdf"
                    if filename.casefold().endswith(".pdf")
                    else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                "contentBytes": encoded,
            },
        )

    def send(self, draft_id: str) -> None:
        """Submit an already prepared draft exactly once per recorded attempt"""
        self.request("POST", f"/me/messages/{quote(draft_id, safe='')}/send")


def validate_account(client_id: str, tenant_id: str, mailbox: str) -> dict[str, str]:
    """Validate local authentication inputs before constructing an authority URL"""
    from uuid import UUID

    try:
        client_id, tenant_id = str(UUID(client_id)), str(UUID(tenant_id))
    except ValueError as exc:
        raise MiniError("Client ID and tenant ID must be UUIDs from your app registration") from exc
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", mailbox):
        raise MiniError("Use the sign-in address of your Microsoft 365 mailbox")
    return {"client_id": client_id, "tenant_id": tenant_id, "mailbox": mailbox.casefold()}
