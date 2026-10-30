from collections.abc import Iterator
from pathlib import Path
from threading import Semaphore
from typing import Any, cast
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from uq_minis.app import create
from uq_minis.core import translate
from uq_minis.core.common import MiniError


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    cached = translate.text
    cached.cache_clear()
    monkeypatch.setattr(translate, "_retry", 0.0)
    monkeypatch.setattr(translate, "_characters", 0)
    monkeypatch.setenv("MINIS_TRANSLATE_KEY", "private-test-key")
    monkeypatch.setenv("MINIS_TRANSLATE_REGION", "test-region")
    yield
    cached.cache_clear()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> tuple[list[httpx.Request], list[httpx.Response]]:
    calls: list[httpx.Request] = []
    responses = [httpx.Response(200, json=[{"translations": [{"text": "पाठ्यक्रम"}]}])]
    original = httpx.Client

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responses.pop(0)

    def client(**kwargs: Any) -> httpx.Client:
        return original(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    return calls, responses


def test_source_language_and_completed_cache(provider: Any) -> None:
    calls, _ = cast(tuple[list[httpx.Request], list[httpx.Response]], provider)
    assert translate.text("Course", "hi", "en") == "पाठ्यक्रम"
    assert translate.text("Course", "hi", "en") == "पाठ्यक्रम"
    assert len(calls) == 1
    assert calls[0].url.params["from"] == "en"
    assert "private-test-key" not in str(calls[0].url)
    assert translate.text("English original", "en", "en") == "English original"
    assert len(calls) == 1


@pytest.mark.parametrize("retry", ["90", "Thu, 01 Jan 1970 00:01:30 GMT"])
def test_rate_limit_waits_then_recovers(
    provider: Any, monkeypatch: pytest.MonkeyPatch, retry: str
) -> None:
    calls, responses = cast(tuple[list[httpx.Request], list[httpx.Response]], provider)
    responses.insert(0, httpx.Response(429, headers={"Retry-After": retry}))
    clock = Mock(return_value=1000.0)
    monkeypatch.setattr(translate, "monotonic", clock)
    monkeypatch.setattr(translate, "time", lambda: 0.0)
    with pytest.raises(translate.Unavailable) as failed:
        translate.text("Course", "hi", "en")
    assert failed.value.status == 429 and failed.value.retry == 90
    with pytest.raises(translate.Unavailable):
        translate.text("Another course", "hi", "en")
    assert len(calls) == 1
    clock.return_value = 1091.0
    assert translate.text("Course", "hi", "en") == "पाठ्यक्रम"
    assert len(calls) == 2


@pytest.mark.parametrize("status", [401, 403, 503])
def test_provider_recovery(provider: Any, status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    calls, responses = cast(tuple[list[httpx.Request], list[httpx.Response]], provider)
    responses.insert(0, httpx.Response(status, text="Provider internals must not reach the UI"))
    with pytest.raises(translate.Unavailable) as failed:
        translate.text("Course", "hi")
    assert failed.value.status == 503 and failed.value.retry == 60
    assert "Provider internals" not in str(failed.value)
    monkeypatch.setattr(translate, "_retry", 0.0)
    assert translate.text("Course", "hi") == "पाठ्यक्रम"
    assert len(calls) == 2


@pytest.mark.parametrize(
    "payload", [None, [], {}, [{"translations": []}], [{"translations": [{"text": " "}]}]]
)
def test_invalid_results_are_not_cached(provider: Any, payload: Any) -> None:
    calls, responses = cast(tuple[list[httpx.Request], list[httpx.Response]], provider)
    responses.insert(0, httpx.Response(200, json=payload))
    with pytest.raises(translate.Unavailable) as failed:
        translate.text("Course", "hi")
    assert failed.value.status == 502
    assert translate.text("Course", "hi") == "पाठ्यक्रम"
    assert len(calls) == 2


def test_budget_and_invalid_input_do_not_start_requests(
    provider: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, _ = cast(tuple[list[httpx.Request], list[httpx.Response]], provider)
    for original, target, source in [
        (" ", "hi", "en"),
        ("Course", "invalid", "en"),
        ("Course", "hi", "invalid"),
    ]:
        with pytest.raises(MiniError):
            translate.text(original, target, source)
    monkeypatch.setattr(translate, "_characters", 60000)
    slots = Semaphore(2)
    monkeypatch.setattr(translate, "_active", slots)
    with pytest.raises(translate.Unavailable) as failed:
        translate.text("Course", "hi")
    assert failed.value.status == 429 and failed.value.retry > 0
    assert not calls and slots.acquire(blocking=False) and slots.acquire(blocking=False)
    monkeypatch.setattr(translate, "_characters", 123)
    with pytest.raises(translate.Unavailable):
        translate.text("A request that never starts", "hi")
    assert not calls and getattr(translate, "_characters") == 123


def test_browser_sees_retry_after_without_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def busy(original: str, target: str, source: str = "auto") -> str:
        raise translate.Unavailable("Translation is resting", status=429, retry=90)

    monkeypatch.setattr(translate, "text", busy)
    with cast(
        httpx.Client,
        TestClient(create(state=tmp_path / "plan.json"), base_url="http://127.0.0.1:8765"),
    ) as client:
        status = client.get("/api/languages")
        assert status.json()["configured"] is True
        assert "private-test-key" not in status.text
        response = client.post(
            "/api/translate",
            json={"text": "Course", "target": "hi", "source": "en"},
            headers={"Origin": "http://127.0.0.1:8765"},
        )
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "90"
        assert response.json()["detail"] == "Translation is resting"


def test_unconnected_browser_fallback_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MINIS_TRANSLATE_KEY")
    with cast(
        httpx.Client,
        TestClient(create(state=tmp_path / "plan.json"), base_url="http://127.0.0.1:8765"),
    ) as client:
        assert client.get("/api/languages").json()["configured"] is False
        response = client.post(
            "/api/translate",
            json={"text": "Course", "source": "en", "target": "hi"},
            headers={"Origin": "http://127.0.0.1:8765"},
        )
        assert response.status_code == 503 and "not connected" in response.json()["detail"]
