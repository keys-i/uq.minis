import asyncio
import os
import shutil
from pathlib import Path
from time import monotonic
from typing import cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from uq_minis.app import create, session
from uq_minis.app.gateway import Job, Workspaces
from uq_minis.core.common import MiniError


def test_public_home(tmp_path: Path) -> None:
    app = create(origin="https://uni.keysi.dev")
    pool = cast(Workspaces, app.state.pool)
    pool.root = tmp_path
    pool.unit = AsyncMock()
    with TestClient(app, base_url="https://uni.keysi.dev") as connection:
        client = cast(httpx.Client, connection)
        response = client.get("/api/minis")
        assert response.status_code == 200
        assert set(response.json()) == {"scrappy", "planny", "buzzy", "clubby", "event", "timey"}
        assert client.get("/api/languages").status_code == 200
        assert client.get("/api/minis/timey").json()["tool"] == "timey"
        for path in ("/api/plan", "/download/private"):
            assert client.get(path).status_code == 401
        assert not pool.active
        pool.unit.assert_not_awaited()


def test_boundary(tmp_path: Path) -> None:
    app = create(origin="https://uni.keysi.dev")
    pool = cast(Workspaces, app.state.pool)
    pool.root = tmp_path
    with TestClient(app, base_url="https://uni.keysi.dev") as connection:
        client = cast(httpx.Client, connection)
        for path in ("/api/plan", "/download/a", "/calendar.ics"):
            assert client.get(path).status_code == 401
        assert client.get("/api/session").json()["hosted"]
        client.cookies.delete(session.GUEST_COOKIE)
        app.state.identity.sessions["a"] = (monotonic() + 60, "a@uq.edu.au")
        client.cookies.set("__Host-minis_session", "a")
        assert client.get("/api/plan").status_code == 409
        assert (
            client.get("/api/plan", headers={"X-Minis-Account": "b@uq.edu.au"}).status_code == 409
        )
        assert (
            client.post("/api/plan", json={}, headers={"Origin": "https://evil.test"}).status_code
            == 400
        )
        assert client.get("/api/session", headers={"Host": "evil.test"}).status_code == 400
        feed = client.get("/api/calendar", headers={"X-Minis-Account": "a@uq.edu.au"}).json()["url"]
        app.state.identity.sessions["b"] = (monotonic() + 60, "b@uq.edu.au")
        client.cookies.set("__Host-minis_session", "b")
        other = client.get("/api/calendar", headers={"X-Minis-Account": "b@uq.edu.au"}).json()[
            "url"
        ]
        assert feed != other and "a@" not in feed
        assert client.get("/calendar.ics?key=guessed").status_code == 401


