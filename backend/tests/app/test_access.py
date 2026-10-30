from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from uq_minis.app import create
from uq_minis.app.session import Identity
from uq_minis.core.common import MiniError
from uq_minis.minis.auth import portal


def test_form_submission() -> None:
    import asyncio

    async def check() -> None:
        page = Mock()
        page.url = "https://auth.uq.edu.au/idp/module.php/core/loginuserpass.php"
        browser = portal.Window(page)
        username, password, submit = AsyncMock(), AsyncMock(), AsyncMock()
        browser.controls = {
            "name": (username, "text"),
            "secret": (password, "password"),
            "go": (submit, "submit"),
        }
        await browser.act({
            "kind": "submit",
            "id": "go",
            "fields": {"name": "s1234567", "secret": "test-only"},
        })
        username.fill.assert_awaited_once_with("s1234567", timeout=2000)
        password.fill.assert_awaited_once_with("test-only", timeout=2000)
        submit.click.assert_awaited_once_with(timeout=2000)
        with pytest.raises(MiniError, match="Invalid sign-in"):
            await browser.act({"kind": "submit", "id": "go", "fields": {"unknown": "x"}})
        assert "test-only" not in str(vars(browser))

    asyncio.run(check())


def test_form_frame() -> None:
    import asyncio

    async def check() -> None:
        page = Mock()
        page.url = "https://auth.uq.edu.au/idp/module.php/core/loginuserpass.php"
        page.is_closed.return_value = False
        page.context.pages = [page]
        page.frames = [page.main_frame]
        page.main_frame.url = page.url
        page.main_frame.evaluate = AsyncMock(
            return_value=[
                {"id": "name", "type": "text", "x": 0, "y": 0, "form": True},
                {"id": "secret", "type": "password", "x": 0, "y": 0, "form": True},
                {"id": "go", "type": "submit", "x": 0, "y": 0, "form": True},
                {"id": "nav", "type": "button", "x": 0, "y": 0, "form": False},
            ]
        )
        page.viewport_size = {"width": 760, "height": 760}
        page.title = AsyncMock(return_value="UQ Authenticate")
        page.locator.return_value.all_inner_texts = AsyncMock(return_value=[])
        page.screenshot = AsyncMock()
        frame = await portal.Window(page).view()
        assert frame["mode"] == "form" and frame["image"] == ""
        assert [item["id"] for item in frame["controls"]] == ["name", "secret", "go"]
        page.screenshot.assert_not_awaited()

    asyncio.run(check())


