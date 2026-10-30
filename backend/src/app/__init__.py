"""Shared FastAPI boundary for local minis and isolated hosted workspaces

Local mode assembles the existing domain routes behind loopback checks
Hosted mode exposes public home metadata and the UQ session gateway, delegating
domain operations to private accounts with the same origin and upload boundaries
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from uq_minis.app import session
from uq_minis.app.art import router as art
from uq_minis.app.core import TOOLS, Workspace
from uq_minis.core.art import RESIDENTS
from uq_minis.core.common import MiniError


def create(
    *,
    state: Path | None = None,
    courses: Path | None = None,
    clubs: Path | None = None,
    port: int = 8765,
    frontend: Path | None = None,
    origin: str = "",
    delegate: tuple[str, str] | None = None,
) -> FastAPI:
    """Build a local mini backend or the hosted account gateway

    Args:
        state: Optional local plan path, leaving other mini paths unchanged
        courses: Optional local offering catalogue
        clubs: Optional local club catalogue
        port: Loopback port used by local HTTP and WebSocket authority checks
        frontend: Built React assets to serve after API routes
        origin: The configured university HTTPS origin for hosted gateway mode
        delegate: Internal account and secret loaded from systemd credentials
            Never accept this tuple from a browser or another untrusted caller

    Returns:
        Application with matching HTTP, WebSocket and workspace boundaries
    """
    if origin and origin != "https://uni.keysi.dev":
        raise MiniError("Hosted minis requires the configured university HTTPS origin")
    from uq_minis.core.paths import migrate

    migrate()
    context = Workspace(port=port)
    if state is not None:
        context.state = state
    if courses is not None:
        context.courses = courses
    if clubs is not None:
        context.clubs = clubs
    app = FastAPI(title="UQ minis", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.workspace = context
    app.state.identity = session.Identity(origin=origin, delegate=delegate)
    from uq_minis.app.weather import install as weather

    weather(app)
    app.include_router(art)
    app.include_router(session.router)
    tools = dict(TOOLS)
    for source in (Path(__file__).resolve().parents[1] / "minis").glob("*/__init__.py"):
        module = source.parent.name
        if module.isidentifier() and Path(__file__).with_name(f"{module}.py").is_file():
            name = module.replace("_", "-")
            tools.setdefault(name, (name.replace("-", " ").title(), "Open this mini"))

    @app.get("/api/minis")
    def minis() -> dict[str, Any]:
        """List public mini descriptions without opening a private workspace"""
        return {
            name: {
                "title": values[0],
                "about": values[1],
                "animal": RESIDENTS.get(name, "numbat"),
            }
            for name, values in tools.items()
            if name not in {"auth", "agent"}
        }

    @app.get("/api/languages")
    def languages() -> dict[str, Any]:
        """Offer public language names while retaining private translation requests"""
        from uq_minis.core import translate

        return {
            "languages": translate.LANGUAGES,
            "configured": translate.configured(),
            "provider": "Microsoft Translator",
        }

    if not origin:
        from uq_minis.app.connect import install as connect

        connect(app)
        from uq_minis.app.research import router as research

        app.include_router(research)

    @app.middleware("http")
    async def local(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origins = {f"http://{host}" for host in allowed} | {
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }
        if origin:
            from urllib.parse import urlsplit

            allowed = {urlsplit(origin).netloc}
            origins = {origin}
        if (
            request.headers.get("host") not in allowed
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            return JSONResponse(
                {"error": "Use the local minis address shown in the terminal"}, status_code=400
            )
        if request.method not in {"GET", "HEAD"}:
            if request.headers.get("origin") not in origins:
                return JSONResponse(
                    {"error": "Open minis locally before changing data"}, status_code=400
                )
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                length = 0
            upload = request.url.path == "/api/timey/source"
            limit = 8 * 1024**2
            if upload and not origin:
                from uq_minis.app.timey import UPLOAD_LIMIT

                limit = UPLOAD_LIMIT
            if not 0 < length <= limit and not (upload and length == 0):
                return JSONResponse(
                    {
                        "error": "Choose a video under 512 MiB"
                        if upload
                        else "Requests must contain at most 8 MiB"
                    },
                    status_code=413,
                )
        auth = session.identity(request)
        if delegate and not auth.owner(request):
            return JSONResponse({"error": "Workspace authentication required"}, status_code=401)
        protected = request.url.path in session.PROTECTED
        if protected and not auth.user(request):
            return JSONResponse(
                {
                    "error": "Sign in with UQ before opening this workflow",
                    "login": "/api/session/login",
                },
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        # Private workers own upstream limits; local form metadata does no upstream work
        outbound = (
            request.url.path in session.OUTBOUND
            and (not origin or not auth.user(request) or request.url.path == "/api/session/login")
            and not (
                request.method in {"GET", "HEAD"} and request.url.path.startswith("/api/minis/")
            )
        )
        if outbound and not auth.enter():
            return JSONResponse(
                {"error": "The source is busy; wait a minute before trying again"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        try:
            response = await call_next(request)
        finally:
            if outbound:
                with auth.lock:
                    auth.busy -= 1
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob: https://resources.getqpay.com https://resources.hellorubric.com https://i.ytimg.com; connect-src 'self' https: http:; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        if request.url.path.startswith("/api/weather/") and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
        if response.status_code in {200, 304} and re.fullmatch(
            r"/assets/[^/]+-[\w-]{8,}\.[\w]+", request.url.path, flags=re.ASCII
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        if request.url.path.startswith("/api/habitat/") and response.headers.get(
            "content-type", ""
        ).startswith("image/svg+xml"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'unsafe-inline'; sandbox"
            )
            response.headers["Cache-Control"] = "private, max-age=300"
        if request.url.path == "/api/brand/uq.png" and response.status_code == 200:
            response.headers["Cache-Control"] = "private, max-age=300"
        return response

    async def expected(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            {"error": str(exc)}, status_code=409 if "Another tab" in str(exc) else 400
        )

    for exception in (MiniError, OSError, ValueError):
        app.add_exception_handler(exception, expected)

    if origin:
        from uq_minis.app.gateway import install
        from uq_minis.app.timey import home

        app.add_api_route("/api/minis/timey", home, methods=["GET"])
        install(app)
    else:

        @app.get("/download/{key}")
        def download(key: str) -> FileResponse:
            path = context.download(key)
            if path is None or not path.is_file() or path.is_symlink():
                raise MiniError(
                    "Download unavailable; open the completed file in your export directory"
                )
            return FileResponse(
                path,
                filename=path.name,
                media_type="audio/mp4" if path.suffix.lower() == ".m4a" else None,
                headers={"Cache-Control": "private, max-age=0, must-revalidate"},
            )

        for name in tools:
            routes: Any = importlib.import_module(f"uq_minis.app.{name.replace('-', '_')}")
            app.include_router(routes.router)

    built = frontend or Path(__file__).resolve().parents[3] / "out/artifacts/frontend"
    if built.is_dir():
        app.mount("/", StaticFiles(directory=built, html=True), name="frontend")
    else:

        @app.get("/")
        def setup() -> dict[str, str]:
            return {
                "message": "The backend is ready. Build the React frontend or run its Vite development server",
                "development": "npm --prefix frontend run dev",
                "build": "npm --prefix frontend run build",
            }

    return app
