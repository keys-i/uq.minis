import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from uq_minis import cli
from uq_minis.core.common import MiniError
from uq_minis.minis.clubby import social
from uq_minis.minis.planny import sources


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    original = httpx.Client
    monkeypatch.chdir(tmp_path)
    for provider in social.PROVIDERS:
        monkeypatch.setenv(provider.upper() + "_ACCESS_TOKEN", "club-read-secret")
    monkeypatch.setenv("META_API_VERSION", "v24.0")
    monkeypatch.setenv("LINKEDIN_VERSION", "202610")

    def install(response: httpx.Response) -> list[httpx.Request]:
        calls: list[httpx.Request] = []

        def read(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return response

        def client(**kwargs: Any) -> httpx.Client:
            return original(transport=httpx.MockTransport(read), **kwargs)

        monkeypatch.setattr(httpx, "Client", client)
        return calls

    return install


@pytest.mark.parametrize(
    "provider,payload,path,link",
    [
        (
            "facebook",
            {
                "data": [
                    {
                        "id": "123_456",
                        "message": "Movie night\nBring a snack",
                        "permalink_url": "https://www.facebook.com/123/posts/456/",
                    }
                ]
            },
            "/v24.0/123/posts",
            "https://www.facebook.com/123/posts/456/",
        ),
        (
            "instagram",
            {
                "data": [
                    {
                        "id": "456",
                        "caption": "Movie night\nBring a snack",
                        "permalink": "https://www.instagram.com/p/example/",
                    }
                ]
            },
            "/v24.0/123/media",
            "https://www.instagram.com/p/example/",
        ),
        (
            "linkedin",
            {
                "elements": [
                    {
                        "id": "urn:li:share:456",
                        "author": "urn:li:organization:123",
                        "lifecycleState": "PUBLISHED",
                        "commentary": "Movie night\nBring a snack",
                    }
                ]
            },
            "/rest/posts",
            "https://www.linkedin.com/feed/update/urn:li:share:456/",
        ),
    ],
)
def test_authorised_posts_share_import_format(
    transport: Callable[..., Any], provider: str, payload: Any, path: str, link: str
) -> None:
    calls = transport(httpx.Response(200, json=payload))
    rows = social.collect(provider, "123", club="Film club")
    assert len(calls) == 1 and calls[0].method == "GET"
    assert calls[0].url.path == path
    assert calls[0].headers["Authorization"] == "Bearer club-read-secret"
    assert "club-read-secret" not in str(calls[0].url) + json.dumps(rows)
    assert rows[0]["title"] == "Movie night" and rows[0]["url"] == link
    assert rows[0]["club"] == "Film club" and rows[0]["start"] == rows[0]["end"] == ""
    imported = sources.social(rows)
    assert imported == sources.social(json.dumps(rows))
    assert imported[0]["notes"] == "Movie night\nBring a snack"
    if provider == "linkedin":
        assert calls[0].url.params["author"] == "urn:li:organization:123"
        assert calls[0].headers["LinkedIn-Version"] == "202610"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401),
        httpx.Response(403),
        httpx.Response(429),
        httpx.Response(200, text="not JSON"),
        httpx.Response(200, json={"error": {"message": "club-read-secret"}}),
        httpx.Response(200, json={"data": [None]}),
        httpx.Response(200, json={"data": [{}] * 101}),
        httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "123_456",
                        "permalink_url": "https://club-read-secret@www.facebook.com/post",
                    }
                ]
            },
        ),
        httpx.Response(
            200,
            json={"data": [{"id": "987_456", "permalink_url": "https://www.facebook.com/post"}]},
        ),
    ],
)
def test_failure_preserves_export(
    transport: Callable[..., Any], tmp_path: Path, response: httpx.Response
) -> None:
    transport(response)
    output = tmp_path / "posts.json"
    output.write_text("previous reviewed data")
    with pytest.raises(MiniError) as error:
        social.export(output, "facebook", "123")
    assert "club-read-secret" not in str(error.value)
    assert output.read_text() == "previous reviewed data"


@pytest.mark.parametrize(
    "provider,account,key,value",
    [
        ("unknown", "123", "FACEBOOK_ACCESS_TOKEN", "secret"),
        ("facebook", "../123", "FACEBOOK_ACCESS_TOKEN", "secret"),
        ("facebook", "123", "FACEBOOK_ACCESS_TOKEN", ""),
        ("facebook", "123", "FACEBOOK_ACCESS_TOKEN", "header\ninjection"),
        ("instagram", "123", "META_API_VERSION", "../../unsafe"),
        ("linkedin", "123", "LINKEDIN_VERSION", "202613"),
    ],
)
def test_invalid_configuration_never_fetches(
    transport: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    account: str,
    key: str,
    value: str,
) -> None:
    calls = transport(httpx.Response(200, json={"data": []}))
    monkeypatch.setenv(key, value)
    with pytest.raises(MiniError):
        social.collect(provider, account)
    assert not calls


def test_cli_export_and_empty_feed(
    transport: Callable[..., Any], runner: CliRunner, tmp_path: Path
) -> None:
    transport(httpx.Response(200, json={"data": []}))
    output = tmp_path / "posts.json"
    result = runner.invoke(
        cli.app,
        ["clubby", "posts", "--provider", "instagram", "--account", "123", "-o", str(output)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text()) == []
    if os.name == "posix":
        assert output.stat().st_mode & 0o777 == 0o600


def test_linkedin_author_and_drafts(transport: Callable[..., Any]) -> None:
    payload = {
        "id": "urn:li:share:456",
        "author": "urn:li:organization:123",
        "lifecycleState": "DRAFT",
    }
    transport(httpx.Response(200, json={"elements": [payload]}))
    assert social.collect("linkedin", "123") == []
    payload["author"] = "urn:li:organization:999"
    transport(httpx.Response(200, json={"elements": [payload]}))
    with pytest.raises(MiniError, match="different organisation"):
        social.collect("linkedin", "123")
