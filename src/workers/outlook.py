"""Outlook web automation through a private browser profile and the visible UI"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from uq_minis.helper.common import MiniError

from . import helper

mail = helper("mail")
HOME = "https://outlook.office.com/mail/"
_MESSAGE_IDS = re.compile(r"<[^<>\s]+>")


class _Text(HTMLParser):
    def __init__(self, reply_only: bool):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0
        self.quoted = False
        self.reply_only = reply_only

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.reply_only and (
            tag == "blockquote"
            or attrs.get("id", "").casefold() == "divrplyfwd"
            or "gmail_quote" in attrs.get("class", "")
        ):
            self.quoted = True
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and not self.quoted:
            self.parts.append(data)


def _text(part, *, reply_only: bool = True) -> str:
    content = part.get_content() if part else ""
    if part and part.get_content_type() == "text/html":
        parser = _Text(reply_only)
        parser.feed(content)
        content = "".join(parser.parts)
    # ponytail: unfamiliar quote formats require review; support ordinary Outlook/Gmail replies.
    lines = []
    for line in content.splitlines():
        if reply_only and re.match(r"\s*(?:From:|On .+wrote:|[-_]{5,}|>).*", line, re.I):
            break
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def parse_message(raw: bytes, url: str) -> dict:
    """Read identifiers, recipients and content from Outlook's downloaded EML"""
    message = BytesParser(policy=policy.default).parsebytes(raw)
    identity = str(message.get("Message-ID", "")).strip()
    if not _MESSAGE_IDS.fullmatch(identity):
        raise MiniError("Outlook exported a message without a valid Message-ID")
    dates = [str(value).rsplit(";", 1)[-1].strip() for value in message.get_all("Received", [])]
    dates.append(str(message.get("Date", "")))
    timestamp = None
    for value in dates:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is not None:
                timestamp = parsed.astimezone(UTC).isoformat()
                break
        except (TypeError, ValueError, OverflowError):
            continue
    if timestamp is None:
        raise MiniError("Outlook exported a message without a usable timestamp")
    try:
        sent = parsedate_to_datetime(str(message.get("Date", "")))
        if sent.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise MiniError("Outlook exported a message without a usable sent date") from exc

    def addresses(header):
        return [
            {"emailAddress": {"address": address.casefold()}}
            for _, address in getaddresses([str(value) for value in message.get_all(header, [])])
        ]

    senders = addresses("From")
    if len(senders) != 1 or not senders[0]["emailAddress"]["address"]:
        raise MiniError("Outlook exported a message without one sender")
    references = _MESSAGE_IDS.findall(
        " ".join(str(message.get(name, "")) for name in ("References", "In-Reply-To"))
    )
    attachments = []
    for part in message.iter_attachments():
        data = part.get_payload(decode=True)
        if data is None:
            raise MiniError("Outlook exported an unreadable attachment")
        attachments.append(
            {"name": part.get_filename(), "sha256": hashlib.sha256(data).hexdigest()}
        )
    return {
        "id": identity,
        "from": senders[0],
        "subject": str(message.get("Subject", "")),
        "receivedDateTime": timestamp,
        "sentDateTime": sent.astimezone(UTC).isoformat(),
        "conversationId": identity,
        "references": references,
        "toRecipients": addresses("To"),
        "ccRecipients": addresses("Cc"),
        "bccRecipients": addresses("Bcc"),
        "uniqueBody": {
            "contentType": "text",
            "content": _text(message.get_body(preferencelist=("plain", "html"))),
        },
        "body": {
            "contentType": "text",
            "content": _text(message.get_body(preferencelist=("plain", "html")), reply_only=False),
        },
        "attachments": attachments,
        "webLink": url,
    }


def _url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "outlook.office.com"
        or not parsed.path.startswith("/mail/")
    ):
        raise MiniError("Outlook did not provide a mailbox link; sign in again")
    return value


def _same_return(
    message: dict, event_id: str, filename: str, document: bytes, mailbox: str
) -> bool:
    return (
        message["subject"] == f"UQU Risk Assessment Return Ref ID: {event_id}"
        and message["from"]["emailAddress"]["address"] == mailbox
        and message["toRecipients"] == [{"emailAddress": {"address": mail.RETURN_TO}}]
        and not message["ccRecipients"]
        and not message["bccRecipients"]
        and message["body"]["content"].strip() == mail.BODY
        and message["attachments"]
        == [{"name": filename, "sha256": hashlib.sha256(document).hexdigest()}]
    )


