"""Route guest tools and verified Eventy accounts to isolated systemd workspaces

The public process owns sessions and opaque calendar capabilities only
Domain operations run under separate dynamic Unix users and working directories
Socket permissions and a per-workspace delegate secret protect the internal API
A bounded warm pool evicts idle processes only when another workspace needs room
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
import shutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

import httpx
from anyio import CancelScope
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from uq_minis.app import session
from uq_minis.core.common import MiniError, atomic_json

ACCOUNT = re.compile(
    r"(?:guest:[a-f0-9]{64}|[a-z0-9][a-z0-9._+-]{0,63}@(?:student\.uq\.edu\.au|uq\.edu\.au|uqconnect\.edu\.au))"
)
HOP = {
    "connection",
    "transfer-encoding",
    "keep-alive",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "host",
    "cookie",
    "authorization",
    "set-cookie",
    "content-length",
    "content-encoding",
}


@dataclass
class Tenant:
    """Own one socket client and count requests that must not be evicted"""

    key: str
    secret: str
    client: httpx.AsyncClient
    busy: int = 0
    used: float = field(default_factory=monotonic)


@dataclass
class Job:
    """Keep a bounded response available only to the requesting account"""

    account: str
    task: asyncio.Task[Response]
    expires: float = field(default_factory=lambda: monotonic() + 1800)


class Workspaces:
    """Lease private native backends without changing any mini's filesystem rules"""

    def __init__(self, root: Path = Path("/var/lib/minis/workspaces")) -> None:
        """Keep identity records outside all tenant filesystems"""
        self.root = root
        self.active: dict[str, Tenant] = {}
        self.lock = asyncio.Lock()
        self.jobs: dict[str, Job] = {}

    async def unit(self, verb: str, key: str) -> None:
        """Ask polkit to manage only the validated workspace's template units"""
        if verb not in {"start", "stop"} or not re.fullmatch(r"[a-f0-9]{24}", key):
            raise MiniError("Invalid workspace operation")
        units = [f"minis@{key}.socket"]
        if verb == "stop":
            units.append(f"minis@{key}.service")
        process = await asyncio.create_subprocess_exec(
            "systemctl",
            "--no-ask-password",
            verb,
            *units,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            code = await asyncio.wait_for(process.wait(), 35)
        except BaseException:
            process.kill()
            await process.wait()
            raise
        if code:
            raise MiniError("Your workspace could not start; try again shortly")

    @asynccontextmanager
    async def lease(self, account: str) -> AsyncGenerator[Tenant]:
        """Reserve capacity before starting a tenant and protect in-flight work"""
        if not ACCOUNT.fullmatch(account):
            raise MiniError("Open Minis to prepare your private workspace")
        key = hashlib.sha256(account.encode()).hexdigest()[:24]
        async with self.lock:
            tenant = self.active.get(key)
            if tenant is None:
                if len(self.active) >= 2:
                    idle = [item for item in self.active.values() if not item.busy]
                    if not idle:
                        raise MiniError("The workspaces are busy; try again shortly")
                    oldest = min(idle, key=lambda item: item.used)
                    await self.unit("stop", oldest.key)
                    await oldest.client.aclose()
                    del self.active[oldest.key]
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                if shutil.disk_usage(self.root).free < 2 * 1024**3:
                    raise MiniError("The workspace disk needs attention; your saved files are safe")
                record = self.root / f"{key}.json"
                if record.exists():
                    values = json.loads(record.read_text())
                    if values.get("account") != account:
                        raise MiniError("The workspace identity does not match")
                    secret = values["secret"]
                    if not isinstance(secret, str) or len(secret) != 64:
                        raise MiniError("The workspace identity needs repair")
                else:
                    if account.startswith("guest:") and len(list(self.root.glob("*.json"))) >= 256:
                        raise MiniError(
                            "Guest workspaces are full; your existing saved files are safe"
                        )
                    secret = secrets.token_hex(32)
                    atomic_json(record, {"account": account, "secret": secret}, private=True)
                await self.unit("start", key)
                tenant = Tenant(
                    key,
                    secret,
                    httpx.AsyncClient(
                        transport=httpx.AsyncHTTPTransport(uds=f"/run/minis/{key}.sock"),
                        base_url="http://127.0.0.1:8765",
                        timeout=httpx.Timeout(1800, connect=30),
                        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
                        trust_env=False,
                    ),
                )
                self.active[key] = tenant
            if tenant.busy >= 8:
                raise MiniError("This workspace is busy; let the current work finish first")
            tenant.busy += 1
        try:
            yield tenant
        finally:
            tenant.busy -= 1
            tenant.used = monotonic()

    async def close(self) -> None:
        """Cancel owned work and stop listeners before shutting down the gateway"""
        for job in self.jobs.values():
            job.task.cancel()
        await asyncio.gather(*(job.task for job in self.jobs.values()), return_exceptions=True)
        for tenant in self.active.values():
            await tenant.client.aclose()
            await self.unit("stop", tenant.key)
        self.active.clear()

    async def collect(self) -> None:
        """Expire abandoned jobs while retaining the bounded warm workspace pool"""
        while True:
            await asyncio.sleep(30)
            for key, job in list(self.jobs.items()):
                if job.expires < monotonic():
                    job.task.cancel()
                    await asyncio.gather(job.task, return_exceptions=True)
                    del self.jobs[key]

    async def forward(self, account: str, request: Request, body: bytes) -> Response:
        """Replace all browser credentials with the workspace's private delegate"""
        if (
            request.method not in {"GET", "HEAD"}
            and shutil.disk_usage(self.root.parent).free < 6 * 1024**3
        ):
            return JSONResponse(
                {
                    "error": "The workspace disk is nearly full; download a backup and contact the site owner"
                },
                status_code=503,
            )
        async with self.lease(account) as tenant:
            headers = {key: value for key, value in request.headers.items() if key not in HOP}
            headers.update({
                "cookie": f"{session.COOKIE}={tenant.secret}",
                "origin": "http://127.0.0.1:8765",
                "accept-encoding": "identity",
            })
            async with tenant.client.stream(
                request.method,
                request.url.path + ("?" + request.url.query if request.url.query else ""),
                headers=headers,
                content=body,
            ) as result:
                data = bytearray()
                async for chunk in result.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 8 * 1024**2:
                        raise MiniError("The workspace response is too large")
                return Response(
                    bytes(data),
                    status_code=result.status_code,
                    headers={key: value for key, value in result.headers.items() if key not in HOP},
                )


def install(app: FastAPI) -> None:
    """Install the hosted boundary before static files, excluding domain routes"""
    pool = Workspaces()
    app.state.pool = pool
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        async with previous(application):
            collector = asyncio.create_task(pool.collect())
            try:
                yield
            finally:
                collector.cancel()
                await asyncio.gather(collector, return_exceptions=True)
                await pool.close()

    app.router.lifespan_context = lifespan

    @app.api_route("/api/{path:path}", methods=["GET", "HEAD", "POST", "PATCH", "DELETE", "PUT"])
    async def api(request: Request, path: str) -> Response:
        auth = session.identity(request)
        owner = auth.owner(request)
        user = auth.user(request)
        university = request.url.path in session.PROTECTED
        account = user if university else owner
        if not owner or not account:
            return JSONResponse(
                {
                    "error": "Sign in with UQ for Eventy"
                    if university
                    else "Reload Minis to prepare your workspace"
                },
                status_code=401,
            )
        if path != "backup" and request.headers.get("x-minis-account") != owner:
            return JSONResponse(
                {"error": "Your account changed; reload this tab before continuing"},
                status_code=409,
            )
        if university and owner != user and request.headers.get("x-minis-user") != user:
            return JSONResponse(
                {"error": "Your UQ account changed; reload this tab"}, status_code=409
            )
        if path.startswith("jobs/"):
            key = path.removeprefix("jobs/")
            job = pool.jobs.get(key)
            if (
                not job
                or job.account not in {owner, user}
                or (job.account != owner and request.headers.get("x-minis-user") != user)
            ):
                return JSONResponse(
                    {"error": "This task is unavailable; return to your workspace"}, status_code=404
                )
            if request.method == "DELETE":
                job.task.cancel()
                await asyncio.gather(job.task, return_exceptions=True)
                del pool.jobs[key]
                return JSONResponse({})
            if not job.task.done():
                await asyncio.wait({job.task}, timeout=0.8)
            if job.task.done():
                return job.task.result()
            return JSONResponse(
                {}, status_code=202, headers={"Location": f"/api/jobs/{key}", "Retry-After": "0"}
            )
        if path == "calendar":
            record = pool.root / "calendar.json"
            values: dict[str, str] = json.loads(record.read_text()) if record.exists() else {}
            token = next((key for key, value in values.items() if value == account), "")
            if not token:
                token = secrets.token_urlsafe(32)
                values[token] = account
                atomic_json(record, values, private=True)
            return JSONResponse({"url": f"/calendar.ics?key={token}"})
        for key, job in list(pool.jobs.items()):
            if len(pool.jobs) < 16:
                break
            if job.task.done():
                del pool.jobs[key]
        if (
            len(pool.jobs) >= 16
            or sum(job.account == account and not job.task.done() for job in pool.jobs.values())
            >= 4
        ):
            return JSONResponse(
                {"error": "Let the current tasks finish before starting another"},
                status_code=429,
                headers={"Retry-After": "2"},
            )
        incoming = bytearray()
        async for chunk in request.stream():
            incoming.extend(chunk)
            if len(incoming) > 8 * 1024**2:
                return JSONResponse(
                    {"error": "Use the file picker to upload large files in parts"}, status_code=413
                )
        body = bytes(incoming)

        async def run() -> Response:
            try:
                return await pool.forward(account, request, body)
            except (MiniError, httpx.HTTPError, OSError) as exc:
                return JSONResponse(
                    {
                        "error": str(exc)
                        if isinstance(exc, MiniError)
                        else "Your workspace lost its connection; try again shortly"
                    },
                    status_code=503,
                )

        task = asyncio.create_task(run())
        try:
            done, _ = await asyncio.wait({task}, timeout=1)
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        if done:
            return task.result()
        key = secrets.token_urlsafe(24)
        pool.jobs[key] = Job(account, task)
        return JSONResponse(
            {}, status_code=202, headers={"Location": f"/api/jobs/{key}", "Retry-After": "0"}
        )

    @app.api_route("/download/{key}", methods=["GET", "HEAD"])
    @app.api_route("/calendar.ics", methods=["GET", "HEAD"])
    async def download(request: Request, key: str = "") -> Response:
        auth = session.identity(request)
        account = (
            auth.user(request) if request.query_params.get("uq") == "on" else auth.owner(request)
        )
        if request.url.path == "/calendar.ics":
            record = pool.root / "calendar.json"
            values: dict[str, str] = json.loads(record.read_text()) if record.exists() else {}
            account = values.get(request.query_params.get("key", ""), "")
        if not account:
            return JSONResponse(
                {"error": "Sign in to open this file or use your private calendar link"},
                status_code=401,
            )
        lease = pool.lease(account)
        tenant = await lease.__aenter__()
        try:
            headers = {"cookie": f"{session.COOKIE}={tenant.secret}", "accept-encoding": "identity"}
            if selected := request.headers.get("range"):
                headers["range"] = selected
            upstream = tenant.client.build_request(
                request.method, request.url.path, headers=headers
            )
            result = await tenant.client.send(upstream, stream=True)
        except BaseException:
            await lease.__aexit__(None, None, None)
            raise

        async def content() -> AsyncGenerator[bytes]:
            try:
                async for chunk in result.aiter_bytes():
                    yield chunk
            finally:
                with CancelScope(shield=True):
                    await result.aclose()
                    await lease.__aexit__(None, None, None)

        headers = {name: value for name, value in result.headers.items() if name not in HOP}
        if length := result.headers.get("content-length"):
            headers["content-length"] = length
        return StreamingResponse(content(), status_code=result.status_code, headers=headers)
