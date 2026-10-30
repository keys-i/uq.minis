import csv
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from uq_minis import cli
from uq_minis.core.common import MiniError, write_csv
from uq_minis.core.web import fetch, trusted
from uq_minis.minis.clubby import directory, events


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch):
    original = httpx.Client

    def install(respond: Callable[[httpx.Request], httpx.Response]):
        calls: list[httpx.Request] = []

        def read(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return respond(request)

        def client(**kwargs: Any) -> httpx.Client:
            return original(transport=httpx.MockTransport(read), **kwargs)

        monkeypatch.setattr(httpx, "Client", client)
        return calls

    return install


@pytest.fixture
def event() -> dict[str, Any]:
    return {
        "id": "200",
        "guild_id": "100",
        "name": "Games night",
        "scheduled_start_time": "2026-10-20T18:00:00+10:00",
        "scheduled_end_time": None,
        "status": 1,
        "entity_metadata": {"location": "St Lucia"},
        "description": "Bring a game, or join ours",
    }


def test_import_and_search(tmp_path: Path, runner: CliRunner) -> None:
    source, details, output = (tmp_path / name for name in ("old.csv", "details.csv", "clubs.csv"))
    write_csv(
        source,
        ("Name", "Link"),
        [{"Name": "Gamers’ Club", "Link": "https://uqu.com.au/clubs-and-societies/gamers/"}],
    )
    write_csv(
        details,
        ("Name", "Interests", "Description", "Website"),
        [
            {
                "Name": "gamers' club",
                "Interests": "Gaming",
                "Description": "Play, learn\nand make friends",
                "Website": "No content found",
            }
        ],
    )
    result = runner.invoke(
        cli.app, ["clubby", "import", str(source), "--details", str(details), "-o", str(output)]
    )
    assert result.exit_code == 0, result.output
    rows = directory.load(output)
    assert len(rows) == 1 and rows[0]["description"] == "Play, learn\nand make friends"
    assert rows[0]["directory_url"].endswith("/gamers/") and rows[0]["website"] == ""
    result = runner.invoke(cli.app, ["clubby", "list", str(output), "--query", "FRIENDS"])
    assert result.exit_code == 0 and "gamers' club" in result.output
    assert directory.search(output, query="missing") == ([], 0)
    assert directory.search(output, offset=1)[0] == []
    with pytest.raises(MiniError, match="different output"):
        directory.import_csv(source, source)


@pytest.mark.parametrize(
    "text", ["Name,Name\nA,B\n", "Name,Link\nA\n", "Name\nA,B\n", 'Name\n"unfinished']
)
def test_bad_csv(tmp_path: Path, text: str) -> None:
    source = tmp_path / "bad.csv"
    source.write_text(text)
    with pytest.raises(MiniError):
        directory.load(source)


def test_club_pages(tmp_path: Path, transport: Any, runner: CliRunner) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qs

        query = json.loads(parse_qs(request.content.decode())["details"][0])
        offset = query["offset"]
        return httpx.Response(
            200,
            json={
                "success": True,
                "selectedUniversityId": "12",
                "totalItemCount": 3,
                "results": [
                    {"title": f"Club {index}", "destination": f"/?s={index + 1}"}
                    for index in range(offset, min(3, offset + 2))
                ],
            },
        )

    calls = transport(respond)
    output = tmp_path / "clubs.csv"
    result = runner.invoke(cli.app, ["clubby", "refresh", "-o", str(output)])
    assert result.exit_code == 0, result.output
    assert len(calls) == 2 and len(directory.load(output)) == 3
    assert len({request.headers.get("host") for request in calls}) == 1


def test_public_events_retain_external_social_links(transport: Any) -> None:
    urls = [
        "/?eid=1",
        "https://clubs.getqpay.com/?eid=2",
        "https://www.facebook.com/events/3/",
        "https://www.instagram.com/p/4/",
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "selectedUniversityId": "12",
                "totalItemCount": len(urls),
                "results": [{"title": "Event", "destination": url} for url in urls],
            },
        )

    transport(respond)
    assert [item["destination"] for item in directory.records("events")] == urls


