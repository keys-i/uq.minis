"""Expose a cancellable, tenant-owned YouTube connection without a public relay

Ordinary HTTP requests retain the gateway's workspace ownership checks
Only an active connection can supply control references or save provider cookies
"""

from __future__ import annotations

import asyncio
import json
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request

from uq_minis.core.common import MiniError
from uq_minis.core.window import Window, window
from uq_minis.minis.timey import connect


class Connection:
    """Own one short-lived browser, closing it after inactivity or app shutdown"""

    def __init__(self) -> None:
        """Create no browser process until the person explicitly connects"""
        self.stack = AsyncExitStack()
        self.browser: Window | None = None
        self.lock = asyncio.Lock()
        self.timer: asyncio.TimerHandle | None = None

    async def close(self) -> None:
        """Release the browser before forgetting its ephemeral control references"""
        async with self.lock:
            if self.timer:
                self.timer.cancel()
                self.timer = None
            await self.stack.aclose()
            self.browser = None

    async def _view(self) -> dict[str, Any]:
        """Finish a valid provider return before exposing the next bounded view"""
        assert self.browser is not None
        if connect.allowed(self.browser.page.url) and self.browser.page.url.startswith(
            "https://www.youtube.com/"
        ):
            cookies = cast(list[dict[str, Any]], await self.browser.page.context.cookies())
            if connect.authenticated(cookies):
                connect.save(cookies)
                return {"connected": True}
        return await self.browser.view()

    async def view(self) -> dict[str, Any]:
        """Read the active provider page while retaining connection ownership"""
        async with self.lock:
            if self.browser is None:
                raise MiniError("The YouTube window closed; open the connection again to continue")
            return await self._view()

    async def act(self, event: dict[str, Any]) -> dict[str, Any]:
        """Apply one bounded action to this workspace's current provider page"""
        kind = event.get("kind")
        if kind in {"cancel", "disconnect"}:
            await self.close()
            if kind == "disconnect":
                connect.disconnect()
            return {"connected": bool(connect.cookiefile()), "open": False}
        async with self.lock:
            if kind == "open" and self.browser is None:
                self.browser = await self.stack.enter_async_context(
                    window(connect.LOGIN, connect.allowed, "YouTube")
                )
                self.timer = asyncio.get_running_loop().call_later(
                    300, lambda: asyncio.create_task(self.close())
                )
            if self.browser is None:
                raise MiniError("Open the YouTube connection again to continue")
            if kind == "finish":
                if not connect.allowed(
                    self.browser.page.url
                ) or not self.browser.page.url.startswith("https://www.youtube.com/"):
                    raise MiniError("Finish Google's sign-in and return to YouTube before saving")
                connect.save(cast(list[dict[str, Any]], await self.browser.page.context.cookies()))
                return {"connected": True}
            if kind != "open":
                await self.browser.act(event)
            return await self._view()


def install(app: FastAPI) -> None:
    """Compose connection cleanup with existing app resources and register its API"""
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        async with previous(application):
            connection = Connection()
            application.state.youtube = connection
            try:
                yield
            finally:
                await connection.close()

    app.router.lifespan_context = lifespan

    @app.api_route("/api/timey/youtube", methods=["GET", "POST"])
    async def youtube(request: Request) -> dict[str, Any]:
        """Keep sign-in frames and actions inside the existing workspace boundary"""
        connection = cast(Connection | None, getattr(request.app.state, "youtube", None))
        if connection is None:
            raise HTTPException(503, "The YouTube connection is starting; try again shortly")
        if request.method == "GET":
            if request.query_params.get("view") == "1":
                result = await connection.view()
                if result.get("connected") is True:
                    await connection.close()
                return result
            async with connection.lock:
                return {
                    "connected": bool(connect.cookiefile()),
                    "open": connection.browser is not None,
                }
        body = await request.body()
        if len(body) > 8192:
            raise MiniError("The sign-in action is too large")
        try:
            event = json.loads(body)
        except (ValueError, RecursionError) as exc:
            raise MiniError("The sign-in action could not be read") from exc
        if not isinstance(event, dict):
            raise MiniError("The sign-in action must name a control")
        try:
            result = await connection.act(cast(dict[str, Any], event))
        except Exception:
            await connection.close()
            raise
        if result.get("connected") is True:
            await connection.close()
        return result
