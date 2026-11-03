from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, call

import httpx
import pytest
from fastapi.testclient import TestClient

from uq_minis.app import connect as connection
from uq_minis.app import create
from uq_minis.core.common import MiniError
from uq_minis.core.window import Window
from uq_minis.minis.auth import portal
from uq_minis.minis.timey import connect


def test_destinations() -> None:
    assert connect.allowed(connect.LOGIN)
    assert not portal.allowed(connect.LOGIN)
    for url in [
        "http://accounts.google.com/",
        "https://accounts.google.com.evil.test/",
        "https://accounts.google.com@evil.test/",
        "https://127.0.0.1/",
        "file:///etc/passwd",
        "https://www.youtube.com:22/",
    ]:
        assert not connect.allowed(url)


def test_private_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert connect.cookiefile() is None
    cookies: list[dict[str, Any]] = [
        {
            "name": "SID",
            "value": "private-session",
            "domain": ".youtube.com",
            "secure": True,
            "httpOnly": True,
            "expires": -1,
        },
        {
            "name": "unrelated",
            "value": "ignore",
            "domain": ".evil.test",
            "secure": True,
        },
    ]
    connect.save(cookies)
    path = connect.cookiefile()
    assert (
        path is not None
        and "private-session" in path.read_text()
        and "ignore" not in path.read_text()
    )
    assert not path.stat().st_mode & 0o077
    for invalid in (
        {**cookies[0], "expires": 1},
        {**cookies[0], "domain": "accounts.google.com"},
    ):
        with pytest.raises(MiniError, match="Finish"):
            connect.save([invalid])
        assert "private-session" in path.read_text()
    other = tmp_path / "other"
    other.mkdir()
    with monkeypatch.context() as context:
        context.chdir(other)
        assert connect.cookiefile() is None
    connect.disconnect()
    assert connect.cookiefile() is None
    assert not list(connect.ROOT.glob(".cookies-*"))


def test_cookie_links(tmp_path: Path) -> None:
    secret = tmp_path / "private"
    secret.write_text("do not touch")
    connect.ROOT.mkdir(parents=True)
    connect.COOKIES.symlink_to(secret)
    with pytest.raises(MiniError, match="links"):
        connect.disconnect()
    assert secret.read_text() == "do not touch"


def test_actions() -> None:
    with cast(
        httpx.Client,
        TestClient(
            create(),
            base_url="http://127.0.0.1:8765",
            headers={"Origin": "http://127.0.0.1:8765"},
        ),
    ) as client:
        assert client.get("/api/timey/youtube").json() == {
            "connected": False,
            "open": False,
        }
        bodies: list[object] = [
            [],
            {"kind": "finish"},
            {"kind": "fill", "id": "invented", "value": "secret"},
        ]
        for body in bodies:
            assert client.post("/api/timey/youtube", json=body).status_code == 400
        assert client.post("/api/timey/youtube", content="x" * 8193).status_code == 400
        assert client.post("/api/timey/youtube", json={"kind": "disconnect"}).status_code == 200


def test_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []
    page = SimpleNamespace(
        url="https://accounts.google.com/ServiceLogin",
        context=SimpleNamespace(
            cookies=AsyncMock(
                return_value=[
                    {
                        "name": "SID",
                        "value": "private-session",
                        "domain": ".youtube.com",
                        "secure": True,
                    }
                ]
            )
        ),
    )
    browser = cast(
        Window,
        SimpleNamespace(
            page=page,
            view=AsyncMock(return_value={"image": "frame"}),
            revision=AsyncMock(return_value="accounts"),
        ),
    )

    @asynccontextmanager
    async def window(*_args: object) -> AsyncGenerator[Window]:
        try:
            yield browser
        finally:
            closed.append(True)

    monkeypatch.setattr(connection, "window", window)
    with cast(
        httpx.Client,
        TestClient(
            create(),
            base_url="http://127.0.0.1:8765",
            headers={"Origin": "http://127.0.0.1:8765"},
        ),
    ) as client:
        assert client.post("/api/timey/youtube", json={"kind": "open"}).status_code == 200
        page.url = "https://www.youtube.com/"
        response = client.get("/api/timey/youtube?view=1")
        assert response.json() == {"connected": True}
        assert client.get("/api/timey/youtube").json() == {
            "connected": True,
            "open": False,
        }
        assert closed == [True]


@pytest.mark.anyio
async def test_connection_reuses_idle_pixels_and_acknowledges_typing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = SimpleNamespace(
        url="https://accounts.google.com/ServiceLogin",
        context=SimpleNamespace(cookies=AsyncMock(return_value=[])),
    )
    render = AsyncMock(return_value={"image": "frame"})
    revision = AsyncMock(return_value="steady")
    action = AsyncMock()
    calls = Mock()
    calls.attach_mock(revision, "revision")
    calls.attach_mock(render, "view")
    browser = cast(
        Window,
        SimpleNamespace(
            page=page,
            view=render,
            revision=revision,
            act=action,
        ),
    )
    session = connection.Connection()
    session.browser = browser
    assert await session._render() == {"image": "frame"}
    assert calls.mock_calls[:2] == [call.revision(), call.view()]
    monkeypatch.setattr(connection, "VIEW_WAIT", 0)
    assert await session.view() == {"acknowledged": True}
    render.assert_awaited_once()

    disconnected = AsyncMock(return_value=True)
    assert await session.view(disconnected) == {"acknowledged": True}
    disconnected.assert_awaited_once()

    result = await session.act({"kind": "fill", "id": "email", "value": "member@example.org"})
    assert result == {"acknowledged": True}
    render.assert_awaited_once()
    action.assert_awaited_once()

    revision.return_value = "next page"
    assert await session.view() == {"image": "frame"}
    assert render.await_count == 2