@pytest.mark.parametrize("failure", ["denied", "loop", "changed", "foreign", "json", "empty"])
def test_club_failure_keeps_output(tmp_path: Path, transport: Any, failure: str) -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2 and failure == "denied":
            return httpx.Response(429)
        if failure == "json":
            return httpx.Response(200, text="not json")
        return httpx.Response(
            200,
            json={
                "success": True,
                "selectedUniversityId": "12",
                "totalItemCount": 3 if calls == 2 and failure == "changed" else 2,
                "results": []
                if failure == "empty"
                else [
                    {
                        "title": "Club",
                        "destination": "https://evil.example/" if failure == "foreign" else "/?s=1",
                    }
                ],
            },
        )

    transport(respond)
    output = tmp_path / "clubs.csv"
    output.write_text("previous export")
    with pytest.raises(MiniError):
        directory.refresh(output)
    assert output.read_text() == "previous export"
    assert not list(tmp_path.glob(".clubs.csv.*"))


def test_events_offline(tmp_path: Path, event: dict[str, Any], runner: CliRunner) -> None:
    source, output = tmp_path / "events.json", tmp_path / "events.csv"
    later = {**event, "id": "201", "scheduled_start_time": "2026-10-21T00:00:00Z"}
    source.write_text(json.dumps([later, event, event]))
    result = runner.invoke(cli.app, ["clubby", "events", "--json", str(source), "-o", str(output)])
    assert result.exit_code == 0, result.output
    with output.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["event_id"] for row in rows] == ["200", "201"]
    assert rows[0]["start"] == "2026-10-20T08:00:00+00:00"
    assert rows[0]["description"] == event["description"]
    assert rows[0]["url"] == "https://discord.com/events/100/200"


def test_events_live(
    tmp_path: Path, event: dict[str, Any], transport: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bot test-token"
        assert request.method == "GET"
        guild = request.url.path.split("/")[-2]
        return httpx.Response(200, json=[{**event, "guild_id": guild}])

    calls = transport(respond)
    output = tmp_path / "events.csv"
    assert events.export(output, guilds=["100", "101", "100"]) == 2
    assert len(calls) == 2 and "test-token" not in output.read_text()


def test_event_failure_keeps_output(
    tmp_path: Path, transport: Any, monkeypatch: pytest.MonkeyPatch, event: dict[str, Any]
) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    def respond(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(403)
            if "/101/" in request.url.path
            else httpx.Response(200, json=[event])
        )

    transport(respond)
    output = tmp_path / "events.csv"
    output.write_text("previous export")
    with pytest.raises(MiniError, match="403"):
        events.export(output, guilds=["100", "101"])
    assert output.read_text() == "previous export"


@pytest.mark.parametrize(
    "change",
    [
        {"id": "../secret"},
        {"guild_id": "0"},
        {"name": ""},
        {"status": True},
        {"description": ["unexpected"]},
        {"scheduled_start_time": "2026-10-20T08:00:00"},
        {"scheduled_end_time": "2020-01-01T00:00:00Z"},
        {"entity_metadata": ["unexpected"]},
    ],
)
def test_bad_events(event: dict[str, Any], change: dict[str, Any]) -> None:
    with pytest.raises(MiniError):
        events.parse(json.dumps([{**event, **change}]))


def test_event_validation(
    tmp_path: Path, event: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(MiniError, match="different guild"):
        events.parse(json.dumps([event]), guild="101")
    with pytest.raises(MiniError, match="array"):
        events.parse("{}")
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    with pytest.raises(MiniError, match="DISCORD_BOT_TOKEN"):
        events.export(tmp_path / "events.csv", guilds=["100"])
    assert events.parse("[]") == []


@pytest.mark.parametrize(
    "url",
    [
        "http://good.example/a",
        "https://good.example.evil/a",
        "https://me@good.example/a",
        "https://good.example:444/a",
        "https://[invalid/a",
    ],
)
def test_trust_boundary(url: str) -> None:
    with pytest.raises(MiniError):
        trusted(url, ("good.example",))


def test_redirect_and_size(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://evil.example/"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(MiniError, match="HTTPS"):
            fetch("https://good.example/", client=client, hosts=("good.example",))
    assert calls == ["https://good.example/"]
    monkeypatch.setattr("uq_minis.core.web.LIMIT", 4)
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"12345"))
    ) as client:
        with pytest.raises(MiniError, match="limit"):
            fetch("https://good.example/", client=client, hosts=("good.example",))