def test_asset_caching(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-12345678.js").write_text("export {}")
    (tmp_path / "index.html").write_text("<main>Minis</main>")
    with TestClient(create(frontend=tmp_path), base_url="http://127.0.0.1:8765") as connection:
        client = cast(httpx.Client, connection)
        asset = client.get("/assets/app-12345678.js")
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert client.get("/").headers["cache-control"] == "no-store"
        assert client.get("/api/session").headers["cache-control"] == "no-store"
        assert client.get("/assets/missing-12345678.js").headers["cache-control"] == "no-store"


def test_session_confirmation() -> None:
    attributes = (
        "Session Information\n"
        "You have successfully signed into The UQ Authenticate system. "
        "Here you can see some of the attributes that are attached to your session.\n"
        "Your attributes\nUser ID:s1234567\nMail:s1234567@student.uq.edu.au"
    )
    assert portal.account(portal.PORTAL, attributes, False) == "s1234567@student.uq.edu.au"


@pytest.mark.parametrize(
    "url,attributes,logout,expected",
    [
        (portal.PORTAL, "mail A@Student.UQ.edu.au", True, "a@student.uq.edu.au"),
        (portal.PORTAL, "mail a@uq.edu.au", False, ""),
        (portal.PORTAL, "mail a@uq.edu.au.evil.test", True, ""),
        (portal.PORTAL, "mail a@example.com", True, ""),
        (portal.PORTAL.replace("auth.uq.edu.au", "evil.test"), "mail a@uq.edu.au", True, ""),
        (portal.PORTAL.replace("https:", "http:"), "mail a@uq.edu.au", True, ""),
        (
            portal.PORTAL.replace("authenticate.php", "loginuserpass.php"),
            "mail a@uq.edu.au",
            True,
            "",
        ),
        (portal.PORTAL, "a@uq.edu.au" + "x" * 65536, True, ""),
    ],
)
def test_portal_identity_requires_a_protected_uq_page(
    url: str, attributes: str, logout: bool, expected: str
) -> None:
    assert portal.account(url, attributes, logout) == expected


@pytest.fixture
def portal_window(monkeypatch: pytest.MonkeyPatch) -> Mock:
    browser = Mock()
    browser.user = AsyncMock(return_value="")
    browser.view = AsyncMock(return_value={"image": "frame", "controls": []})
    browser.act = AsyncMock()
    browser.closed = False

    @asynccontextmanager
    async def window() -> AsyncGenerator[Mock]:
        try:
            yield browser
        finally:
            browser.closed = True

    monkeypatch.setattr(portal, "window", window)
    return browser


@pytest.mark.parametrize("path", ["event", "agent", "auth"])
def test_uni_workflows_fail_closed_without_a_session(tmp_path: Path, path: str) -> None:
    with cast(
        httpx.Client,
        TestClient(create(state=tmp_path / "plan.json"), base_url="http://127.0.0.1:8765"),
    ) as client:
        assert client.get(f"/api/minis/{path}").status_code == 401
        assert (
            client.post(
                f"/api/minis/{path}", json={}, headers={"Origin": "http://127.0.0.1:8765"}
            ).status_code
            == 401
        )
        assert client.get("/api/plan").status_code == 200
        assert client.get("/api/session").json()["user"] == ""


def test_portal_access_cannot_be_claimed_by_a_callback(tmp_path: Path) -> None:
    app = create(state=tmp_path / "plan.json")
    with TestClient(app, base_url="http://127.0.0.1:8765") as connection:
        client = cast(httpx.Client, connection)
        assert client.get("/api/session").json()["configured"]
        assert client.get("/api/session/callback?user=a@uq.edu.au").status_code == 404
        response = client.post(
            "/api/session/login",
            json={"user": "a@uq.edu.au"},
            headers={"Origin": "http://127.0.0.1:8765"},
        )
        assert response.status_code == 200 and not app.state.identity.sessions
        assert response.json() == {"user": "", "window": "/api/session/window"}
        assert client.get("/api/minis/event").status_code == 401


def test_verified_session_is_opaque_expires_and_logs_out(
    tmp_path: Path,
    portal_window: Mock,
) -> None:
    app = create(state=tmp_path / "plan.json")
    auth = Identity()
    app.state.identity = auth

    def signed_in(_: dict[str, Any]) -> None:
        portal_window.user.return_value = "a@student.uq.edu.au"

    portal_window.act.side_effect = signed_in
    with TestClient(app, base_url="http://127.0.0.1:8765") as connection:
        client = cast(httpx.Client, connection)
        response = client.post(
            "/api/session/login", json={}, headers={"Origin": "http://127.0.0.1:8765"}
        )
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "a@student" not in cookie
        with connection.websocket_connect(
            "ws://127.0.0.1:8765/api/session/window", headers={"Origin": "http://127.0.0.1:8765"}
        ) as window:
            assert window.receive_json()["image"] == "frame"
            assert client.get("/api/session").json()["user"] == ""
            window.send_json({"kind": "click", "id": "login"})
            assert window.receive_json()["user"] == "a@student.uq.edu.au"
        assert portal_window.closed
        assert client.get("/api/session").json()["user"] == "a@student.uq.edu.au"
        assert client.get("/api/minis/event").status_code == 200
        client.post("/api/session/logout", json={}, headers={"Origin": "http://127.0.0.1:8765"})
        assert client.get("/api/minis/event").status_code == 401
        auth.sessions["expired"] = (monotonic() - 1, "a@student.uq.edu.au")
        client.cookies.set("minis_session", "expired")
        assert client.get("/api/minis/event").status_code == 401


@pytest.mark.parametrize(
    "origin,reserve", [("https://evil.test", True), ("http://127.0.0.1:8765", False)]
)
def test_window_origin_and_cookie(
    tmp_path: Path,
    portal_window: Mock,
    origin: str,
    reserve: bool,
) -> None:
    from starlette.websockets import WebSocketDisconnect

    with TestClient(
        create(state=tmp_path / "plan.json"), base_url="http://127.0.0.1:8765"
    ) as connection:
        client = cast(httpx.Client, connection)
        if reserve:
            client.post("/api/session/login", json={}, headers={"Origin": "http://127.0.0.1:8765"})
        with (
            pytest.raises(WebSocketDisconnect),
            connection.websocket_connect(
                "ws://127.0.0.1:8765/api/session/window", headers={"Origin": origin}
            ),
        ):
            pass
        portal_window.user.assert_not_called()


@pytest.mark.parametrize("invalid", [False, True])
def test_cancellation_and_invalid_input_release_the_portal(
    tmp_path: Path,
    portal_window: Mock,
    invalid: bool,
) -> None:
    from starlette.websockets import WebSocketDisconnect

    app = create(state=tmp_path / "plan.json")
    with TestClient(app, base_url="http://127.0.0.1:8765") as connection:
        client = cast(httpx.Client, connection)
        client.post("/api/session/login", json={}, headers={"Origin": "http://127.0.0.1:8765"})
        with connection.websocket_connect(
            "ws://127.0.0.1:8765/api/session/window", headers={"Origin": "http://127.0.0.1:8765"}
        ) as window:
            window.receive_json()
            if invalid:
                window.send_text("x" * 8193)
                assert "too large" in window.receive_json()["error"]
        assert portal_window.closed and not app.state.identity.sessions
        with (
            pytest.raises(WebSocketDisconnect),
            connection.websocket_connect(
                "ws://127.0.0.1:8765/api/session/window",
                headers={"Origin": "http://127.0.0.1:8765"},
            ),
        ):
            pass
        from uq_minis.app.session import VERIFY

        assert VERIFY.acquire(blocking=False)
        VERIFY.release()


def test_upstream_work_is_bounded_without_a_queue(tmp_path: Path) -> None:
    app = create(state=tmp_path / "plan.json")
    auth = app.state.identity
    assert auth.enter() and auth.enter() and not auth.enter()
    auth.busy = 0
    auth.calls.extend([monotonic()] * 30)
    with cast(httpx.Client, TestClient(app, base_url="http://127.0.0.1:8765")) as client:
        response = client.get("/api/course?code=CSSE1001")
        assert response.status_code == 429 and response.headers["Retry-After"] == "60"
        assert client.get("/api/research").status_code == 200
        assert client.get("/api/minis/timey").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/catalogues",
        "/api/minis/scrappy",
        "/api/minis/clubby",
        "/api/research/feedback",
        "/api/research/refresh",
        "/api/research/catalogue",
        "/api/sync",
        "/api/discord",
        "/api/social",
    ],
)
def test_bulk_requests_keep_guest_budget(tmp_path: Path, path: str) -> None:
    app = create(state=tmp_path / "plan.json")
    app.state.identity.calls.extend([monotonic()] * 30)
    with cast(
        httpx.Client,
        TestClient(app, base_url="http://127.0.0.1:8765"),
    ) as client:
        response = client.post(
            path, json={"kind": "courses"}, headers={"Origin": "http://127.0.0.1:8765"}
        )
        assert response.status_code == 429 and response.headers["Retry-After"] == "60"
