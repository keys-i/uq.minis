import json
from collections.abc import Iterator
from pathlib import Path
from time import monotonic
from typing import Any, cast
from unittest.mock import Mock
from xml.etree.ElementTree import fromstring

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.fixtures import Clip
from uq_minis.app import create
from uq_minis.app.core import Workspace
from uq_minis.cli import get_app
from uq_minis.core.art import COLOURS, RESIDENTS
from uq_minis.core.common import write_csv
from uq_minis.minis import agent, auth, timey
from uq_minis.minis.event.pipeline import RunResult


@pytest.fixture
def browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[httpx.Client]:
    monkeypatch.chdir(tmp_path)
    cookies = tmp_path / "google-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setattr("uq_minis.minis.timey.connect.cookiefile", lambda: cookies)
    app = create(state=tmp_path / "plan.json", courses=tmp_path / "courses.csv")
    app.state.identity.sessions["test-session"] = (
        monotonic() + 3600,
        "student@student.uq.edu.au",
    )
    with cast(
        httpx.Client,
        TestClient(
            app,
            base_url="http://127.0.0.1:8765",
            headers={"Origin": "http://127.0.0.1:8765"},
        ),
    ) as client:
        client.cookies.set("minis_session", "test-session")
        yield client


@pytest.mark.parametrize("mini", ["scrappy", "clubby", "event", "auth", "agent", "timey"])
def test_browser_choices(browser: httpx.Client, mini: str) -> None:
    assert (mini in browser.get("/api/minis").json()) == (mini not in {"auth", "agent"})
    schema = browser.get(f"/api/minis/{mini}").json()
    assert schema["tool"] == mini and schema["fields"]


def test_workflow_destinations(
    browser: httpx.Client,
) -> None:
    names = browser.get("/api/minis").json()
    assert "buzzy" in names and "event" in names and "scrappy" in names
    assert "auth" not in names and "agent" not in names
    assert "Assessments" in names["planny"]["about"]


def test_room_wording(browser: httpx.Client) -> None:
    expected = browser.get("/api/rooms", params={"q": "St Lucia", "seats": 50})
    spoken = browser.get("/api/rooms", params={"q": "Find a room at St Lucia for 50 people"})
    assert expected.status_code == spoken.status_code == 200
    assert spoken.json() == expected.json()
    assert spoken.json()["rows"]
    assert all(row["seats"] >= 50 for row in spoken.json()["rows"])


