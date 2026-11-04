"""Keep private browser workspaces separate from verified UQ access

A persistent random guest cookie owns ordinary minis without university login
Only its digest is public, and UQ sign-in does not replace an existing guest
workspace or turn a guest worker's delegate into verified university access

A short-lived, single-use reservation connects the in-site sign-in window to
its HttpOnly cookie. The WebSocket must pass same-origin checks before the
backend opens a private browser; only a verified portal response activates
the opaque eight-hour session

Sessions are process-local and separate from saved Forms or Outlook access
The shared request budget also bounds university traffic across browser minis
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
from collections import deque
from dataclasses import dataclass, field
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Any, cast

from anyio import CancelScope
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketState

from uq_minis.core.common import MiniError

router = APIRouter()
COOKIE = "minis_session"
HOST_COOKIE = "__Host-minis_session"
GUEST_COOKIE = "__Host-minis_workspace"
VERIFY = BoundedSemaphore(1)
PROTECTED = {"/api/minis/event", "/api/minis/auth", "/api/minis/agent", "/api/rooms"}
OUTBOUND = PROTECTED | {
    "/api/timey/search",
    "/api/timey/clip",
    "/api/timey/source",
    "/api/timey/youtube/start",
    "/api/timey/youtube/callback",
    "/api/course",
    "/api/profile",
    "/api/catalogues",
    "/api/sync",
    "/api/discord",
    "/api/social",
    "/api/research/refresh",
    "/api/research/catalogue",
    "/api/research/feedback",
    "/api/clubs/feed",
    "/api/minis/timey",
    "/api/research/course",
    "/api/research/trail",
    "/api/session/login",
    "/api/minis/scrappy",
    "/api/minis/clubby",
    "/api/club",
    "/api/search",
}


@dataclass
class Identity:
    """Keep opaque sessions on this server after a successful portal access check"""

    origin: str = ""
    delegate: tuple[str, str] | None = None
    sessions: dict[str, tuple[float, str]] = field(default_factory=dict)
    attempts: dict[str, float] = field(default_factory=dict)
    calls: deque[float] = field(default_factory=deque)
    busy: int = 0
    lock: Lock = field(default_factory=Lock)

    @property
    def cookie(self) -> str:
        """Prevent sibling domains from setting the hosted session cookie"""
        return HOST_COOKIE if self.origin else COOKIE

    def prune(self) -> None:
        """Expire sessions before reading or allocating records"""
        now = monotonic()
        for key in list(self.sessions):
            if self.sessions[key][0] <= now:
                del self.sessions[key]
        for key in list(self.attempts):
            if self.attempts[key] <= now:
                del self.attempts[key]

    def user(self, request: Request) -> str:
        """Return only an identity verified through the protected UQ portal"""
        key = request.cookies.get(self.cookie, "")
        if self.delegate is not None:
            account, secret = self.delegate
            return (
                account
                if not account.startswith("guest:") and secrets.compare_digest(key, secret)
                else ""
            )
        with self.lock:
            self.prune()
            return self.sessions.get(key, (0, ""))[1]

    def owner(self, request: Request) -> str:
        """Resolve private workspace access separately from verified university access"""
        if self.delegate is not None:
            account, secret = self.delegate
            return (
                account
                if secrets.compare_digest(request.cookies.get(self.cookie, ""), secret)
                else ""
            )
        token = request.cookies.get(GUEST_COOKIE, "") if self.origin else ""
        if re.fullmatch(r"[a-f0-9]{64}", token):
            return "guest:" + hashlib.sha256(token.encode()).hexdigest()
        return self.user(request)

    def enter(self) -> bool:
        """Bound shared upstream traffic and reject excess work without queuing it"""
        with self.lock:
            now = monotonic()
            while self.calls and self.calls[0] <= now - 60:
                self.calls.popleft()
            if self.busy >= 2 or len(self.calls) >= 30:
                return False
            self.calls.append(now)
            self.busy += 1
            return True


def identity(request: Request) -> Identity:
    """Read this backend's identity boundary"""
    return cast(Identity, request.app.state.identity)


