"""Connect a private Timey workspace to YouTube through Google's OAuth flow

The browser visits Google's real consent page while this backend owns the
single-use state, PKCE verifier and refresh token
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import Protocol, cast
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from uq_minis.app import metric, telemetry
from uq_minis.core.common import MiniError, atomic_json
from uq_minis.core.paths import STATE
from uq_minis.minis.timey.youtube import SCOPE

TOKEN = STATE / "timey/youtube.json"
CALLBACK = "/api/timey/youtube/callback"
AUTH_HOST = "accounts.google.com"
PUBLIC_ORIGIN = "https://uni.keysi.dev"
STATE_LIFETIME = 300


class OAuthCredentials(Protocol):
    """The credential values retained after Google's callback"""

    refresh_token: str | None
    scopes: list[str] | None

    def to_json(self) -> str:
        """Serialise the supported Google credential"""
        ...


class OAuthFlow(Protocol):
    """The small google-auth-oauthlib surface needed by the web flow"""

    credentials: OAuthCredentials

    def authorization_url(self, **values: str) -> tuple[str, str]:
        """Build Google's consent URL and a random state value"""
        ...

    def fetch_token(self, **values: str) -> object:
        """Exchange one callback code for the workspace credential"""
        ...


class OAuthFactory(Protocol):
    """The typed constructor boundary around google-auth-oauthlib"""

    def from_client_config(
        self, client_config: dict[str, object], scopes: list[str], **values: object
    ) -> OAuthFlow:
        """Create one web flow from validated provider configuration"""
        ...


@dataclass
class Pending:
    """Bind one expiring provider callback to the flow that created it"""

    state: str
    flow: OAuthFlow
    origin: str
    expires: float


def _safe_token() -> None:
    """Reject provider state redirected through links"""
    if any(path.is_symlink() for path in (TOKEN, TOKEN.parent, TOKEN.parent.parent)):
        raise MiniError("Reconnect YouTube using this workspace's private storage")


