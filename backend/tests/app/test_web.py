import json
import os
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from uq_minis import app, web
from uq_minis.core.common import MiniError


def test_activation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "a" * 64
    (tmp_path / "identity").write_text(
        json.dumps({"account": "person@uq.edu.au", "secret": secret})
    )
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.setenv("MINIS_ORIGIN", "")
    create, run = Mock(return_value="application"), Mock()
    monkeypatch.setattr(app, "create", create)
    monkeypatch.setattr(uvicorn, "run", run)
    web.run()
    assert create.call_args.kwargs["delegate"] == ("person@uq.edu.au", secret)
    assert run.call_args.args == ("application",)
    assert run.call_args.kwargs["fd"] == 3
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    with pytest.raises(MiniError, match="port"):
        web.run(80)
    assert run.call_count == 1


def test_hosted_observability_is_bounded_and_private(capsys: pytest.CaptureFixture[str]) -> None:
    application = app.create(origin="https://uni.keysi.dev")
    with TestClient(application, base_url="https://uni.keysi.dev") as connection:
        client = cast(httpx.Client, connection)
        health = client.get("/api/health", headers={"X-Request-ID": "bad"})
        assert health.json() == {"status": "ok", "service": "uq-minis"}
        assert health.headers["X-Request-ID"] != "bad"
        assert "style-src-elem 'self'" in health.headers["Content-Security-Policy"]
        assert "style-src-attr 'unsafe-inline'" in health.headers["Content-Security-Policy"]
        assert "'unsafe-eval'" not in health.headers["Content-Security-Policy"]
        assert health.headers["Permissions-Policy"].startswith("camera=()")
        assert health.headers["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"
        correlated = client.get("/api/health", headers={"X-Request-ID": "request-1234"})
        assert correlated.headers["X-Request-ID"] == "request-1234"
        assert client.get("/download/do-not-log-this-key").status_code == 401
        metrics = client.get("/internal/metrics")
        assert metrics.headers["Cache-Control"] == "no-store"
        assert "uq_minis_http_requests_total 4" in metrics.text
        assert "uq_minis_semantic_cache_hits_total 0" in metrics.text
        assert "uq_minis_youtube_oauth_failures_total 0" in metrics.text
        assert "request_id" not in metrics.text and "path=" not in metrics.text
    output = capsys.readouterr().out
    events = [
        json.loads(line)
        for line in output.splitlines()
        if line.startswith('{"event":"http_request"')
    ]
    assert events
    assert any(event["path"] == "/download/{key}" for event in events)
    assert "do-not-log-this-key" not in output
    assert set(events[-1]) == {
        "event",
        "request_id",
        "method",
        "path",
        "status",
        "duration_ms",
    }


def test_frontend_serves_known_mini_deep_links_only(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<main>UQ minis</main>")
    application = app.create(frontend=tmp_path)
    with TestClient(application, base_url="http://127.0.0.1:8765") as connection:
        client = cast(httpx.Client, connection)
        assert client.get("/planny").text == "<main>UQ minis</main>"
        assert client.get("/timey").headers["content-type"].startswith("text/html")
        assert client.get("/unknown-mini").status_code == 404