@router.get("/api/session")
def status(request: Request) -> JSONResponse:
    """Prepare an isolated guest workspace without requiring university sign-in"""
    auth = identity(request)
    owner = auth.owner(request)
    token = ""
    if auth.origin and not owner:
        token = secrets.token_hex(32)
        owner = "guest:" + hashlib.sha256(token.encode()).hexdigest()
    response = JSONResponse({
        "configured": True,
        "user": auth.user(request),
        "hosted": bool(auth.origin),
        "workspace": owner,
    })
    if token:
        response.set_cookie(
            GUEST_COOKIE,
            token,
            max_age=365 * 86400,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
    return response


@router.post("/api/session/login")
async def login(request: Request) -> JSONResponse:
    """Reserve a single-use local sign-in window without accepting a claimed identity"""
    auth = identity(request)
    if name := auth.user(request):
        return JSONResponse({"user": name})
    key = secrets.token_urlsafe(32)
    with auth.lock:
        auth.prune()
        if len(auth.sessions) + len(auth.attempts) >= 128:
            raise MiniError("Too many active sessions; try again later")
        auth.attempts.pop(request.cookies.get(auth.cookie, ""), None)
        auth.attempts[key] = monotonic() + 60
    response = JSONResponse({"user": "", "window": "/api/session/window"})
    response.set_cookie(
        auth.cookie,
        key,
        max_age=8 * 3600,
        httponly=True,
        secure=bool(auth.origin),
        samesite="lax",
        path="/" if auth.origin else "/api",
    )
    return response


@router.websocket("/api/session/window")
async def window(socket: WebSocket) -> None:
    """Keep pixels and human input local while the backend verifies UQ's session"""
    port = socket.app.state.workspace.port
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{host}" for host in hosts} | {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    }
    auth = cast(Identity, socket.app.state.identity)
    if auth.origin:
        from urllib.parse import urlsplit

        hosts = {urlsplit(auth.origin).netloc}
        origins = {auth.origin}
    if socket.headers.get("host") not in hosts or socket.headers.get("origin") not in origins:
        await socket.close(code=1008)
        return
    auth = cast(Identity, socket.app.state.identity)
    key = socket.cookies.get(auth.cookie, "")
    with auth.lock:
        auth.prune()
        reserved = auth.attempts.pop(key, 0) > monotonic()
    if not reserved:
        await socket.close(code=1008)
        return
    await socket.accept()
    if not VERIFY.acquire(blocking=False):
        await socket.send_json({"error": "A UQ sign-in is already open; finish or cancel it first"})
        await socket.close(code=1008)
        return
    actions: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)

    async def verify() -> None:
        from uq_minis.minis.auth import portal

        deadline = monotonic() + 300
        async with portal.window() as browser:
            next_frame = 0.0
            previous: dict[str, Any] = {}
            while monotonic() < deadline:
                if name := await browser.user():
                    with auth.lock:
                        auth.prune()
                        auth.sessions[key] = (monotonic() + 8 * 3600, name)
                    await socket.send_json({"user": name})
                    return
                if monotonic() >= next_frame:
                    frame = await browser.view()
                    if frame != previous:
                        await socket.send_json(frame)
                        previous = frame
                    next_frame = monotonic() + 1
                try:
                    event = await asyncio.wait_for(
                        actions.get(), max(0.01, next_frame - monotonic())
                    )
                except TimeoutError:
                    continue
                await browser.act(event)
                if event.get("kind") in {"submit", "click", "enter", "select"}:
                    next_frame, previous = 0.0, {}
        raise MiniError("UQ sign-in timed out; try signing in again")

    worker = asyncio.create_task(verify())
    receiver = asyncio.create_task(socket.receive_text())
    try:
        while True:
            done, _ = await asyncio.wait({worker, receiver}, return_when=asyncio.FIRST_COMPLETED)
            if worker in done:
                await worker
                break
            message = receiver.result()
            if len(message) > 8192:
                raise MiniError("The sign-in input is too large")
            try:
                event = json.loads(message)
            except (ValueError, RecursionError) as exc:
                raise MiniError("Invalid sign-in input") from exc
            if not isinstance(event, dict) or actions.full():
                raise MiniError("The sign-in connection is busy; cancel and try again")
            actions.put_nowait(cast(dict[str, Any], event))
            receiver = asyncio.create_task(socket.receive_text())
    except WebSocketDisconnect:
        pass
    except MiniError as exc:
        if socket.client_state == WebSocketState.CONNECTED:
            await socket.send_json({"error": str(exc)})
    finally:
        with CancelScope(shield=True):
            receiver.cancel()
            worker.cancel()
            try:
                await asyncio.gather(receiver, worker, return_exceptions=True)
            finally:
                VERIFY.release()
            if socket.application_state == WebSocketState.CONNECTED:
                await socket.close()


@router.post("/api/session/logout")
def logout(request: Request) -> JSONResponse:
    """Invalidate this server session without touching separate Forms credentials"""
    auth = identity(request)
    with auth.lock:
        auth.sessions.pop(request.cookies.get(auth.cookie, ""), None)
        auth.attempts.pop(request.cookies.get(auth.cookie, ""), None)
    response = JSONResponse({"user": ""})
    response.delete_cookie(
        auth.cookie,
        path="/" if auth.origin else "/api",
        secure=bool(auth.origin),
        httponly=True,
        samesite="lax",
    )
    return response