class Outlook:
    """Use Outlook's search, EML export and compose controls without calling private APIs"""

    def __init__(self, db, mailbox: str, *, username: str | None = None, interactive: bool = False):
        """Bind one private browser profile to one worker database"""
        self.db, self.mailbox, self.interactive = db, mailbox, interactive
        self.username = username or mailbox
        self.context = self.runtime = None
        self.stage = "starting the browser"
        self.prepared = None
        self.state_dir = Path(db.execute("PRAGMA database_list").fetchone()[2]).parent
        db.executescript("""
            CREATE TABLE IF NOT EXISTS browser_mail (id TEXT PRIMARY KEY, data TEXT NOT NULL);
        """)

    def __enter__(self):
        """Open a dedicated profile, allowing interactive sign-in only during login"""
        try:
            from playwright.sync_api import Error, sync_playwright
        except ImportError as exc:
            raise MiniError("Install browser support: uv sync --locked --extra agent") from exc
        self.browser_error = Error
        profile = self.state_dir / "browser"
        if profile.is_symlink():
            raise MiniError("The Outlook browser profile must not be a symlink")
        profile.mkdir(mode=0o700, exist_ok=True)
        profile.chmod(0o700)
        try:
            self.runtime = sync_playwright().start()
            self.context = self.runtime.chromium.launch_persistent_context(
                str(profile),
                headless=not self.interactive,
                accept_downloads=True,
                locale="en-AU",
                timezone_id="Australia/Brisbane",
            )
            self.context.set_default_timeout(15000)
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
            self.stage = "checking your Outlook sign-in"
            if self.interactive:
                print(
                    "Sign into Outlook in the browser, complete MFA, and wait for your inbox. Use English display language and individual messages (Mail settings → Layout).",
                    flush=True,
                )
            self._search_box().wait_for(
                state="visible", timeout=300000 if self.interactive else 30000
            )
            _url(self.page.url)
            self.page.get_by_role(
                "button", name=re.compile(r"Account manager|Your account", re.I)
            ).click()
            self.page.get_by_text(re.compile(rf"^{re.escape(self.username)}$", re.I)).wait_for(
                state="visible"
            )
            self.page.keyboard.press("Escape")
            return self
        except BaseException as exc:
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise

    def __exit__(self, kind, error, traceback):
        """Close the browser and report UI failures without leaking page content"""
        try:
            if self.context:
                self.context.close()
        finally:
            if self.runtime:
                self.runtime.stop()
        if isinstance(error, self.browser_error):
            raise MiniError(
                f"Outlook web failed while {self.stage}. Run agent login again if signed out; "
                "check the English Outlook layout. Install Chromium with: "
                "uv run --extra agent playwright install chromium"
            ) from None

    def _search_box(self):
        return (
            self.page.get_by_role("searchbox", name="Search", exact=True)
            .or_(self.page.get_by_role("textbox", name="Search", exact=True))
            .or_(self.page.get_by_role("combobox", name="Search", exact=True))
        ).filter(visible=True)

    def _search(self, query: str, folder: str | None = None) -> None:
        self.stage = "searching mail"
        self.page.goto(HOME, wait_until="domcontentloaded")
        _url(self.page.url)
        if folder:
            self.page.get_by_role(
                "treeitem", name=re.compile(rf"^{re.escape(folder)}(?:\s|$)")
            ).first.click()
        search = self._search_box()
        search.fill(query)
        search.press("Enter")
        scope = "Current folder" if folder else "All folders"
        selected = self.page.get_by_role("button", name=scope, exact=True)
        if not selected.is_visible():
            self.page.get_by_role(
                "button", name="All folders" if folder else "Current folder", exact=True
            ).click()
            self.page.get_by_role("menuitem", name=scope, exact=True).click()
        selected.wait_for(state="visible")

    def _read(self) -> dict:
        self.stage = "exporting the selected message"
        # A conversation with multiple displayed messages is ambiguous; do not choose one by position.
        bodies = self.page.get_by_role("document", name=re.compile("Message body", re.I))
        bodies.first.wait_for(state="visible")
        if bodies.count() != 1:
            raise MiniError("Set Outlook Mail → Layout → Show email as individual messages")
        url = _url(self.page.url)
        if not re.search(r"/id/[^/?#]+", urlsplit(url).path):
            raise MiniError("Outlook did not expose a link to the selected message")
        self.page.get_by_role("button", name="More actions", exact=True).click()
        with self.page.expect_download() as pending:
            self.page.get_by_role(
                "menuitem", name=re.compile(r"^(Save as|Download)$", re.I)
            ).click()
        download = pending.value
        try:
            path = download.path()
            if path.stat().st_size > 10_000_000:
                raise MiniError("The Outlook message export exceeds 10 MB")
            message = parse_message(path.read_bytes(), url)
        finally:
            download.delete()
        return message

    def _collect(self, query: str, folder: str | None = None) -> list[dict]:
        self._search(query, folder)
        listing = self.page.get_by_role(
            "listbox", name=re.compile("Message list|Search results", re.I)
        )
        empty = self.page.get_by_text(
            re.compile(r"^(No results|We didn't find anything)(?:\.|$)", re.I)
        )
        listing.or_(empty).first.wait_for(state="visible")
        if empty.is_visible():
            return []
        seen, messages = set(), {}
        # ponytail: bounded UI scan; narrow --since if a sender has more than 50 screens of results.
        for _ in range(50):
            rows = listing.get_by_role("option")
            keys = [
                rows.nth(i).get_attribute("aria-label") or rows.nth(i).inner_text()
                for i in range(rows.count())
            ]
            if len(set(keys)) != len(keys):
                raise MiniError(
                    "Outlook search has indistinguishable rows; narrow the watch's --since date"
                )
            for index, key in enumerate(keys):
                if key not in seen:
                    previous = self.page.url
                    selected = rows.nth(index).get_attribute("aria-selected") == "true"
                    rows.nth(index).click()
                    if not selected:
                        self.page.wait_for_url(lambda url: url != previous)
                    item = self._read()
                    messages[item["id"]] = item
                    seen.add(key)
            moved = listing.evaluate("""element => {
                let scroller = element;
                while (scroller && scroller.scrollHeight <= scroller.clientHeight) scroller = scroller.parentElement;
                if (!scroller) return false;
                const before = scroller.scrollTop;
                scroller.scrollTop += Math.max(1, scroller.clientHeight * 0.75);
                return scroller.scrollTop !== before;
            }""")
            if not moved:
                return list(messages.values())
            self.page.wait_for_timeout(500)
        raise MiniError("Outlook search exceeded 50 screens; narrow the watch's --since date")

    def messages(self, since: str) -> list[dict]:
        """Read only the two event correspondents and retain RFC thread references"""
        found = []
        for sender in (mail.REQUEST_SENDER, mail.CLUBS_SENDER):
            for message in self._collect(f"from:{sender} received:>={since[:10]}"):
                if message["from"]["emailAddress"]["address"] == sender and datetime.fromisoformat(
                    message["receivedDateTime"]
                ) >= datetime.fromisoformat(since):
                    self.db.execute(
                        "INSERT OR REPLACE INTO browser_mail VALUES (?, ?)",
                        (message["id"], json.dumps(message)),
                    )
                    found.append(message)
        return found

    def create_reply(self, request_id: str) -> str:
        """Reserve a local draft identity before touching Outlook"""
        if not self.db.execute("SELECT 1 FROM browser_mail WHERE id = ?", (request_id,)).fetchone():
            raise MiniError("The risk request is missing from saved browser mail")
        return f"browser:{uuid4()}"

    def _event(self, identity: str):
        row = self.db.execute("SELECT * FROM events WHERE draft_id = ?", (identity,)).fetchone()
        if row is None:
            raise MiniError("Unknown browser draft")
        return row

    def _returns(self, event) -> list[dict]:
        matches = []
        query = f'subject:"UQU Risk Assessment Return Ref ID: {event["event_id"]}"'
        for message in self._collect(query, "Sent Items"):
            if message["subject"] != f"UQU Risk Assessment Return Ref ID: {event['event_id']}":
                continue
            if event["request_id"] not in message["references"] or datetime.fromisoformat(
                message["sentDateTime"]
            ) < datetime.fromisoformat(event["request_time"]):
                continue
            if not _same_return(
                message, event["event_id"], event["filename"], event["document"], self.mailbox
            ):
                raise MiniError(
                    "An Outlook return has different recipients, body or attachment; inspect it"
                )
            matches.append(message)
        if len(matches) > 1:
            raise MiniError(
                "Multiple matching Outlook returns exist; inspect Drafts and Sent Items"
            )
        return matches

    def message(self, identity: str) -> dict:
        """Reconcile sent mail by full content; never infer success from a missing draft"""
        if not identity.startswith("browser:"):
            row = self.db.execute(
                "SELECT data FROM browser_mail WHERE id = ?", (identity,)
            ).fetchone()
            if not row:
                raise MiniError("The requested message is missing from saved browser mail")
            return json.loads(row[0])
        event = self._event(identity)
        sent = self._returns(event)
        if sent:
            return {**sent[0], "isDraft": False}
        return {"id": identity, "isDraft": True}

    def prepare(self, identity: str, event_id: str, filename: str, document: bytes) -> None:
        """Prepare one reply in this browser; interrupted drafts are never sent later"""
        event = self._event(identity)
        request = self.message(event["request_id"])
        self.page.goto(_url(request["webLink"]), wait_until="domcontentloaded")
        self.stage = "preparing the risk-assessment reply"
        self.page.get_by_role("button", name="Reply", exact=True).click()
        subject = self.page.get_by_role(
            "textbox", name=re.compile(r"^(Add a subject|Subject)$", re.I)
        )
        if not subject.is_visible():
            self.page.get_by_role(
                "button", name=re.compile(r"^(Reply options|More reply options)$", re.I)
            ).click()
            self.page.get_by_role("menuitem", name="Edit subject", exact=True).click()
        subject.fill(f"UQU Risk Assessment Return Ref ID: {event_id}")
        # Require editable recipient fields, including empty Cc/Bcc, before changing the message.
        for name in ("To", "Cc", "Bcc"):
            field = self.page.get_by_role("textbox", name=name, exact=True)
            if not field.is_visible():
                self.page.get_by_role("button", name=name, exact=True).click()
            field.press("ControlOrMeta+a")
            field.press("Backspace")
            if name == "To":
                field.fill(mail.RETURN_TO)
                field.press("Enter")
        self.page.get_by_role("textbox", name=re.compile(r"^Message body", re.I)).fill(mail.BODY)
        self.page.get_by_role("button", name=re.compile(r"^(Attach file|Attach)$", re.I)).click()
        with self.page.expect_file_chooser() as chooser:
            self.page.get_by_role(
                "menuitem", name=re.compile(r"^(Browse this computer|Browse this device)$", re.I)
            ).click()
        chooser.value.set_files(
            {
                "name": filename,
                "mimeType": "application/pdf"
                if filename.endswith(".pdf")
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "buffer": document,
            }
        )
        self.page.get_by_role(
            "button", name=re.compile(rf"^Remove {re.escape(filename)}(?:$| attachment)", re.I)
        ).wait_for(state="visible", timeout=60000)
        self.prepared = identity
        self._verify_compose(event)

    def _verify_compose(self, event) -> None:
        """Require the exact visible fields and one finished attachment before Send"""
        subject = self.page.get_by_role(
            "textbox", name=re.compile(r"^(Add a subject|Subject)$", re.I)
        )
        body = self.page.get_by_role("textbox", name=re.compile(r"^Message body", re.I))
        if (
            subject.input_value() != f"UQU Risk Assessment Return Ref ID: {event['event_id']}"
            or body.inner_text().strip() != mail.BODY
        ):
            raise MiniError("The composed subject or body differs from the registered return")
        for name, expected in (("To", [mail.RETURN_TO]), ("Cc", []), ("Bcc", [])):
            field = self.page.get_by_role("textbox", name=name, exact=True)
            # Recipient pickers put resolved chips beside their input. Refuse layouts without that boundary.
            picker = field.locator(
                "xpath=ancestor::*[@role='list' or contains(@class, 'ms-BasePicker-text')][1]"
            )
            if picker.count() != 1:
                raise MiniError(
                    "Outlook's recipient picker layout is unsupported; no send was attempted"
                )
            chips = picker.locator(".ms-PickerItem-root")
            addresses = []
            for chip in chips.all():
                address = chip.get_attribute("data-email")
                if not address:
                    address = chip.locator("[data-email]").get_attribute("data-email")
                addresses.append(address.casefold() if address else "")
            if (
                addresses != expected
                or field.input_value().strip()
                or (not expected and picker.inner_text().strip())
            ):
                raise MiniError("Outlook's resolved recipients differ from the required return")
        attachments = self.page.get_by_role(
            "button", name=re.compile(r"^Remove .+ attachment$", re.I)
        )
        if (
            attachments.count() != 1
            or attachments.first.get_attribute("aria-label")
            != f"Remove {event['filename']} attachment"
        ):
            raise MiniError("Outlook's attachments differ from the registered form")
        if self.page.get_by_role("progressbar").count():
            raise MiniError("The risk attachment is still uploading; no send was attempted")

    def send(self, identity: str) -> None:
        """Click Send once for the reply prepared in this process after durable intent"""
        event = self._event(identity)
        if event["state"] != "sending" or not event["send_started"]:
            raise MiniError("Browser send requires a saved send intent")
        if self.prepared != identity:
            raise MiniError("This browser has no verified prepared reply; check Sent Items")
        self.stage = "sending the verified draft"
        self._verify_compose(event)
        self.prepared = None
        self.page.get_by_role("button", name="Send", exact=True).click(no_wait_after=True)
        self.page.get_by_text("Message sent", exact=True).wait_for(state="visible", timeout=60000)
        self.page.get_by_role("button", name="Undo", exact=True).wait_for(
            state="hidden", timeout=60000
        )