def test_guest(tmp_path: Path) -> None:
    app = create(origin="https://uni.keysi.dev")
    pool = cast(Workspaces, app.state.pool)
    pool.root = tmp_path
    pool.forward = AsyncMock(return_value=JSONResponse({"ok": True}))
    with TestClient(app, base_url="https://uni.keysi.dev") as connection:
        client = cast(httpx.Client, connection)
        status = client.get("/api/session")
        owner = status.json()["workspace"]
        assert owner.startswith("guest:") and not status.json()["user"]
        assert client.cookies[session.GUEST_COOKIE] not in owner
        assert "HttpOnly" in status.headers["set-cookie"]
        headers = {"X-Minis-Account": owner}
        for path in ("/api/plan", "/api/minis/scrappy", "/api/minis/clubby"):
            assert client.get(path, headers=headers).status_code == 200
            assert pool.forward.call_args.args[0] == owner
        callback = client.get(
            "/api/timey/youtube/callback?state=provider&code=one-use",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        assert callback.status_code == 200
        assert pool.forward.call_args.args[0] == owner
        assert client.get("/api/minis/event", headers=headers).status_code == 401
        app.state.identity.sessions["uq"] = (monotonic() + 60, "a@uq.edu.au")
        client.cookies.set(session.HOST_COOKIE, "uq")
        assert client.get("/api/session").json()["workspace"] == owner
        assert client.get("/api/minis/event", headers=headers).status_code == 409
        assert (
            client.get(
                "/api/minis/event", headers={**headers, "X-Minis-User": "a@uq.edu.au"}
            ).status_code
            == 200
        )
        assert pool.forward.call_args.args[0] == "a@uq.edu.au"
        assert client.get("/api/plan", headers=headers).status_code == 200
        assert pool.forward.call_args.args[0] == owner
        client.cookies.clear()
        other = client.get("/api/session").json()["workspace"]
        assert other != owner
        assert client.get("/api/plan", headers=headers).status_code == 409
        assert client.get("/api/plan", headers={"X-Minis-Account": other}).status_code == 200
        assert pool.forward.call_args.args[0] == other


def test_guest_delegate(tmp_path: Path) -> None:
    app = create(state=tmp_path / "plan.json", delegate=("guest:" + "a" * 64, "private"))
    with TestClient(app, base_url="http://127.0.0.1:8765") as connection:
        client = cast(httpx.Client, connection)
        client.cookies.set("minis_session", "private")
        assert client.get("/api/plan").status_code == 200
        assert client.get("/api/minis/timey").status_code == 200
        assert client.get("/api/minis/event").status_code == 401
        assert client.get("/api/minis/auth").status_code == 401
        assert client.get("/api/minis/agent").status_code == 401
        assert client.get("/api/session").json()["user"] == ""


def test_delegate(tmp_path: Path) -> None:
    app = create(state=tmp_path / "plan.json", delegate=("a@uq.edu.au", "private"))
    with TestClient(app, base_url="http://127.0.0.1:8765") as connection:
        client = cast(httpx.Client, connection)
        assert client.get("/api/plan").status_code == 401
        client.cookies.set("minis_session", "private")
        assert client.get("/api/plan").status_code == 200
        assert client.get("/api/session").json()["user"] == "a@uq.edu.au"
        app.state.identity.calls.extend([monotonic()] * 30)
        assert client.get("/api/minis/timey").status_code == 200
        assert (
            client.post(
                "/api/timey/clip", json={}, headers={"Origin": "http://127.0.0.1:8765"}
            ).status_code
            == 429
        )


def test_tenant_throttle(tmp_path: Path) -> None:
    app = create(origin="https://uni.keysi.dev")
    pool = cast(Workspaces, app.state.pool)
    pool.root = tmp_path
    pool.forward = AsyncMock(return_value=JSONResponse({"ok": True}))
    app.state.identity.sessions["a"] = (monotonic() + 60, "a@uq.edu.au")
    app.state.identity.calls.extend([monotonic()] * 30)
    with TestClient(app, base_url="https://uni.keysi.dev") as connection:
        client = cast(httpx.Client, connection)
        client.cookies.set("__Host-minis_session", "a")
        response = client.post(
            "/api/timey/clip",
            json={},
            headers={"Origin": "https://uni.keysi.dev", "X-Minis-Account": "a@uq.edu.au"},
        )
        assert response.status_code == 200
        pool.forward.assert_awaited_once()


def test_leases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def check() -> None:
        pool = Workspaces(tmp_path)
        pool.unit = AsyncMock()
        async with pool.lease("a@uq.edu.au") as first:
            async with pool.lease("b@uq.edu.au") as second:
                assert first.key != second.key and first.secret != second.secret
                with pytest.raises(MiniError, match="busy"):
                    async with pool.lease("c@uq.edu.au"):
                        pass
        first.used = 0
        with monkeypatch.context() as timing:
            timing.setattr(asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError]))
            with pytest.raises(asyncio.CancelledError):
                await pool.collect()
        assert first.key in pool.active
        async with pool.lease("c@uq.edu.au"):
            assert first.key not in pool.active
        async with pool.lease("a@uq.edu.au") as recovered:
            assert recovered.secret == first.secret
        if os.name == "posix":
            assert (tmp_path / f"{first.key}.json").stat().st_mode & 0o077 == 0
        with pytest.raises(MiniError):
            async with pool.lease("../../root"):
                pass
        await pool.close()

    asyncio.run(check())