def connected() -> bool:
    """Recognise a bounded owner-only refresh token without contacting Google"""
    _safe_token()
    if not TOKEN.exists():
        return False
    if (
        not TOKEN.is_file()
        or TOKEN.stat().st_size > 64 * 1024
        or os.name == "posix"
        and TOKEN.stat().st_mode & 0o077
    ):
        raise MiniError("Reconnect YouTube to repair its private connection")
    try:
        loaded: object = json.loads(TOKEN.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MiniError("Reconnect YouTube; its saved connection could not be read") from exc
    if not isinstance(loaded, dict):
        raise MiniError("Reconnect YouTube; its saved connection is invalid")
    values = cast(dict[str, object], loaded)
    refresh = values.get("refresh_token")
    scopes = values.get("scopes", [])
    return (
        isinstance(refresh, str) and bool(refresh) and isinstance(scopes, list) and SCOPE in scopes
    )


def disconnect() -> None:
    """Forget only this workspace's YouTube upload permission"""
    _safe_token()
    TOKEN.unlink(missing_ok=True)


def _origin(request: Request) -> str:
    """Use only the gateway's trusted origin or a validated loopback origin"""
    forwarded = request.headers.get("x-minis-origin", "")
    if forwarded:
        if forwarded != PUBLIC_ORIGIN:
            raise MiniError("The YouTube return address is not trusted")
        return forwarded
    parsed = urlsplit(str(request.base_url))
    if (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost"}
        and parsed.port is not None
        and 1024 <= parsed.port <= 65535
    ):
        return f"http://{parsed.hostname}:{parsed.port}"
    raise MiniError("Open Timey from its trusted address before connecting YouTube")


def _client(origin: str) -> dict[str, object]:
    """Read the deployment credential and require its exact callback"""
    paths: list[Path] = []
    if directory := os.environ.get("CREDENTIALS_DIRECTORY"):
        paths.append(Path(directory) / "google-oauth")
    paths.append(STATE / "timey/client_secret.json")
    path = next((item for item in paths if item.is_file() and not item.is_symlink()), None)
    if path is None:
        raise MiniError("YouTube sign-in is not configured yet")
    if path.stat().st_size > 64 * 1024:
        raise MiniError("The YouTube OAuth configuration is invalid")
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MiniError("The YouTube OAuth configuration could not be read") from exc
    if not isinstance(loaded, dict):
        raise MiniError("YouTube sign-in needs a Google Web OAuth client")
    config = cast(dict[str, object], loaded)
    if not isinstance(config.get("web"), dict):
        raise MiniError("YouTube sign-in needs a Google Web OAuth client")
    web = cast(dict[str, object], config["web"])
    callback = origin + CALLBACK
    client_id = web.get("client_id")
    client_secret = web.get("client_secret")
    redirects = web.get("redirect_uris")
    if (
        not isinstance(client_id, str)
        or not client_id.endswith(".apps.googleusercontent.com")
        or not isinstance(client_secret, str)
        or not client_secret
        or web.get("auth_uri")
        not in {
            "https://accounts.google.com/o/oauth2/auth",
            "https://accounts.google.com/o/oauth2/v2/auth",
        }
        or web.get("token_uri") != "https://oauth2.googleapis.com/token"
        or not isinstance(redirects, list)
        or callback not in redirects
    ):
        raise MiniError("The Google OAuth client does not allow this Timey return address")
    return config


def _flow(config: dict[str, object], callback: str) -> OAuthFlow:
    """Create Google's supported web flow with an automatic PKCE verifier"""
    try:
        factory = cast(OAuthFactory, getattr(import_module("google_auth_oauthlib.flow"), "Flow"))
    except ImportError as exc:
        raise MiniError("YouTube sign-in support is not installed on this backend") from exc
    return factory.from_client_config(
        config,
        scopes=[SCOPE],
        redirect_uri=callback,
        autogenerate_code_verifier=True,
    )


def _page(title: str, message: str, status: int = 200) -> HTMLResponse:
    """Give the provider window a useful script-free finishing state"""
    return HTMLResponse(
        "<!doctype html><html lang=en><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{title}</title><main><h1>{title}</h1><p>{message}</p></main>",
        status_code=status,
    )


class Connection:
    """Own one pending OAuth exchange for this isolated workspace"""

    def __init__(self, app: FastAPI) -> None:
        """Start without provider state or a network request"""
        self.app = app
        self.pending: Pending | None = None
        self.lock = asyncio.Lock()

    def record(self, name: str, event: str) -> None:
        """Count and emit a fixed lifecycle outcome without provider data"""
        metric(self.app, name)
        telemetry(self.app, event)

    async def start(self, request: Request) -> dict[str, str]:
        """Create one consent URL without exposing the client secret"""
        origin = _origin(request)
        flow = _flow(_client(origin), origin + CALLBACK)
        url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != AUTH_HOST
            or not re.fullmatch(r"[A-Za-z0-9._~-]{20,256}", state)
            or parse_qs(parsed.query).get("state") != [state]
        ):
            raise MiniError("Google returned an invalid YouTube consent link")
        async with self.lock:
            self.pending = Pending(state, flow, origin, monotonic() + STATE_LIFETIME)
        return {"url": url}

    async def callback(self, request: Request) -> HTMLResponse:
        """Consume one state value before exchanging Google's code"""
        state = request.query_params.get("state", "")
        async with self.lock:
            pending = self.pending
            valid = (
                pending is not None
                and pending.expires > monotonic()
                and bool(state)
                and secrets.compare_digest(state, pending.state)
            )
            if pending is not None and (valid or pending.expires <= monotonic()):
                self.pending = None
        if not valid or pending is None or _origin(request) != pending.origin:
            self.record("oauth_failures", "youtube_oauth_failed")
            return _page(
                "Connection expired",
                "Close this window and try Continue with Google again",
                400,
            )
        if request.query_params.get("error"):
            self.record("oauth_cancellations", "youtube_oauth_cancelled")
            return _page(
                "Connection cancelled",
                "No YouTube permission was saved. You can close this window",
                400,
            )
        response = pending.origin + request.url.path
        if request.url.query:
            response += "?" + request.url.query
        google_error = cast(
            type[Exception], getattr(import_module("google.auth.exceptions"), "GoogleAuthError")
        )
        oauth_error = cast(
            type[Exception], getattr(import_module("oauthlib.oauth2"), "OAuth2Error")
        )
        try:
            await run_in_threadpool(pending.flow.fetch_token, authorization_response=response)
            credential = pending.flow.credentials
            loaded: object = json.loads(credential.to_json())
            if not isinstance(loaded, dict):
                raise MiniError("Google returned an invalid YouTube credential")
            values = cast(dict[str, object], loaded)
            scopes = credential.scopes
            if scopes is None:
                saved_scopes = values.get("scopes")
                listed = cast(list[object], saved_scopes) if isinstance(saved_scopes, list) else []
                scopes = (
                    cast(list[str], listed)
                    if all(isinstance(value, str) for value in listed)
                    else []
                )
            if not credential.refresh_token or SCOPE not in scopes:
                raise MiniError("Google did not return the YouTube upload permission")
            _safe_token()
            TOKEN.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            atomic_json(TOKEN, values, private=True)
        except MiniError:
            raise
        except (OSError, ValueError) as exc:
            raise MiniError("Google could not finish the YouTube connection") from exc
        except Exception as exc:
            if not isinstance(exc, (google_error, oauth_error)):
                raise
            raise MiniError("Google could not finish the YouTube connection") from exc
        self.record("oauth_completions", "youtube_oauth_completed")
        return _page(
            "YouTube connected",
            "Return to Timey. This window will close there",
        )

    async def cancel(self) -> None:
        """Invalidate any callback before forgetting the saved permission"""
        async with self.lock:
            self.pending = None
        disconnect()


def install(app: FastAPI) -> None:
    """Register the workspace-owned consent, callback and disconnect endpoints"""
    connection = Connection(app)
    app.state.youtube = connection

    @app.get("/api/timey/youtube")
    async def status(request: Request) -> dict[str, bool]:
        """Report permission state without exposing provider tokens"""
        try:
            _client(_origin(request))
            configured = True
        except MiniError:
            configured = False
        return {"connected": connected(), "configured": configured}

    @app.post("/api/timey/youtube/start")
    async def start(request: Request) -> dict[str, str]:
        """Prepare the provider URL after a same-origin user action"""
        try:
            result = await connection.start(request)
        except Exception:
            connection.record("oauth_failures", "youtube_oauth_failed")
            raise
        connection.record("oauth_starts", "youtube_oauth_started")
        return result

    @app.get("/api/timey/youtube/callback", response_class=HTMLResponse)
    async def callback(request: Request) -> HTMLResponse:
        """Accept only Google's single-use state-bearing return"""
        try:
            return await connection.callback(request)
        except Exception:
            connection.record("oauth_failures", "youtube_oauth_failed")
            raise

    @app.post("/api/timey/youtube")
    async def change(request: Request) -> dict[str, bool]:
        """Disconnect only when the existing JSON action names that effect"""
        try:
            body = await request.json()
        except (ValueError, RecursionError) as exc:
            raise MiniError("The YouTube connection action could not be read") from exc
        if body != {"kind": "disconnect"}:
            raise HTTPException(422, "Choose the supported YouTube connection action")
        await connection.cancel()
        return {"connected": False, "configured": True}