def test_publication_failure(tmp_path: Path) -> None:
    output = tmp_path / "data.csv"
    output.write_text("old")
    broken = Mock(side_effect=OSError("disk full"))
    with pytest.raises(OSError):
        write_csv(output, ("name",), ({"name": broken()} for _ in range(1)))
    assert output.read_text() == "old" and list(tmp_path.iterdir()) == [output]


def test_directory_populates_and_preserves_saved_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "clubs.csv"

    def publish(path: Path) -> None:
        write_csv(
            path,
            directory.FIELDS,
            [
                {"name": "Film club", "directory_url": "https://campus.hellorubric.com/?s=1"},
            ],
        )

    refresh = Mock(side_effect=publish)
    enrich = Mock(side_effect=MiniError("Details temporarily unavailable"))
    monkeypatch.setattr(directory, "refresh", refresh)
    monkeypatch.setattr(directory, "enrich", enrich)
    assert directory.ensure(output) == ""
    assert len(directory.load(output)) == 1
    assert directory.ensure(output) == ""
    assert refresh.call_count == 1
    before = output.read_bytes()
    os.utime(output, (0, 0))
    refresh.side_effect = MiniError("Directory temporarily unavailable")
    assert "unavailable" in directory.ensure(output)
    assert output.read_bytes() == before
    assert not list(tmp_path.glob(".cache-*"))
    enrich.assert_not_called()


def test_public_profile_is_listed_validated_and_cached(tmp_path: Path, transport: Any) -> None:
    output = tmp_path / "clubs.csv"
    url = "https://campus.hellorubric.com/?s=2409"
    write_csv(output, directory.FIELDS, [{"name": "Film club", "directory_url": url}])

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "societyid": 2409,
                "description": "<p>Watch &amp; discuss films</p>",
                "sections": [
                    {
                        "array": [
                            {
                                "eventid": 1,
                                "upcoming": 1,
                                "title": "Movie night",
                                "destination": "/?eid=1",
                            },
                            {"eventid": 2, "upcoming": 0, "title": "Past event"},
                        ]
                    }
                ],
            },
        )

    calls = transport(respond)
    with pytest.raises(MiniError, match="saved union directory"):
        directory.profile(output, "https://evil.example/?s=2409")
    assert not calls
    result = directory.profile(output, url)
    assert "Watch & discuss films" in result["club"]["description"]
    assert [event["url"] for event in result["events"]] == ["https://campus.hellorubric.com/?eid=1"]
    assert directory.profile(output, url) == result
    assert len(calls) == 1


@pytest.mark.parametrize("sections", [None, {}, [None], [{"array": {}}], [{"array": [None]}]])
def test_malformed_club_profile_is_not_published(
    tmp_path: Path, transport: Any, sections: Any
) -> None:
    output = tmp_path / "clubs.csv"
    url = "https://campus.hellorubric.com/?s=1"
    write_csv(output, directory.FIELDS, [{"name": "Club", "directory_url": url}])

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "societyid": 1,
                "sections": sections,
            },
        )

    transport(respond)
    with pytest.raises(MiniError, match="invalid"):
        directory.profile(output, url)
    assert not list((tmp_path / "cache").glob("*/profile.json"))


def test_description_encoding(tmp_path: Path) -> None:
    output = tmp_path / "clubs.csv"
    write_csv(
        output,
        directory.FIELDS,
        [{"name": "Film", "description": "Watch &amp; discuss&lt;br/&gt;<b>films</b> together"}],
    )
    row = directory.load(output)[0]
    assert row["description"] == "Watch & discuss films together"
    assert directory.search(output, query="discuss films")[1] == 1