def test_proxy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def check() -> None:
        pool = Workspaces(tmp_path)
        pool.unit = AsyncMock()
        async with pool.lease("a@uq.edu.au") as tenant:
            await tenant.client.aclose()

            def receive(request: httpx.Request) -> httpx.Response:
                assert request.headers["cookie"] == "minis_session=" + tenant.secret
                assert request.headers["origin"] == "http://127.0.0.1:8765"
                assert request.headers["x-minis-origin"] == "https://uni.keysi.dev"
                assert "authorization" not in request.headers
                return httpx.Response(
                    400, json={"error": "real failure"}, headers={"Set-Cookie": "bad=1"}
                )

            tenant.client = httpx.AsyncClient(
                transport=httpx.MockTransport(receive), base_url="http://127.0.0.1:8765"
            )
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/api/plan",
            "query_string": b"",
            "headers": [
                (b"cookie", b"minis_session=browser"),
                (b"authorization", b"Bearer browser"),
                (b"x-minis-origin", b"https://evil.test"),
            ],
        })
        result = await pool.forward("a@uq.edu.au", request, b"{}")
        assert result.status_code == 400 and "set-cookie" not in result.headers
        low = shutil.disk_usage(tmp_path)._replace(free=0)
        monkeypatch.setattr(shutil, "disk_usage", Mock(return_value=low))
        assert (await pool.forward("a@uq.edu.au", request, b"{}")).status_code == 503
        request.scope["method"] = "GET"
        assert (await pool.forward("a@uq.edu.au", request, b"")).status_code == 400
        await pool.close()

    asyncio.run(check())


def test_jobs(tmp_path: Path) -> None:
    app = create(origin="https://uni.keysi.dev")
    pool = cast(Workspaces, app.state.pool)
    pool.root = tmp_path
    with TestClient(app, base_url="https://uni.keysi.dev") as connection:
        client = cast(httpx.Client, connection)
        app.state.identity.sessions["b"] = (monotonic() + 60, "b@uq.edu.au")
        client.cookies.set("__Host-minis_session", "b")

        async def insert() -> None:
            task = asyncio.create_task(
                asyncio.sleep(0, result=JSONResponse({"error": "failed"}, status_code=422))
            )
            await task
            pool.jobs["owned"] = Job("a@uq.edu.au", task)

        assert connection.portal is not None
        connection.portal.call(insert)
        headers = {"X-Minis-Account": "b@uq.edu.au"}
        assert client.get("/api/jobs/owned", headers=headers).status_code == 404
        pool.jobs["owned"].account = "b@uq.edu.au"
        assert client.get("/api/jobs/owned", headers=headers).status_code == 422
        assert (
            client.request(
                "DELETE",
                "/api/jobs/owned",
                headers={**headers, "Origin": "https://uni.keysi.dev", "Content-Length": "2"},
                content=b"{}",
            ).status_code
            == 200
        )

        async def fill() -> None:
            task = asyncio.create_task(asyncio.sleep(0, result=JSONResponse({})))
            await task
            for number in range(16):
                pool.jobs[str(number)] = Job("a@uq.edu.au", task)

        connection.portal.call(fill)
        pool.forward = AsyncMock(return_value=JSONResponse({"ok": True}))
        assert client.get("/api/plan", headers=headers).status_code == 200
        assert len(pool.jobs) == 15
    assert len(pool.jobs) == 15


@pytest.mark.parametrize("selected", [None, "bytes=1-2"])
def test_download(tmp_path: Path, selected: str | None) -> None:
    app = create(origin="https://uni.keysi.dev")
    pool = cast(Workspaces, app.state.pool)
    pool.root = tmp_path / "workspaces"
    pool.unit = AsyncMock()
    picture = tmp_path / "picture.png"
    picture.write_bytes(b"data")
    with TestClient(app, base_url="https://uni.keysi.dev") as connection:
        client = cast(httpx.Client, connection)
        app.state.identity.sessions["a"] = (monotonic() + 60, "a@uq.edu.au")
        client.cookies.set("__Host-minis_session", "a")

        async def prepare() -> None:
            async with pool.lease("a@uq.edu.au") as tenant:
                await tenant.client.aclose()
                internal = create(delegate=("a@uq.edu.au", tenant.secret))
                internal.state.workspace.downloads["file"] = picture
                tenant.client = httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=internal), base_url="http://127.0.0.1:8765"
                )

        assert connection.portal is not None
        connection.portal.call(prepare)
        response = client.get("/download/file", headers={"Range": selected} if selected else {})
        assert response.status_code == (206 if selected else 200), response.text
        assert response.content == (b"at" if selected else b"data")
        assert response.headers["content-length"] == str(len(response.content))
        client.cookies.clear()
        assert client.get("/download/file").status_code == 401
