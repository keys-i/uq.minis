import json
import os
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from uq_minis.app import connect as connection
from uq_minis.app import create
from uq_minis.core.common import MiniError
from uq_minis.minis.auth import portal
from uq_minis.minis.timey import connect
from uq_minis.minis.timey.youtube import SCOPE

ORIGIN = "http://127.0.0.1:8765"
STATE = "a" * 32


def oauth_client() -> None:
    path = Path(".config/timey/client_secret.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "web": {
                "client_id": "test.apps.googleusercontent.com",
                "client_secret": "test-only",
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [ORIGIN + connection.CALLBACK],
            }
        })
    )


class Flow:
    def __init__(self) -> None:
        self.credentials = cast(
            connection.OAuthCredentials,
            SimpleNamespace(
                refresh_token="refresh-token",
                scopes=[SCOPE],
                to_json=lambda: json.dumps({
                    "refresh_token": "refresh-token",
                    "scopes": [SCOPE],
                }),
            ),
        )
        self.response = ""

    def authorization_url(self, **values: str) -> tuple[str, str]:
        assert values == {
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={STATE}", STATE

    def fetch_token(self, **values: str) -> object:
        self.response = values["authorization_response"]
        return None


def flow_factory(
    flow: Flow,
) -> Callable[[dict[str, object], str], connection.OAuthFlow]:
    def create_flow(_config: dict[str, object], _callback: str) -> connection.OAuthFlow:
        return flow

    return create_flow


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


def test_private_download_connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    if os.name == "posix":
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


def test_public_oauth_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    oauth_client()
    flow = Flow()
    monkeypatch.setattr(connection, "_flow", flow_factory(flow))
    with cast(
        httpx.Client,
        TestClient(
            create(),
            base_url=ORIGIN,
            headers={"Origin": ORIGIN},
        ),
    ) as client:
        assert client.get("/api/timey/youtube").json() == {
            "connected": False,
            "configured": True,
        }
        started = client.post("/api/timey/youtube/start", json={})
        assert started.status_code == 200
        assert started.json()["url"].startswith("https://accounts.google.com/")
        callback = client.get(
            connection.CALLBACK + f"?state={STATE}&code=one-use",
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        assert callback.status_code == 200
        assert "YouTube connected" in callback.text
        assert flow.response == ORIGIN + connection.CALLBACK + f"?state={STATE}&code=one-use"
        assert client.get("/api/timey/youtube").json()["connected"] is True
        if os.name == "posix":
            assert connection.TOKEN.stat().st_mode & 0o077 == 0
        replay = client.get(connection.CALLBACK + f"?state={STATE}&code=replay")
        assert replay.status_code == 400
        metrics = client.get("/internal/metrics").text
        assert "uq_minis_youtube_oauth_starts_total 1" in metrics
        assert "uq_minis_youtube_oauth_completions_total 1" in metrics
        assert "uq_minis_youtube_oauth_failures_total 1" in metrics
        assert "refresh-token" not in metrics and STATE not in metrics
        assert client.post("/api/timey/youtube", json={"kind": "disconnect"}).json() == {
            "connected": False,
            "configured": True,
        }
        assert not connection.TOKEN.exists()


def test_oauth_rejects_wrong_state_and_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    oauth_client()
    monkeypatch.setattr(connection, "_flow", flow_factory(Flow()))
    with cast(
        httpx.Client,
        TestClient(create(), base_url=ORIGIN, headers={"Origin": ORIGIN}),
    ) as client:
        assert client.post("/api/timey/youtube/start", json={}).status_code == 200
        rejected = client.get(connection.CALLBACK + "?state=wrong&code=unused")
        assert rejected.status_code == 400
        assert not connection.TOKEN.exists()
        cancelled = client.get(connection.CALLBACK + f"?state={STATE}&error=access_denied")
        assert cancelled.status_code == 400
        metrics = client.get("/internal/metrics").text
        assert "uq_minis_youtube_oauth_failures_total 1" in metrics
        assert "uq_minis_youtube_oauth_cancellations_total 1" in metrics
        assert client.post("/api/timey/youtube", json=[]).status_code == 422
        assert client.post("/api/timey/youtube", content="not-json").status_code == 400


def test_hosted_oauth_telemetry_contains_no_provider_data(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    oauth_client()
    monkeypatch.setattr(connection, "_flow", flow_factory(Flow()))
    application = create(delegate=("a@uq.edu.au", "private"))
    with cast(
        httpx.Client,
        TestClient(application, base_url=ORIGIN, headers={"Origin": ORIGIN}),
    ) as client:
        client.cookies.set("minis_session", "private")
        client.post("/api/timey/youtube/start", json={})
        client.get(connection.CALLBACK + f"?state={STATE}&code=one-use")
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    oauth = [event for event in events if str(event.get("event", "")).startswith("youtube_")]
    assert oauth == [
        {"event": "youtube_oauth_started"},
        {"event": "youtube_oauth_completed"},
    ]
    assert all(set(event) == {"event"} for event in oauth)
    requests = [event for event in events if event.get("event") == "http_request"]
    assert [event["path"] for event in requests] == [
        "/api/timey/youtube/start",
        connection.CALLBACK,
    ]
    assert "refresh-token" not in json.dumps(events) and STATE not in json.dumps(events)


def test_oauth_requires_web_client_and_exact_callback() -> None:
    path = Path(".config/timey/client_secret.json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"installed": {"client_id": "desktop"}}))
    with pytest.raises(MiniError, match="Web OAuth"):
        connection._client(ORIGIN)
    oauth_client()
    with pytest.raises(MiniError, match="return address"):
        connection._client("https://uni.keysi.dev")


def test_upload_token_links_are_rejected(tmp_path: Path) -> None:
    secret = tmp_path / "private"
    secret.write_text("do not touch")
    connection.TOKEN.parent.mkdir(parents=True)
    connection.TOKEN.symlink_to(secret)
    with pytest.raises(MiniError, match="private storage"):
        connection.disconnect()
    assert secret.read_text() == "do not touch"
