"""Shared FastAPI boundary for local minis and isolated hosted workspaces

Local mode assembles the existing domain routes behind loopback checks
Hosted mode exposes public home metadata and the UQ session gateway, delegating
domain operations to private accounts with the same origin and upload boundaries
"""

from __future__ import annotations

import importlib
import json
import re
import secrets
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from uq_minis.app import session
from uq_minis.app.art import router as art
from uq_minis.app.core import TOOLS, Workspace
from uq_minis.core.art import RESIDENTS
from uq_minis.core.common import MiniError

REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; style-src-elem 'self'; "
    "style-src-attr 'unsafe-inline'; "
    "img-src 'self' data: blob: https://resources.getqpay.com "
    "https://resources.hellorubric.com https://i.ytimg.com; "
    "font-src 'self' data:; media-src 'self' data: blob:; worker-src 'self' blob:; "
    "connect-src 'self' wss://uni.keysi.dev; object-src 'none'; frame-src 'none'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


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
    app.state.http_metrics = {
        "requests": 0,
        "errors": 0,
        "in_flight": 0,
        "duration_ms": 0.0,
    }
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

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict[str, str]:
        """Report process readiness without disclosing dependency or account state"""
        return {"status": "ok", "service": "uq-minis"}

    @app.get("/internal/metrics", include_in_schema=False)
    def metrics() -> PlainTextResponse:
        """Expose label-free process metrics only through the private Unix socket"""
        values = app.state.http_metrics
        lines = (
            f"uq_minis_http_requests_total {values['requests']}",
            f"uq_minis_http_errors_total {values['errors']}",
            f"uq_minis_http_in_flight {values['in_flight']}",
            f"uq_minis_http_duration_milliseconds_total {values['duration_ms']:.3f}",
        )
        return PlainTextResponse(
            "\n".join(lines) + "\n",
            media_type="text/plain; version=0.0.4",
            headers={"Cache-Control": "no-store"},
        )

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
            "Content-Security-Policy": CSP,
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

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Correlate requests and retain only bounded aggregate process telemetry"""
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if REQUEST_ID.fullmatch(supplied) else secrets.token_hex(16)
        values = app.state.http_metrics
        values["requests"] += 1
        values["in_flight"] += 1
        started = monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers.update({
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Permissions-Policy": (
                    "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
                ),
                "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
                "Cross-Origin-Resource-Policy": "same-origin",
            })
            response.headers.setdefault("Content-Security-Policy", CSP)
            return response
        finally:
            duration = (monotonic() - started) * 1000
            values["in_flight"] -= 1
            values["duration_ms"] += duration
            if status >= 500:
                values["errors"] += 1
            if origin:
                print(
                    json.dumps(
                        {
                            "event": "http_request",
                            "request_id": request_id,
                            "method": request.method,
                            "path": request.url.path,
                            "status": status,
                            "duration_ms": round(duration, 3),
                        },
                        separators=(",", ":"),
                    ),
                    file=sys.stdout,
                    flush=True,
                )

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
        index = built / "index.html"

        def mini_shell() -> FileResponse:
            return FileResponse(index, media_type="text/html")

        for mini in ("planny", "scrappy", "buzzy", "clubby", "event", "timey"):
            app.add_api_route(f"/{mini}", mini_shell, include_in_schema=False)
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