def test_overlay_updates(browser: httpx.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO

    from PIL import Image

    download = Mock(side_effect=AssertionError("Live controls must not download media"))
    monkeypatch.setattr(timey, "download", download)
    first = browser.post("/api/timey/preview", data={"style": "minimal", "length": "10m"})
    second = browser.post("/api/timey/preview", data={"style": "minecraft", "length": "25m"})
    assert first.status_code == second.status_code == 200
    assert first.headers["Content-Type"] == "image/png"
    assert first.content != second.content
    with Image.open(BytesIO(first.content)) as picture:
        assert picture.size == (960, 540) and picture.mode == "RGBA"
        pixel = picture.getpixel((0, 0))
        assert isinstance(pixel, tuple) and pixel[3] == 0
    invalid = browser.post("/api/timey/preview", data={"length": "invalid"})
    assert invalid.status_code == 400
    zero = browser.post("/api/timey/preview", data={"length": "0s", "panel": "on"})
    assert zero.status_code == 200
    from uq_minis.minis.timey.video import Timer, frames

    expected = next(frames(Timer(seconds=1, start_gap=0, end_gap=1), 960, 540, offset=1))
    assert zero.content == expected
    panel = browser.post(
        "/api/timey/preview",
        data={
            "panel": "on",
            "size": "3",
            "overlay_width": "0.4",
            "overlay_height": "0.2",
        },
    )
    with Image.open(BytesIO(panel.content)) as picture:
        assert picture.size == (810, 351)
    changed = browser.post(
        "/api/timey/preview", data={"overlay_width": "0.4", "overlay_height": "0.2"}
    )
    with Image.open(BytesIO(changed.content)) as picture:
        box = picture.getbbox()
        assert box is not None and box[2] - box[0] <= 384 and box[3] - box[1] <= 108
    assert browser.post("/api/timey/preview", data={"overlay_height": "nan"}).status_code == 400
    assert browser.post("/api/timey/preview", data={"x": "0.4"}).status_code == 400
    assert browser.post("/api/timey/preview", data={"x": "nan", "y": "0.2"}).status_code == 400
    download.assert_not_called()


def test_browser_youtube_search_reuses_cli_search(
    browser: httpx.Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        {
            "title": "Forest",
            "length": "10:00",
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
        }
    ]
    search = Mock(return_value=rows)
    monkeypatch.setattr(timey, "search", search)
    result = browser.get("/api/timey/search", params={"query": "forest"})
    assert result.status_code == 200 and result.json()["rows"] == rows
    search.assert_called_once_with("forest", cookies=tmp_path / "google-cookies.txt")


def test_youtube_actions_require_google_without_locking_local_timey(
    browser: httpx.Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uq_minis.minis.timey import connect

    monkeypatch.setattr(connect, "cookiefile", lambda: None)
    search = Mock(side_effect=AssertionError("Search must stop before contacting YouTube"))
    monkeypatch.setattr(timey, "search", search)
    result = browser.get("/api/timey/search", params={"query": "forest"})
    assert result.status_code == 400 and "Connect Google" in result.text
    assert (
        browser.post("/api/timey/clip", data={"source": "https://youtu.be/abcdefghijk"}).status_code
        == 400
    )
    search.assert_not_called()
    assert browser.post("/api/timey/preview", data={"style": "minimal"}).status_code == 200


def test_browser_font_search_reuses_the_cli_shelf(
    browser: httpx.Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uq_minis.core.common import MiniError

    catalogue = Mock(return_value={f"Test {number}": "display" for number in range(20)})
    monkeypatch.setattr(timey, "catalogue", catalogue)
    download = Mock(side_effect=AssertionError("Search must not download font files"))
    monkeypatch.setattr(timey, "font", download)
    result = browser.get("/api/timey/fonts", params={"query": "Test 19"})
    assert result.status_code == 200
    assert result.json()["rows"][0] == {
        "name": "Test 19",
        "description": "display",
        "source": "https://fonts.google.com/specimen/Test+19",
    }
    assert result.json()["notice"] == ""
    shelf = browser.get("/api/timey/fonts").json()
    assert len(shelf["rows"]) == 12 and shelf["total"] > 12
    assert "bundled" not in browser.get("/api/timey/fonts", params={"query": "Bungee"}).text
    assert browser.get("/api/timey/fonts", params={"query": "x" * 201}).status_code == 422
    catalogue.side_effect = MiniError("Offline")
    fallback = browser.get("/api/timey/fonts", params={"query": "spooky"}).json()
    assert any(row["name"] == "Creepster" for row in fallback["rows"])
    assert "Offline font shelf" in fallback["notice"]
    assert browser.get("/api/timey/fonts", params={"query": "zzqxxzzq"}).json()["total"] == 0
    download.assert_not_called()


def test_cached_seeking(
    browser: httpx.Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"cached-video-bytes")
    prepare = Mock(return_value=(path, "Forest"))
    monkeypatch.setattr("uq_minis.minis.timey.clip.prepare", prepare)
    monkeypatch.setattr("uq_minis.minis.timey.video.probe", Mock(return_value=(960, 540, False)))
    result = browser.post(
        "/api/timey/clip", data={"source": "https://youtu.be/abcdefghijk?t=1m20s"}
    )
    assert result.status_code == 200
    data = result.json()
    assert data["url"].startswith("/download/") and data["title"] == "Forest"
    assert data["width"] == 960 and data["height"] == 540
    assert prepare.call_args.kwargs["start"] == 80
    response = browser.get(data["url"], headers={"Range": "bytes=0-5"})
    assert response.status_code == 206 and response.content == b"cached"
    assert "frame-src 'none'" in response.headers["Content-Security-Policy"]
    result = browser.post(
        "/api/timey/clip",
        data={"source": "https://youtu.be/abcdefghijk?t=80", "start": "2:00"},
    )
    assert result.status_code == 200 and prepare.call_args.kwargs["start"] == 120
    (tmp_path / "info.json").write_text('{"duration":300,"complete":true}')
    cached = browser.post("/api/timey/clip", data={"source": "https://youtu.be/abcdefghijk"})
    assert cached.status_code == 200 and cached.json()["complete"] is True


def test_complete_seeking(
    browser: httpx.Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "complete.mp4"
    path.write_bytes(b"complete-video-bytes")
    (tmp_path / "info.json").write_text('{"duration": 300}')
    prepare = Mock(return_value=(path, "Forest"))
    monkeypatch.setattr("uq_minis.minis.timey.clip.prepare", prepare)
    monkeypatch.setattr("uq_minis.minis.timey.video.probe", Mock(return_value=(960, 540, False)))
    result = browser.post(
        "/api/timey/clip",
        data={
            "source": "https://youtu.be/abcdefghijk",
            "complete": "on",
            "start": "80",
        },
    )
    assert result.status_code == 200 and result.json()["complete"] is True
    assert prepare.call_args.kwargs["start"] == 0
    assert prepare.call_args.kwargs["complete"] is True
    response = browser.get(result.json()["url"], headers={"Range": "bytes=15-19"})
    assert response.status_code == 206 and response.content == b"bytes"
    assert (
        browser.post(
            "/api/timey/clip",
            data={
                "source": "https://youtu.be/abcdefghijk",
                "complete": "on",
                "start": "300",
            },
        ).status_code
        == 400
    )
    assert (
        browser.post(
            "/api/timey/clip",
            data={
                "source": "https://youtu.be/abcdefghijk",
                "complete": "on",
                "start": "2147483648",
            },
        ).status_code
        == 400
    )
    assert browser.post("/api/timey/clip", data={"complete": "no"}).status_code == 400


def test_portrait_and_font(
    browser: httpx.Client,
) -> None:
    from io import BytesIO

    from PIL import Image

    from uq_minis.assets import ROOT

    result = browser.post(
        "/api/timey/preview",
        data={
            "width": "304",
            "height": "540",
            "font": str(ROOT / "timey/fonts/bungee.ttf"),
        },
    )
    assert result.status_code == 200
    with Image.open(BytesIO(result.content)) as picture:
        assert picture.size == (304, 540)
    assert browser.post("/api/timey/preview", data={"width": "2000"}).status_code == 400


def test_private_video_upload(browser: httpx.Client, clip: Clip) -> None:
    video = clip("local.mp4", "color=c=blue:s=160x90:r=10", 2)
    uploaded = browser.post(
        "/api/timey/source?name=Holiday.mp4",
        content=video.read_bytes() + bytes(9 * 1024**2),
    )
    assert uploaded.status_code == 200, uploaded.text
    source = uploaded.json()["source"]
    assert source.startswith("upload:") and "/" not in source
    prepared = browser.post("/api/timey/clip", data={"source": source})
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["title"] == "Holiday.mp4"
    assert prepared.json()["duration"] == pytest.approx(2, abs=0.1)
    result = browser.post(
        "/api/minis/timey", data={"source": source, "action": "preview", "length": "5s"}
    )
    assert result.status_code == 200, result.text
    assert browser.get(result.json()["downloads"][0]["url"]).headers["content-type"] == "image/png"
    assert browser.post("/api/timey/clip", data={"source": "upload:missing"}).status_code == 400


def test_invalid_video_upload(browser: httpx.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    assert browser.post("/api/timey/source", content=b"not a video").status_code == 400
    monkeypatch.setattr("uq_minis.app.timey.UPLOAD_LIMIT", 4)
    assert browser.post("/api/timey/source", content=b"12345").status_code == 413
    assert browser.post("/api/timey/source", content=iter([b"12", b"345"])).status_code == 413
    assert not list(Path(".config/timey").glob(".upload-*"))
    assert not list(Path(".config/timey/sources").glob("*/info.json"))


def test_uploaded_image_is_safe_previewable_and_renderable(
    browser: httpx.Client, tmp_path: Path
) -> None:
    from io import BytesIO

    from PIL import Image

    from uq_minis.minis.timey.video import inspect

    with Image.new("RGB", (1024, 768), "#70a070") as picture, BytesIO() as image:
        picture.save(image, format="PNG")
        uploaded = browser.post("/api/timey/source?name=Garden.png", content=image.getvalue())
    assert uploaded.status_code == 200, uploaded.text
    source = uploaded.json()["source"]
    assert source.startswith("upload:") and "/" not in source
    response = browser.post("/api/timey/clip", data={"source": source})
    assert response.status_code == 200, response.text
    backdrop = response.json()
    assert backdrop["kind"] == "image" and backdrop["title"] == "Garden.png"
    assert (backdrop["width"], backdrop["height"]) == (720, 540)
    preview = browser.get(backdrop["url"])
    assert preview.headers["content-type"] == "image/png"
    with Image.open(BytesIO(preview.content)) as thumbnail:
        assert thumbnail.size == (720, 540)
    assert (
        browser.post(
            "/api/timey/preview",
            data={"width": backdrop["width"], "height": backdrop["height"]},
        ).status_code
        == 200
    )
    result = browser.post(
        "/api/minis/timey",
        data={
            "source": source,
            "action": "sample",
            "style": "minimal",
            "length": "1s",
            "start_gap": "0",
            "end_gap": "0",
            "height": "240",
        },
    )
    assert result.status_code == 200, result.text
    output = tmp_path / "sample.mp4"
    output.write_bytes(browser.get(result.json()["downloads"][0]["url"]).content)
    assert inspect(output)[3] == pytest.approx(1, abs=0.1)
    assert (
        browser.post("/api/timey/source?name=broken.png", content=b"not an image").status_code
        == 400
    )
    assert browser.get(backdrop["url"]).status_code == 200
    assert not list(Path(".config/timey").glob(".upload-*"))


def test_official_course_outage_retains_saved_requirements(
    browser: httpx.Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uq_minis.core.common import MiniError, atomic_json
    from uq_minis.minis.planny import research

    path = tmp_path / "research.json"
    saved = {
        **research.load(path),
        "courses": [
            {
                "code": "CSSE2002",
                "name": "Software",
                "faculty": "IT",
                "requirements": {
                    "Course Code": "CSSE2002",
                    "Pre-Requisites": "CSSE1001",
                },
            }
        ],
    }
    atomic_json(path, saved, private=True)
    monkeypatch.setattr("uq_minis.app.research.course_info", Mock(side_effect=MiniError("Offline")))
    result = browser.get("/api/research/course?code=CSSE2002")
    assert result.status_code == 200
    assert result.json()["readiness"]["wording"] == "CSSE1001"
    assert result.json()["readiness"]["status"] == "missing"
    assert result.json()["official_error"] == "Offline"
    assert research.search(saved, "CSSE2002", semester="1")["total"] == 1


@pytest.mark.parametrize("mini", RESIDENTS)
def test_shared_cli_habitats(browser: httpx.Client, mini: str) -> None:
    look = browser.get("/api/habitat", params={"mini": mini}).json()
    assert look["animal"] == getattr(get_app(mini), "habitat") == RESIDENTS[mini]
    assert look["colours"]["ink"] == COLOURS["ink"]
    assert look["name"] and look["source"].startswith("https://")
    assert look["quip"] and "|" not in look["quip"]


def test_card_art_and_image_sources(browser: httpx.Client) -> None:
    response = browser.get("/api/brand/uq.png")
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert response.headers["Cache-Control"] == "private, max-age=300"
    policy = response.headers["Content-Security-Policy"]
    images = policy.split("img-src ", 1)[1].split(";", 1)[0]
    assert set(images.split()) == {
        "'self'",
        "data:",
        "blob:",
        "https://resources.getqpay.com",
        "https://resources.hellorubric.com",
        "https://i.ytimg.com",
    }
    assert browser.get("/api/minis").json()["planny"]["animal"] == RESIDENTS["planny"]


def test_habitat_art_is_bounded_and_inert(browser: httpx.Client) -> None:
    for pose in ("idle", "look", "pet"):
        response = browser.get("/api/habitat/otter.svg", params={"pose": pose})
        assert response.status_code == 200
        assert fromstring(response.text).tag == "{http://www.w3.org/2000/svg}svg"
        assert len(response.content) < 500_000
        assert "<script" not in response.text and "https://" not in response.text
        assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert browser.get("/api/habitat/unknown.svg").status_code == 400
    assert browser.get("/api/habitat/otter.svg?pose=unknown").status_code == 400


@pytest.mark.parametrize("mini", ["scrappy", "clubby", "agent", "timey"])
def test_unknown_actions(browser: httpx.Client, mini: str) -> None:
    response = browser.post(f"/api/minis/{mini}", data={"action": "unknown"})
    assert response.status_code == 400


def test_scrappy_saved_search_and_download(browser: httpx.Client, tmp_path: Path) -> None:
    write_csv(
        tmp_path / "courses.csv",
        ("course_code", "course_name", "offering_link"),
        [
            {
                "course_code": "CSSE2002",
                "course_name": "Programming",
                "offering_link": "https://programs-courses.uq.edu.au/course.html?course_code=CSSE2002",
            }
        ],
    )
    result = browser.post("/api/minis/scrappy", data={"action": "list", "query": "csse"})
    assert result.status_code == 200 and len(result.json()["rows"]) == 1
    result = browser.post(
        "/api/minis/scrappy",
        data={"action": "links", "university": "unsw"},
        files={
            "html": (
                "index.html",
                '<a href="/COMP1511/26T3/">COMP1511 Programming Fundamentals</a>',
            )
        },
    )
    assert result.status_code == 200
    url = result.json()["downloads"][0]["url"]
    assert "COMP1511" in browser.get(url).text
    assert browser.get("/download/unknown").status_code == 400


def test_clubby_import(browser: httpx.Client) -> None:
    response = browser.post(
        "/api/minis/clubby",
        data={"action": "import"},
        files={
            "source": (
                "clubs.csv",
                "Name,Link\nGames,https://uqu.com.au/clubs-and-societies/games/\n",
            )
        },
    )
    assert response.status_code == 200
    assert "Games" in browser.get(response.json()["downloads"][0]["url"]).text
    response = browser.post(
        "/api/minis/clubby",
        data={"action": "import"},
        files={"source": ("clubs.csv", "Name,Link\nBroken\n")},
    )
    assert response.status_code == 400


def test_event_previews_and_requires_submission_authority(
    browser: httpx.Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    generate = Mock(return_value=RunResult((), ()))
    monkeypatch.setattr("uq_minis.app.event.generate", generate)
    response = browser.post("/api/minis/event", data={"source": "event.toml"})
    assert response.status_code == 200 and generate.call_args.kwargs["form_action"] == "preview"
    response = browser.post("/api/minis/event", data={"source": "event.toml", "submit": "on"})
    assert response.status_code == 400 and generate.call_count == 1
    assert browser.post("/api/minis/event", data={"mode": "risk"}).status_code == 400


@pytest.mark.parametrize("action", ["watch", "poll"])
def test_mail_needs_authority(
    browser: httpx.Client, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    operation = Mock()
    monkeypatch.setattr(agent, action, operation)
    response = browser.post("/api/minis/agent", data={"action": action})
    assert response.status_code == 400
    operation.assert_not_called()


def test_auth_keeps_credentials_private(
    browser: httpx.Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = Mock(return_value={"secret": "private-token"})
    write = Mock()
    monkeypatch.setattr(auth, "capture", capture)
    monkeypatch.setattr(auth, "write_env", write)
    result = browser.post("/api/minis/auth", data={"browser": "chromium"})
    assert result.status_code == 200 and "private-token" not in result.text
    write.assert_called_once()


def test_mail_recipient(browser: httpx.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    operation = Mock()
    monkeypatch.setattr(agent, "watch", operation)
    monkeypatch.setattr(agent, "status", Mock(return_value=[]))
    response = browser.post(
        "/api/minis/agent",
        data={
            "action": "watch",
            "source": "event.toml",
            "event_id": "566",
            "recipient": "pfassist@pf.uq.edu.au",
            "confirm": "on",
        },
    )
    assert response.status_code == 200
    assert operation.call_args.kwargs["recipient"] == "pfassist@pf.uq.edu.au"


def test_timey_preview_reuses_renderer(
    browser: httpx.Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    output = tmp_path / "preview.png"
    output.write_bytes(b"preview")
    monkeypatch.setattr(timey, "require_ffmpeg", Mock())
    monkeypatch.setattr(timey, "download", Mock(return_value=(source, {})))
    render = Mock(return_value=output)
    monkeypatch.setattr(timey, "render", render)
    response = browser.post(
        "/api/minis/timey",
        data={"source": str(source), "action": "preview", "start": "5s"},
    )
    assert response.status_code == 200 and render.call_args.kwargs["start"] == 5
    assert browser.get(response.json()["image"]).content == b"preview"


def test_discord_refresh_preserves_other_sources(
    browser: httpx.Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    row: dict[str, Any] = {
        "guild_id": "100",
        "event_id": "200",
        "name": "Game night",
        "start": "2026-10-25T08:00:00Z",
        "end": "",
        "url": "https://discord.com/events/100/200",
        "description": "Bring a game",
        "location": "Campus",
        "status": "scheduled",
    }
    collect = Mock(return_value=[row])
    monkeypatch.setattr("uq_minis.app.planny.events.collect", collect)
    result = browser.post("/api/discord", json={"guilds": "100, 100"})
    assert result.status_code == 200
    collect.assert_called_once_with(guilds=["100"])
    saved = result.json()
    saved["announcements"].append({"id": "other", "title": "Other", "source": "Instagram"})
    assert browser.post("/api/plan", json=saved).status_code == 200
    collect.return_value = []
    result = browser.post("/api/discord", json={"guilds": "100"})
    assert [item["id"] for item in result.json()["announcements"]] == ["other"]


def test_downloads_and_request_limits(browser: httpx.Client, tmp_path: Path) -> None:
    workspace = Workspace(exports=tmp_path / "exports")
    file = workspace.directory() / "result.csv"
    file.write_text("complete")
    key = workspace.publish(file)["url"].rsplit("/", 1)[1]
    assert workspace.download(key) == file
    assert (
        browser.post(
            "/api/plan", content=b"x", headers={"Content-Length": str(8 * 1024**2 + 1)}
        ).status_code
        == 413
    )
    assert browser.get("/api/plan", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 400


def test_social_refresh_keeps_selections_and_other_posts(
    browser: httpx.Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        {
            "title": "Movie night",
            "source": "Instagram",
            "url": "https://www.instagram.com/p/example/",
            "notes": "Bring a snack",
        }
    ]
    collect = Mock(return_value=rows)
    monkeypatch.setattr("uq_minis.app.planny.social.collect", collect)
    data = {
        "provider": "instagram",
        "account": "123",
        "club": "Film club",
        "club_url": "https://campus.hellorubric.com/?s=456",
    }
    result = browser.post("/api/social", json=data)
    assert result.status_code == 200
    collect.assert_called_once_with("instagram", "123", club="Film club")
    saved = result.json()
    assert saved["announcements"][0]["club_url"] == data["club_url"]
    saved["announcements"][0]["saved"] = False
    saved["announcements"].append({
        "id": "other",
        "title": "Older saved post",
        "source": "Facebook",
    })
    assert browser.post("/api/plan", json=saved).status_code == 200
    rows[0]["notes"] = "Updated details"
    data["club_url"] = ""
    result = browser.post("/api/social", json=data)
    assert len(result.json()["announcements"]) == 2
    assert result.json()["announcements"][0]["notes"] == "Updated details"
    assert result.json()["announcements"][0]["saved"] is False
    assert result.json()["announcements"][0]["club_url"] == "https://campus.hellorubric.com/?s=456"
    collect.return_value = []
    assert len(browser.post("/api/social", json=data).json()["announcements"]) == 2


@pytest.mark.parametrize("remote", [False, True])
def test_timer_draft(
    browser: httpx.Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: bool
) -> None:
    source = tmp_path / "clip.mp4"
    source.touch()
    output = tmp_path / "timer.mp4"
    output.write_bytes(b"video")
    monkeypatch.setattr(timey, "require_ffmpeg", Mock())
    download = Mock(return_value=(source, "Background title"))
    monkeypatch.setattr(timey, "download", download)
    render = Mock(return_value=output)
    monkeypatch.setattr(timey, "render", render)
    from uq_minis.minis.timey import youtube

    prepare = Mock(return_value={})
    monkeypatch.setattr(youtube, "prepare", prepare)
    response = browser.post(
        "/api/minis/timey",
        data={
            "source": "https://youtu.be/abcdefghijk" if remote else str(source),
            "action": "render",
            "length": "20s",
            "size": "1.2",
            "position": "bottom-right",
            "x": "0.3",
            "y": "0.8",
            "overlay_width": "0.4",
            "overlay_height": "0.2",
            "motion": "off",
            "loop_blend": "1.5",
            "height": "720",
            "music": str(source),
            "music_volume": "0.4",
            "mix_audio": "on",
            "fps": "60",
            "use_accent": "on",
            "accent": "#abcdef",
            "metadata": "on",
            **({"audience": "children", "synthetic": "yes", "first_frame": ""} if remote else {}),
        },
    )
    assert response.status_code == 200, response.text
    timer = render.call_args.args[2]
    assert timer.size == 1.2 and timer.position == "bottom-right" and not timer.motion
    assert timer.x == 0.3 and timer.y == 0.8
    assert timer.width == 0.4 and timer.height == 0.2
    assert timer.loop_blend == 1.5 and timer.accent == "#abcdef"
    assert render.call_args.kwargs["music_volume"] == 0.4
    assert render.call_args.kwargs["mix_audio"] and render.call_args.kwargs["fps"] == 60
    assert download.call_count == 2
    details = response.json()["downloads"][-1]["url"]
    draft = browser.get(details).json()
    assert draft["status"] == {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": False,
    }
    assert draft["thumbnail"] == "first-frame"
    prepare.assert_called_once()
    assert browser.get(details).json()["context"]["source_url"] == (
        "https://www.youtube.com/watch?v=abcdefghijk" if remote else ""
    )


def test_timey_upload_is_separate_and_requires_review(
    browser: httpx.Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uq_minis.minis.timey import youtube

    upload = Mock(return_value="https://www.youtube.com/watch?v=abcdefghijk")
    monkeypatch.setattr(youtube, "upload", upload)
    fields = {"action": "upload", "source": "timer.mp4", "details": "checked.json"}
    assert browser.post("/api/minis/timey", data=fields).status_code == 400
    upload.assert_not_called()
    assert browser.post("/api/minis/timey", data={**fields, "confirm": "on"}).status_code == 200
    upload.assert_called_once()
    browser.cookies.clear()
    assert browser.post("/api/minis/timey", data={**fields, "confirm": "on"}).status_code == 401
    assert upload.call_count == 1


def test_browser_room_shortlist_and_recovery_controls(
    browser: httpx.Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert browser.get("/api/rooms", params={"q": "St Lucia", "seats": 20}).json()["rows"]
    assert browser.get("/api/rooms", params={"seats": -1}).status_code == 400
    retry = Mock()
    monkeypatch.setattr(agent, "status", Mock(return_value=[]))
    response = browser.post("/api/minis/agent", data={"action": "retry-send", "event_id": "566"})
    assert response.status_code == 400
    monkeypatch.setattr(agent, "retry_send", retry)
    response = browser.post(
        "/api/minis/agent",
        data={
            "action": "retry-send",
            "event_id": "566",
            "confirm_not_sent": "on",
            "state_dir": "private-mail",
        },
    )
    assert response.status_code == 200
    retry.assert_called_once_with("566", confirm_not_sent=True, state_dir=Path("private-mail"))


def test_new_event_creates_editable_draft_and_never_submits(
    browser: httpx.Client, event_toml: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tomllib

    from uq_minis.app.event import DETAILS

    original = tomllib.loads(event_toml.read_text())
    fields = {
        f"{section}.{key}": str(original[section][key])
        for section, (_, keys) in DETAILS.items()
        for key in keys
    }
    room = browser.get("/api/rooms", params={"q": "St Lucia", "seats": 20}).json()["rows"][0]
    fields.update(
        input="new",
        venue=f"{room['campus']}|{room['room']}",
        mode="risk",
        capacity="21-50",
        attendance="20",
    )
    generate = Mock(return_value=RunResult((), ()))
    monkeypatch.setattr("uq_minis.app.event.generate", generate)
    response = browser.post("/api/minis/event", data=fields)
    assert response.status_code == 200, response.text
    saved = browser.get(response.json()["downloads"][0]["url"]).text
    draft = tomllib.loads(saved)
    assert draft["event"]["title"] == "Sample Event"
    assert draft["event"]["room"] == room["room"]
    assert draft["form"]["values"]["terms"] == ""
    assert generate.call_args.kwargs["form_action"] == "preview"
    assert (
        browser.post(
            "/api/minis/event", data={**fields, "submit": "on", "confirm": "on"}
        ).status_code
        == 400
    )
    assert generate.call_count == 1


def test_music_export(browser: httpx.Client, clip: Clip, tmp_path: Path) -> None:
    from uq_minis.minis.timey import clip as clips
    from uq_minis.minis.timey.video import inspect

    video = clip("backdrop.mp4", "color=c=blue:s=160x90:r=10", 2, audio=True)
    track, _ = clips.prepare(str(video), tmp_path / "tracks", audio=True, complete=True)
    uploaded = browser.post("/api/timey/source?name=Music.m4a&audio=on", content=track.read_bytes())
    assert uploaded.status_code == 200, uploaded.text
    music = uploaded.json()["source"]
    ready = browser.post("/api/timey/clip", data={"source": music, "audio": "on", "complete": "on"})
    assert ready.status_code == 200 and ready.json()["kind"] == "audio", ready.text
    assert ready.json()["title"] == "Music.m4a"
    assert ready.json()["duration"] == pytest.approx(2, abs=0.1)
    assert browser.get(ready.json()["url"]).headers["content-type"] == "audio/mp4"
    result = browser.post(
        "/api/minis/timey",
        data={
            "source": str(video),
            "music": music,
            "action": "render",
            "length": "2s",
            "start_gap": "0s",
            "end_gap": "0s",
            "fps": "24",
            "style": "minimal",
        },
    )
    assert result.status_code == 200, result.text
    output = tmp_path / "export.mp4"
    output.write_bytes(browser.get(result.json()["downloads"][0]["url"]).content)
    assert inspect(output)[2] is True
    assert inspect(output)[3] == pytest.approx(2, abs=0.1)
    assert browser.post("/api/timey/clip", data={"source": music, "audio": "no"}).status_code == 400
    assert (
        browser.post(
            "/api/minis/timey",
            data={
                "source": str(video),
                "music": "upload:missing",
                "length": "1s",
                "action": "render",
            },
        ).status_code
        == 400
    )
    silent = clip("silent.mp4", "color=c=blue:s=160x90:r=10", 1)
    assert (
        browser.post(
            "/api/timey/source?name=silent.mp4&audio=on", content=silent.read_bytes()
        ).status_code
        == 400
    )


def test_animated_preview(browser: httpx.Client) -> None:
    from io import BytesIO
    from threading import Event

    from PIL import Image
    from starlette.datastructures import FormData

    from uq_minis.app.timey import _overlay
    from uq_minis.core.common import MiniError

    result = browser.post(
        "/api/timey/preview",
        data={
            "style": "minecraft",
            "length": "30s",
            "panel": "on",
            "animated": "on",
            "size": "3",
        },
    )
    assert result.status_code == 200 and result.headers["content-type"] == "image/webp"
    with Image.open(BytesIO(result.content)) as image:
        assert getattr(image, "n_frames", 1) <= 40 and image.size == (540, 234)
        assert image.convert("RGBA").getpixel((0, 0)) == (0, 0, 0, 0)
        first = image.convert("RGBA").tobytes()
        image.seek(15)
        assert image.convert("RGBA").tobytes() != first
    cancelled = Event()
    cancelled.set()
    with pytest.raises(MiniError, match="cancelled"):
        _overlay(FormData({"panel": "on", "animated": "on"}), cancelled)
    assert _overlay(FormData({"panel": "on"})).startswith(b"\x89PNG")
    assert browser.post("/api/timey/preview", data={"animated": "on"}).status_code == 400


@pytest.mark.parametrize("format", ["HEIF", "GIF", "WEBP", "TIFF"])
def test_picture_formats(browser: httpx.Client, tmp_path: Path, format: str) -> None:
    from importlib import import_module

    from PIL import Image

    from uq_minis.minis.timey.video import inspect

    import_module("pillow_heif.HeifImagePlugin")
    suffix = {"HEIF": "heic", "TIFF": "tiff"}.get(format, format.lower())
    picture = tmp_path / f"background.{suffix}"
    with (
        Image.new("RGB", (32, 24), "red") as first,
        Image.new("RGB", (32, 24), "blue") as second,
    ):
        if format in {"GIF", "WEBP"}:
            first.save(
                picture,
                format=format,
                save_all=True,
                append_images=[second],
                duration=120,
                loop=0,
            )
        else:
            first.save(picture, format=format)
    result = browser.post(
        f"/api/timey/source?name=background.{suffix}", content=picture.read_bytes()
    )
    assert result.status_code == 200, result.text
    ready = browser.post("/api/timey/clip", data={"source": result.json()["source"]})
    assert ready.status_code == 200, ready.text
    assert ready.json()["kind"] == ("video" if format in {"GIF", "WEBP"} else "image")
    if format in {"GIF", "WEBP"}:
        clip = browser.get(ready.json()["url"])
        output = tmp_path / "decoded.mp4"
        output.write_bytes(clip.content)
        assert inspect(output)[3] == pytest.approx(0.24, abs=0.08)


@pytest.mark.parametrize("suffix", ["ttf", "woff2"])
def test_uploaded_font(browser: httpx.Client, suffix: str) -> None:
    from uq_minis.assets import ROOT

    source = (
        ROOT / "timey/fonts/bungee.ttf"
        if suffix == "ttf"
        else Path(__file__).resolve().parents[3] / "frontend/assets/fonts/comic.woff2"
    )
    result = browser.post(
        f"/api/timey/source?name=letters.{suffix}&font=on", content=source.read_bytes()
    )
    assert result.status_code == 200, result.text
    preview = browser.post(
        "/api/timey/preview",
        data={"length": "10s", "font": result.json()["source"], "panel": "on"},
    )
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/png", (
        preview.text
    )
    invalid = browser.post(f"/api/timey/source?name=broken.{suffix}&font=on", content=b"not a font")
    assert invalid.status_code == 400 and "font" in invalid.text


def test_timey_quality(browser: httpx.Client, clip: Clip, tmp_path: Path) -> None:
    import subprocess

    movie = clip("quality.mp4", "color=c=blue:s=640x360:r=30", 1)
    source = browser.post("/api/timey/source?name=quality.mp4", content=movie.read_bytes()).json()[
        "source"
    ]
    for height, fps in [(240, 24), (360, 60)]:
        reply = browser.post(
            "/api/timey/clip",
            data={
                "source": source,
                "height": str(height),
                "fps": str(fps),
                "complete": "on",
            },
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["height"] == height
        output = tmp_path / f"check-{height}.mp4"
        output.write_bytes(browser.get(reply.json()["url"]).content)
        data = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=avg_frame_rate",
                    "-of",
                    "json",
                    str(output),
                ],
                text=True,
            )
        )
        assert data["streams"][0]["avg_frame_rate"] == f"{fps}/1"
    assert (
        browser.post("/api/timey/clip", data={"source": source, "height": "900"}).status_code == 400
    )


def test_timey_save_and_publish(
    browser: httpx.Client, clip: Clip, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uq_minis.minis.timey import youtube

    movie = clip("finished.mp4", "color=c=blue:s=160x90:r=10", 1)
    source = browser.post("/api/timey/source?name=finished.mp4", content=movie.read_bytes()).json()[
        "source"
    ]
    token = "/download/" + source.removeprefix("upload:")
    assert browser.post("/api/timey/save", data={"source": token}).status_code == 200
    assert browser.post("/api/timey/save", data={"source": "../../private.mp4"}).status_code == 400
    prepare, upload = Mock(), Mock(return_value="https://youtu.be/abcdefghijk")
    monkeypatch.setattr(youtube, "prepare", prepare)
    monkeypatch.setattr(youtube, "upload", upload)
    fields = {
        "source": token,
        "title": "Study time",
        "description": "A quiet countdown",
        "destination": "youtube",
        "confirm": "on",
    }
    assert browser.post("/api/timey/publish", data={**fields, "confirm": ""}).status_code == 400
    assert browser.post("/api/timey/publish", data=fields).status_code == 200
    details = json.loads(upload.call_args.args[1].read_text())
    assert details["snippet"]["title"] == "Study time"
    assert (
        details["status"]["containsSyntheticMedia"] is False
        and details["thumbnail"] == "first-frame"
    )
    browser.cookies.clear()
    assert browser.post("/api/timey/save", data={"source": token}).status_code == 401
    assert browser.post("/api/timey/publish", data=fields).status_code == 401
    upload.assert_called_once()


def test_media_registry_recovery(tmp_path: Path) -> None:
    first = Workspace(exports=tmp_path / "exports")
    movie = tmp_path / "movie.mp4"
    movie.write_bytes(b"preserved draft media")
    token = first.publish(movie)["url"].removeprefix("/download/")
    recovered = Workspace(exports=tmp_path / "exports")
    assert recovered.download(token) == movie.resolve()
    movie.unlink()
    assert Workspace(exports=tmp_path / "exports").download(token) is None


def test_project_bridge(browser: httpx.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(409, json={"error": "A newer edit is available"})

    constructor = httpx.AsyncClient
    monkeypatch.setenv("KEYSI_SERVICES_URL", "http://127.0.0.1:8788")
    monkeypatch.setenv("KEYSI_MINIS_KEY", "private-test-service-key")

    def client(*, timeout: float, follow_redirects: bool) -> httpx.AsyncClient:
        return constructor(
            transport=httpx.MockTransport(reply),
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

    monkeypatch.setattr(httpx, "AsyncClient", client)
    response = browser.put("/api/timey/projects/ABCDEFGHIJKL", json={"revision": 0})
    assert response.status_code == 409 and "newer edit" in response.json()["error"]
    assert seen[0].headers["X-Keysi-User"] == "student@student.uq.edu.au"
    assert seen[0].headers["Authorization"] == "Bearer private-test-service-key"
    assert "private-test-service-key" not in response.text
    assert browser.get("/api/timey/projects/bad-code").status_code == 400
    browser.cookies.clear()
    assert browser.get("/api/timey/projects").status_code == 401
    assert len(seen) == 1


def test_upload_parts(browser: httpx.Client) -> None:
    from io import BytesIO

    from PIL import Image

    with Image.new("RGB", (20, 20), "white") as picture, BytesIO() as image:
        picture.save(image, format="PNG")
        data = image.getvalue()
    key = "a" * 32
    path = f"/api/timey/parts/{key}?name=picture.png"
    first = browser.post(path, content=data[:20])
    assert first.json() == {"pending": "on"}
    assert browser.post(path + "&offset=0", content=b"duplicate").status_code == 400
    final = browser.post(path + "&offset=20&final=on", content=data[20:])
    assert final.status_code == 200, final.text
    assert final.json()["source"].startswith("upload:")
    assert not list(Path("out/.cache/timey/parts").iterdir())
    assert browser.post("/api/timey/parts/bad", content=b"bad").status_code == 400
