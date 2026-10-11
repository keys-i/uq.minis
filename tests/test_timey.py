import json
import math
import os
import subprocess
import threading
from array import array
from contextlib import nullcontext
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock

import httpx
import pytest

from uq_minis import cli
from uq_minis.cli import timey as wizard
from uq_minis.core import cache, terminal
from uq_minis.core.common import MiniError
from uq_minis.minis import timey
from uq_minis.minis.timey import cache as media_cache
from uq_minis.minis.timey import preview, style, video, youtube

try:
    from PIL import Image, ImageChops, ImageStat
except ImportError:
    Image = ImageChops = ImageStat = None


class TestSearch:
    def test_results(self, videos):
        factory, client = videos
        client.extract_info.return_value["entries"] += [
            {"id": "abcdefghijk", "title": "Duplicate"},
            {"id": "bad/url", "title": "Untrusted ID"},
            {"id": "zyxwvutsrqp", "is_live": True},
            {"id": "12345678901", "title": "\x1b[31mForest\nwalk", "duration": float("inf")},
            None,
        ]
        results = video.search(" forest ")
        assert len(results) == 2 and results[0]["length"] == "01:23"
        assert results[1]["length"] == "duration unavailable" and "\x1b" not in results[1]["title"]
        client.extract_info.assert_called_once_with("ytsearch5:forest", download=False)
        assert factory.call_args.args[0]["extract_flat"]
        assert all(
            result["url"].startswith("https://www.youtube.com/watch?v=") for result in results
        )

    @pytest.mark.parametrize("query", ["", "x" * 201])
    def test_query(self, videos, query):
        with pytest.raises(MiniError, match="200"):
            video.search(query)
        videos[0].assert_not_called()

    @pytest.mark.parametrize("failure", ["unavailable", "network", "malformed", "empty"])
    def test_failure(self, videos, monkeypatch, failure):
        _, client = videos
        if failure == "unavailable":
            monkeypatch.setattr(video, "YoutubeDL", None)
        elif failure == "network":
            client.extract_info.side_effect = video.DownloadError("Offline")
        else:
            client.extract_info.return_value = [] if failure == "malformed" else None
        if failure == "empty":
            assert video.search("forest") == []
        else:
            with pytest.raises(MiniError):
                video.search("forest")

    @pytest.mark.parametrize(
        "answers",
        [
            "forest\nhttps://www.youtube.com/watch?v=abcdefghijk\n",
            "forest\nback\n\nhttps://www.youtube.com/watch?v=abcdefghijk\n",
        ],
    )
    def test_choose(self, videos, thumbnails, runner, answers):
        app = terminal.application()
        result = []

        @app.command()
        def run():
            result.append(wizard._media("Choose a video"))

        invoked = runner.invoke(app, [], input=answers)
        assert invoked.exit_code == 0, invoked.output
        assert result == ["https://www.youtube.com/watch?v=abcdefghijk"]
        assert "A quiet forest · 01:23" in invoked.output

    def test_path(self, videos, runner):
        app = terminal.application()

        @app.command()
        def run():
            assert wizard._media("Choose a video") == "https://youtu.be/abcdefghijk"

        result = runner.invoke(app, [], input="~/missing-folder\nhttps://youtu.be/abcdefghijk\n")
        assert result.exit_code == 0, result.output
        videos[0].assert_not_called()


class TestPreview:
    @pytest.mark.parametrize(
        "field,answers,expected",
        [
            ("position", "top-left\n", "top-left"),
            ("accent", "#6FE9EF\n", "#6FE9EF"),
            ("accent", "bad\n#FF0000\nn\n#FFD34D\n", "#FFD34D"),
        ],
        ids=["placement", "palette", "review-colour"],
    )
    def test_choices(self, field, answers, expected, runner):
        app = terminal.application()
        picked = []

        @app.command()
        def run():
            studio = wizard._Studio(timey.Timer())
            choices = (
                {value: value for value in video.POSITIONS}
                if field == "position"
                else {"#6FE9EF": "Blue", "#FFD34D": "Yellow"}
            )
            picked.append(studio.choose(field, "Choose", choices, free=field == "accent"))
            assert getattr(studio.timer, field) == picked[-1]

        result = runner.invoke(app, [], input=answers)
        assert result.exit_code == 0, result.output
        assert picked == [expected]

    @pytest.mark.parametrize(
        "answer,source",
        [
            ("Cinzel\ny\n", "https://fonts.google.com/specimen/Cinzel"),
            ("Space Mono\nn\nbungee\n", "https://fonts.google.com/specimen/Space+Mono"),
            (
                "https://fonts.google.com/specimen/Cinzel\ny\n",
                "https://fonts.google.com/specimen/Cinzel",
            ),
            ("missing.ttf\nbungee\n", None),
            ("spook\nCreepster\ny\n", "https://fonts.google.com/specimen/Creepster"),
            ("ariel\nArimo\ny\n", "https://fonts.google.com/specimen/Arimo"),
            ("Ciznel\nCinzel\ny\n", "https://fonts.google.com/specimen/Cinzel"),
            ("random nonsense\nback\nbungee\n", None),
            ("open sans\ny\n", "https://fonts.google.com/specimen/Open+Sans"),
            ("noto sans devanagari\ny\n", "https://fonts.google.com/specimen/Noto+Sans+Devanagari"),
        ],
        ids=[
            "family",
            "reject",
            "link",
            "missing-file",
            "mood",
            "ariel",
            "typo",
            "refine",
            "open-sans",
            "full-list",
        ],
    )
    def test_font_review(self, answer, source, runner, monkeypatch, fontlist):
        font = str(video.ASSETS / "timey/fonts/bungee.ttf")
        resolve = []
        monkeypatch.setattr(
            wizard, "resolve_font", lambda value, *args, **kwargs: (resolve.append(value), font)[1]
        )
        app = terminal.application()

        @app.command()
        def run():
            assert wizard._Studio(timey.Timer()).font("") == font

        result = runner.invoke(app, [], input=answer)
        assert result.exit_code == 0, result.output
        assert resolve == ([source] if source else [])

    def test_font_failure(self, runner, monkeypatch, fontlist):
        requests = []

        def fail(value, *args, **kwargs):
            requests.append(value)
            raise MiniError("Google Fonts is offline")

        monkeypatch.setattr(wizard, "resolve_font", fail)
        app = terminal.application()

        @app.command()
        def run():
            studio = wizard._Studio(timey.Timer())
            assert studio.font("") == ""
            assert studio.timer.font == ""

        result = runner.invoke(app, [], input="spook\nCreepster\nrandom words\ntheme\n")
        assert result.exit_code == 0, result.output
        assert "Google Fonts is offline" in result.output
        assert requests == ["https://fonts.google.com/specimen/Creepster"]

    @pytest.mark.parametrize("timer", [None, timey.Timer(start_gap=5)])
    def test_frame(self, clip, timer, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        source = clip("opening.mp4", "color=c=navy:s=480x270:r=24", seconds=1)
        result = preview.frame(source, timer)
        assert "▀" in result.picture.plain
        assert not list(tmp_path.glob(".timey-preview-*"))

    @pytest.mark.parametrize("state", ["image", "fallback", "oversized", "broken", "offline"])
    def test_thumbnail(self, videos, thumbnails, state):
        if state == "fallback":
            type(thumbnails).status_code = PropertyMock(side_effect=[404, 200])
        elif state == "oversized":
            thumbnails.iter_bytes.return_value = [b"x" * (1024 * 1024 + 1)]
        elif state == "broken":
            thumbnails.iter_bytes.return_value = [b"not an image"]
        elif state == "offline":
            thumbnails.raise_for_status.side_effect = httpx.ConnectError("Offline")
        result = preview.thumbnail(video.search("forest")[0])
        assert "01:23" in result.description
        assert ("▀" in result.picture.plain) is (state in {"image", "fallback"})
        if state in {"image", "fallback"}:
            assert len(result.picture.plain.splitlines()[0]) == 40
            assert (
                preview.httpx.stream.call_args_list[-1]
                .args[1]
                .endswith("hqdefault.jpg" if state == "fallback" else "sddefault.jpg")
            )
        else:
            assert "Thumbnail unavailable" in result.picture.plain

    @pytest.mark.parametrize(
        "field,values",
        [
            ("style", list(video.STYLES)),
            ("position", video.POSITIONS),
            ("accent", ["", "#8FDA53", "#6FE9EF"]),
        ],
    )
    def test_samples(self, field, values):
        samples = wizard._Studio(timey.Timer()).samples(field, values)
        assert len({sample.picture.spans.__repr__() for sample in samples.values()}) == len(values)
        assert all(len(sample.picture.plain.splitlines()) <= 14 for sample in samples.values())

    @pytest.mark.parametrize("name", ["bungee", "Bungee", "Press Start 2P", "Skranji"])
    def test_fonts(self, runner, name, monkeypatch, fontlist):
        monkeypatch.setattr(
            wizard, "resolve_font", lambda *args, **kwargs: pytest.fail("Downloaded")
        )
        app = terminal.application()
        paths = []

        @app.command()
        def run():
            studio = wizard._Studio(timey.Timer())
            paths.append(studio.font(""))

        result = runner.invoke(app, [], input=f"{name}\n")
        assert result.exit_code == 0, result.output
        assert Path(paths[0]).is_file() and Path(paths[0]).stem == name.casefold().replace(" ", "")


class TestTimer:
    @pytest.mark.parametrize(
        "settings",
        [
            {"seconds": 0},
            {"seconds": 86401},
            {"seconds": True},
            {"start_gap": -1},
            {"end_gap": 3601},
            {"accent": "red"},
            {"label": "bad\nlabel"},
            {"size": float("nan")},
            {"size": 3.1},
            {"size": 10**999},
            {"loop_blend": float("inf")},
            {"loop_blend": -0.1},
        ],
        ids=lambda settings: next(iter(settings)),
    )
    def test_invalid(self, settings):
        with pytest.raises(MiniError):
            timey.Timer(**settings)

    def test_defaults(self):
        assert timey.Timer(seconds=3, start_gap=2, end_gap=4).total == 9
        assert timey.clock(0, hours=True) == "00:00:00"
        assert timey.clock(3661) == "01:01:01"
        assert timey.Timer().position == "centre"
        assert timey.Timer().size == 2.4 and timey.Timer().label == ""
        assert timey.placement(timey.Timer(), 1920, 1080)[2] == pytest.approx(
            timey.placement(timey.Timer(size=1.4), 1920, 1080)[2] * (2.4 / 1.4)
        )

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("600", 600),
            ("10m", 600),
            ("25:00", 1500),
            ("1:02:03", 3723),
            ("1h 30m", 5400),
            ("0s", 0),
            ("", None),
            ("1:60", None),
            ("-10", None),
            ("1.5m", None),
            ("10 days", None),
            ("2m 1h", None),
        ],
        ids=[
            "raw",
            "minutes",
            "clock",
            "hours",
            "units",
            "zero",
            "empty",
            "seconds",
            "negative",
            "fraction",
            "unit",
            "order",
        ],
    )
    def test_duration(self, value, expected):
        with pytest.raises(MiniError) if expected is None else nullcontext():
            assert timey.duration(value) == expected


class TestVideo:
    @pytest.mark.parametrize(
        "source,valid",
        [
            ("https://youtu.be/abcdefghijk?list=playlist", True),
            ("https://www.youtube.com/watch?v=abcdefghijk&list=playlist", True),
            ("https://m.youtube.com/shorts/abcdefghijk", True),
            ("https://youtube.com.evil.test/watch?v=abcdefghijk", False),
            ("https://evil@youtube.com/watch?v=abcdefghijk", False),
            ("file:///etc/passwd", False),
            ("https://youtube.com/playlist?list=x", False),
            ("https://youtu.be/not-an-id", False),
            ("https://[bad", False),
        ],
        ids=[
            "short",
            "watch",
            "mobile",
            "domain",
            "userinfo",
            "scheme",
            "playlist",
            "identity",
            "malformed",
        ],
    )
    def test_url(self, source, valid):
        with nullcontext() if valid else pytest.raises(MiniError):
            assert timey.youtube_url(source) == "https://www.youtube.com/watch?v=abcdefghijk"

    def test_download(self, tmp_path, monkeypatch):
        source = tmp_path / "minecraft.mp4"
        source.write_bytes(b"local")
        assert timey.download(str(source), tmp_path) == (source, "minecraft")
        options = {}

        class Downloader:
            def __init__(self, config):
                options.update(config)
                self.params = config

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def extract_info(self, url, download, process):
                assert (
                    url == "https://www.youtube.com/watch?v=abcdefghijk"
                    and not download
                    and not process
                )
                return {"title": "Minecraft gameplay", "duration": 20}

            def process_ie_result(self, info, download):
                assert download
                (tmp_path / "source.mp4").write_bytes(b"download")
                return info

        monkeypatch.setattr(video, "YoutubeDL", Downloader)
        monkeypatch.setattr(video, "DownloadError", RuntimeError)
        path, title = timey.download(
            "https://youtu.be/abcdefghijk?tracking=" + "x" * 600, tmp_path, seconds=12, height=720
        )
        assert path.name == "source.mp4" and title == "Minecraft gameplay"
        assert options["noplaylist"] and "height<=720" in options["format"]
        assert options["match_filter"]({"is_live": True})
        assert options["download_ranges"]({"duration": 20}, None)[0]["end_time"] == 12
        assert options["download_ranges"]({"duration": 5}, None)[0]["end_time"] == 5

    def test_cache(self, tmp_path, monkeypatch):
        root = tmp_path / "cache"
        calls, updates = [], []

        class Downloader:
            def __init__(self, options):
                self.params = options

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def extract_info(self, url, download, process):
                calls.append(url)
                return {"title": "Minecraft gameplay", "duration": 20}

            def process_ie_result(self, info, download):
                assert self.params["concurrent_fragment_downloads"] == 8
                if "download_ranges" in self.params:
                    section = self.params["download_ranges"](info, self)[0]
                    assert section == {"start_time": 3, "end_time": 15}
                else:
                    assert "external_downloader_args" not in self.params
                Path(self.params["outtmpl"].replace("%(ext)s", "mp4")).write_bytes(
                    b"completed video"
                )
                return info

        monkeypatch.setattr(video, "YoutubeDL", Downloader)
        monkeypatch.setattr(cache, "ENTRIES", 2)
        url = "https://youtu.be/abcdefghijk"
        for name, seconds, start, height in (
            ("first", 12, 3, 720),
            ("repeat", 12, 3, 720),
            ("shorter", 4, 3, 720),
            ("full", 60, 0, 720),
            ("longer", 3600, 0, 720),
            ("quality", 60, 0, 1080),
        ):
            work = tmp_path / name
            work.mkdir()
            path, title = video.download(
                url + "?tracking=ignored",
                work,
                seconds=seconds,
                start=start,
                height=height,
                cache=root,
                progress=lambda done, stage: updates.append(stage),
            )
            assert path.read_bytes() == b"completed video" and title == "Minecraft gameplay"
        assert len(calls) == 3
        assert sum("cache hit" in stage for stage in updates) == 3
        assert len(list(root.glob("*/info.json"))) == 2
        assert (tmp_path / "repeat/source.mp4").read_bytes() == b"completed video"
        assert media_cache.identity(video.youtube_url(url), 720, True) != media_cache.identity(
            video.youtube_url(url), 720, False
        )
        assert media_cache.identity(video.youtube_url(url), 720, True) == media_cache.identity(
            video.youtube_url(url), 1080, True
        )
        for entry in root.glob("*/info.json"):
            entry.write_text('{"file":"../../secret"}')
        work = tmp_path / "corrupt"
        work.mkdir()
        video.download(url, work, seconds=60, height=720, cache=root)
        assert len(calls) == 4
        for start in (-1, 20, True, 2**31):
            with pytest.raises(MiniError, match="start"):
                video.download(url, work, seconds=1, start=start, cache=root)
        assert not list(root.glob(".cache-*"))

    def test_progress(self, tmp_path, monkeypatch):
        updates, measured = [], threading.Event()

        def progress(done, stage):
            updates.append((done, stage))
            if done == 0.5 and "speed" in stage:
                measured.set()

        class Downloader:
            def __init__(self, options):
                self.options = options
                self.params = options

            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def extract_info(self, url, download, process):
                assert not download and not process
                return {"title": "Music", "duration": 30}

            def process_ie_result(self, info, download):
                assert self.options["format"] == "bestaudio/best"
                self.options["download_ranges"]({"duration": 30}, None)
                arguments = self.options["external_downloader_args"]["ffmpeg_o"]
                log = Path(arguments[arguments.index("-progress") + 1])
                log.write_text(
                    "out_time_us=5000000\ntotal_size=1048576\nspeed=2.0x\nprogress=continue\n"
                )
                assert measured.wait(1)
                self.options["progress_hooks"][0](
                    {"status": "downloading", "downloaded_bytes": 10, "speed": 5, "eta": 2}
                )
                (tmp_path / "source.m4a").write_bytes(b"music")
                return {"title": "Music"}

        monkeypatch.setattr(video, "YoutubeDL", Downloader)
        path, title = video.download(
            "https://youtu.be/abcdefghijk", tmp_path, seconds=10, audio=True, progress=progress
        )
        assert path.suffix == ".m4a" and title == "Music"
        assert any(done is None and "ETA" in stage for done, stage in updates)
        assert updates[-1] == (1, "Music ready · Music")
        assert not any(thread.name == "timey-download" for thread in threading.enumerate())
        measured.clear()

        def fail(done, stage):
            if done == 0.5 and "speed" in stage:
                measured.set()
                raise RuntimeError("progress callback failed")

        with pytest.raises(RuntimeError, match="callback failed"):
            video.download(
                "https://youtu.be/abcdefghijk", tmp_path, seconds=10, audio=True, progress=fail
            )
        assert not any(thread.name == "timey-download" for thread in threading.enumerate())


class TestStyle:
    @pytest.mark.parametrize(
        "state", ["fresh", "cached", "stale", "broken", "large", "offline", "malformed"]
    )
    def test_catalogue(self, tmp_path, monkeypatch, state):
        payload = json.dumps(
            {
                "familyMetadataList": [
                    {"family": "Open Sans", "category": "Sans Serif"},
                    {"family": "Noto Sans Devanagari", "category": "Sans Serif"},
                ]
            }
        ).encode()
        path = tmp_path / "catalogue.json"
        if state in {"cached", "stale", "broken"}:
            path.write_bytes(b"bad" if state == "broken" else payload)
            if state == "stale":
                os.utime(path, (1, 1))
        requests = []

        def reply(request):
            requests.append(request.url)
            if state in {"offline", "stale"}:
                raise httpx.ConnectError("Offline")
            data = payload
            if state == "large":
                data = b"x" * (cache.SNAPSHOT + 1)
            elif state == "malformed":
                data = b'{"familyMetadataList":[{"family":"bad\\u001b","category":"Serif"}]}'
            return httpx.Response(200, content=data)

        with httpx.Client(transport=httpx.MockTransport(reply)) as client:
            monkeypatch.setattr(style.httpx, "stream", client.stream)
            if state in {"offline", "large", "malformed"}:
                with pytest.raises(MiniError, match="catalogue"):
                    style.catalogue(tmp_path)
                assert not path.exists()
            else:
                families = style.catalogue(tmp_path)
                assert "Open Sans" in style.fonts("open sans", families)
                assert "Noto Sans Devanagari" in style.fonts("devanagari", families)
                assert "Creepster" in style.fonts("spook", families)
                assert path.read_bytes() == payload
        assert len(requests) == (0 if state == "cached" else 1)
        assert not list(tmp_path.glob(".cache-*"))

    @pytest.mark.parametrize(
        "query,family",
        [("spook", "Creepster"), ("ariel", "Arimo"), ("Ciznel", "Cinzel"), ("sci fi", "Orbitron")],
    )
    def test_fonts(self, query, family):
        assert family in style.fonts(query)
        assert family in style.fonts(query)[family]
        assert not style.fonts("random nonsense")
        with pytest.raises(MiniError, match="200"):
            style.fonts("x" * 201)

    @pytest.mark.parametrize(
        "status,message", [(400, "did not recognise"), (503, "Could not download")]
    )
    def test_font_error(self, tmp_path, monkeypatch, status, message):
        if style.ImageFont is None:
            pytest.skip("Pillow is an optional Timey dependency")
        client = httpx.Client
        monkeypatch.setattr(
            style.httpx,
            "Client",
            lambda **kwargs: client(
                transport=httpx.MockTransport(lambda request: httpx.Response(status)), **kwargs
            ),
        )
        with pytest.raises(MiniError, match=message):
            style.font("https://fonts.google.com/specimen/spook", tmp_path)
        assert not list(tmp_path.iterdir())

    @pytest.mark.parametrize(
        "path,value",
        [
            (("shapes", 0, "points"), [[0, 0], [600, 20]]),
            (("shapes", 0, "points"), [[0, 0], [400, 240]]),
            (("shapes", 0, "points"), [[400, 20], [30, 10]]),
            (("shapes", 0, "points"), [[0, 0], [float("nan"), 20]]),
            (("shapes", 0, "points"), [[0, 0], [10**500, 20]]),
            (("shapes", 0, "points"), "coordinates"),
            (("shapes", 0, "colour"), "red"),
            (("shapes", 0, "kind"), "triangle"),
            (("shapes", 0, "width"), True),
            (("shapes", 2, "points"), [[0, 0], [20, 20]]),
            (("text", "timer", "point"), [0, 60]),
            (("name",), "x" * 100),
            (("name",), "bad\nname"),
            (("name",), 42),
            (("bar", "segments"), 1.5),
            (("font",), "unknown"),
            (("code",), "print('unsafe')"),
        ],
        ids=[
            "width",
            "height",
            "order",
            "nan",
            "overflow",
            "coordinates",
            "colour",
            "shape",
            "bool",
            "polygon",
            "text-position",
            "name-length",
            "control",
            "name-type",
            "segments",
            "font",
            "code",
        ],
    )
    def test_invalid(self, art, path, value):
        target = art
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(MiniError):
            style.validate(art)

    @pytest.mark.parametrize("agent", ["codex", "claude"])
    def test_generate(self, tmp_path, art, designer, agent):
        progress = []
        generated, saved = style.design(
            "Hollow Knight mask and soul vessel",
            tmp_path,
            agent=agent,
            progress=lambda done, stage: progress.append((done, stage)),
        )
        assert generated == style.read(saved) == art
        assert len(designer.calls) == 1 and progress[-1][0] == 1
        assert not list(tmp_path.glob(".design-*"))

    @pytest.mark.parametrize(
        "agent,response,status,error",
        [
            ("codex", "{broken", 0, "valid structured data"),
            ("codex", "x" * 65537, 0, "too much structured data"),
            ("codex", "{}", 1, "could not finish"),
            ("claude", "{broken", 0, "valid structured data"),
            ("claude", "{}", 0, "valid structured data"),
            ("claude", '{"is_error":true,"result":"not signed in"}', 0, "not signed in"),
        ],
        ids=["json", "size", "exit", "claude-json", "claude-fields", "claude-error"],
    )
    def test_response(self, tmp_path, designer, agent, response, status, error):
        designer.output[agent], designer.status = response, status
        original = tmp_path / "saved.json"
        original.write_text("keep")
        with pytest.raises(MiniError, match=error):
            style.design("A custom theme", tmp_path, agent=agent)
        assert original.read_text() == "keep"
        assert not list(tmp_path.glob(".design-*"))

    @pytest.mark.skipif(Image is None, reason="Pillow is an optional Timey dependency")
    @pytest.mark.parametrize("font", ["serif", "pixel"])
    def test_custom(self, art, font):
        art["font"] = font
        timer = timey.Timer(seconds=2, start_gap=0, end_gap=0, style=art["name"], artwork=art)
        assert len(list(timey.frames(timer, 1920, 1080))) == 2
        assert next(timey.frames(replace(timer, seconds=3600), 720, 1280, preview=True))

    @pytest.mark.parametrize("force", [False, True], ids=["terminate", "kill"])
    def test_timeout(self, tmp_path, monkeypatch, designer, force):
        from unittest.mock import Mock

        process = Mock(stdin=BytesIO())
        process.poll.side_effect = [None, None]
        process.wait.side_effect = [subprocess.TimeoutExpired("agent", 5), 0] if force else [0]
        monkeypatch.setattr(style.subprocess, "Popen", Mock(return_value=process))
        monkeypatch.setattr(style.time, "monotonic", Mock(side_effect=[0, 301]))
        with pytest.raises(MiniError, match="timed out"):
            style.design("A custom theme", tmp_path, agent="codex")
        process.terminate.assert_called_once()
        assert process.kill.call_count == int(force)
        assert process.stdin.closed and not list(tmp_path.glob(".design-*"))

    @pytest.mark.parametrize(
        "chosen,available,expected",
        [
            ("auto", ("codex", "claude"), "codex"),
            ("auto", ("claude",), "claude"),
            ("codex", ("codex",), "codex"),
            ("auto", (), None),
            ("claude", (), None),
            ("unknown", ("codex",), None),
        ],
        ids=["preferred", "fallback", "explicit", "none", "missing", "invalid"],
    )
    def test_designer(self, monkeypatch, chosen, available, expected):
        monkeypatch.setattr(
            style.shutil, "which", lambda name: f"/bin/{name}" if name in available else None
        )
        with nullcontext() if expected else pytest.raises(MiniError):
            assert style.designer(chosen) == expected

    @pytest.mark.parametrize(
        "title,expected", [("Temple_Run gameplay", "temple-run"), ("Unknown game", "minimal")]
    )
    def test_suggest(self, title, expected):
        assert timey.suggest_style(title) == expected

    @pytest.mark.parametrize("name", timey.STYLES)
    @pytest.mark.parametrize(
        "width,height", [(1920, 1080), (720, 1280)], ids=["landscape", "portrait"]
    )
    def test_layouts(self, name, width, height):
        if Image is None:
            pytest.skip("Pillow is an optional Timey dependency")
        timer = timey.Timer(seconds=2, start_gap=2, end_gap=2, style=name, position="bottom-centre")
        images = list(timey.frames(timer, width, height))
        assert len(images) == 6
        assert images[0] == images[1] and images[-1] == images[-2]
        assert len({images[0], images[2], images[3], images[4]}) == 4
        with Image.open(BytesIO(images[0])) as panel:
            x, y, _ = timey.placement(timer, width, height)
            assert 0 <= x < x + panel.width <= width
            assert 0 <= y < y + panel.height <= height
            assert panel.mode == "RGBA"

    @pytest.mark.skipif(Image is None, reason="Pillow is an optional Timey dependency")
    def test_preview(self):
        timer = timey.Timer(seconds=86400, start_gap=3600, end_gap=3600)
        assert len(list(timey.frames(timer, 1920, 1080, preview=True))) == 1

    def test_art(self, tmp_path, monkeypatch):
        if Image is None:
            pytest.skip("Pillow is an optional Timey dependency")
        original = video._temple_digits
        glyphs = original()
        assert set(glyphs) == set("0123456789:")
        assert len({glyph.tobytes() for glyph in glyphs.values()}) == 11
        assert all(
            glyph.mode == "RGBA" and glyph.getchannel("A").getextrema() == (0, 255)
            for glyph in glyphs.values()
        )
        calls = []

        def load(height):
            calls.append(height)
            return original(height)

        monkeypatch.setattr(video, "_temple_digits", load)
        timer = timey.Timer(seconds=2, start_gap=1, end_gap=1, style="temple-run", size=1)
        images = list(timey.frames(timer, 3840, 2160))
        assert len(images) == 4 and calls == [176]
        intro = Image.open(BytesIO(images[0]))
        live = Image.open(BytesIO(images[1]))
        left, top, right, bottom = ImageChops.difference(intro, live).convert("RGB").getbbox()
        assert 210 <= left < right <= 871 and 376 <= top < bottom <= 409
        with Image.open((video.ASSETS / "timey/art") / "plate.png") as stone:
            backdrop = stone.convert("RGBA").resize(live.size, Image.Resampling.LANCZOS)
            assert (
                ImageChops.difference(live, backdrop)
                .convert("RGB")
                .crop((400, 358, 680, 380))
                .getbbox()
                is None
            )
        _, edge = video._surface(images[0], timer, tmp_path)
        with Image.open(edge) as panel:
            alpha = panel.getchannel("A")
            assert alpha.crop((150, 175, 930, 358)).getbbox() is None
            assert alpha.crop((20, 230, 100, 310)).getbbox() is not None
            assert alpha.crop((215, 386, 865, 396)).getbbox() is None
        previews = [
            Image.open(
                BytesIO(
                    next(timey.frames(replace(timer, seconds=seconds), 3840, 2160, preview=True))
                )
            )
            for seconds in (86400, 3661)
        ]
        left, top, right, bottom = ImageChops.difference(*previews).convert("RGB").getbbox()
        assert 150 <= left < right <= 930 and 186 <= top < bottom <= 358
        custom = replace(timer, font=str((video.ASSETS / "timey/fonts") / "skranji.ttf"))
        calls.clear()
        custom_frame = next(timey.frames(custom, 3840, 2160, preview=True))
        assert not calls and custom_frame != images[1]
        next(timey.frames(replace(timer, label="Focus time"), 3840, 2160, preview=True))
        assert calls == [124]

    def test_motion(self, tmp_path, monkeypatch, clip):
        source = clip("source.mp4", "color=c=black:s=640x360:r=30:d=1")
        timer = timey.Timer(
            seconds=86400, start_gap=3600, end_gap=3600, style="temple-run", size=2, loop_blend=0
        )
        original, counts = video.frames, []

        def frames(*args, **kwargs):
            for png in original(*args, **kwargs):
                counts.append(True)
                yield png

        monkeypatch.setattr(video, "frames", frames)
        for fps, motion in ((24, True), (30, True), (60, True), (30, False)):
            counts.clear()
            output = tmp_path / f"{fps}-{motion}.mp4"
            timey.render(source, output, replace(timer, motion=motion), sample=True, fps=fps)
            assert len(counts) == 6 and timer.start_gap == 3600
            metadata = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "csv=p=0",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            assert float(metadata) == pytest.approx(6, abs=0.04)
            selected = "+".join(f"eq(n,{round(moment * fps)})" for moment in (1.75, 2.083333, 2.5))
            pixels = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(output),
                    "-vf",
                    f"select='{selected}',crop=240:42:200:173,format=rgb24",
                    "-fps_mode",
                    "passthrough",
                    "-f",
                    "rawvideo",
                    "pipe:1",
                ],
                capture_output=True,
                check=True,
            ).stdout
            chunk = 240 * 42 * 3
            assert len(pixels) == chunk * 3
            before, middle, settled = [
                Image.frombytes("RGB", (240, 42), pixels[i : i + chunk])
                for i in range(0, len(pixels), chunk)
            ]
            distance_before = sum(ImageStat.Stat(ImageChops.difference(before, middle)).mean) / 3
            distance_after = sum(ImageStat.Stat(ImageChops.difference(settled, middle)).mean) / 3
            assert distance_before > 0.5
            assert distance_after > 0.5 if motion else distance_after < 0.5
        with pytest.raises(MiniError, match="still preview or a motion sample"):
            timey.render(source, tmp_path / "invalid.png", timer, preview=True, sample=True)

    def test_font(self, tmp_path, monkeypatch):
        if Image is None:
            pytest.skip("Pillow is an optional Timey dependency")
        payload = Path(video._font("mono", 16).path).read_bytes()
        requested = []
        real_client = httpx.Client

        def response(request):
            requested.append(str(request.url))
            if request.url.host == "fonts.googleapis.com":
                return httpx.Response(
                    200, text="@font-face {src: url(https://fonts.gstatic.com/s/test/font.ttf)}"
                )
            return httpx.Response(200, content=payload)

        monkeypatch.setattr(
            style.httpx,
            "Client",
            lambda **kwargs: real_client(transport=httpx.MockTransport(response), **kwargs),
        )
        cached = style.font("https://fonts.google.com/specimen/Press+Start+2P", tmp_path)
        assert Path(cached).read_bytes() == payload
        assert "family=Press+Start+2P" in requested[0]
        assert style.font("https://fonts.google.com/specimen/Press+Start+2P", tmp_path) == cached
        assert len(requested) == 2
        for link in (
            "http://fonts.google.com/specimen/Roboto",
            "https://fonts.google.com.evil.test/specimen/Roboto",
            "https://evil@fonts.google.com/specimen/Roboto",
            "https://fonts.google.com:444/specimen/Roboto",
        ):
            with pytest.raises(MiniError, match="HTTPS Google Fonts"):
                style.font(link, tmp_path)
        monkeypatch.setattr(
            style.httpx,
            "Client",
            lambda **kwargs: real_client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        302, headers={"location": "https://evil.test/font.ttf"}
                    )
                ),
                **kwargs,
            ),
        )
        with pytest.raises(MiniError, match="HTTPS Google Fonts"):
            style.font("https://fonts.gstatic.com/s/test/redirect.ttf", tmp_path)


class TestUpload:
    def test_metadata(self, draft):
        data = draft
        assert "tags" not in youtube.validate(data)["snippet"]
        data["status"]["publishAt"] = "2099-01-01T18:00:00+10:00"
        assert youtube.validate(data)["status"]["publishAt"].endswith("+10:00")

    @pytest.mark.parametrize(
        "section,change",
        [
            ("status", {"privacyStatus": "public"}),
            ("status", {"publishAt": "2099-01-01T18:00:00"}),
            ("status", {"publishAt": "2000-01-01T18:00:00Z"}),
            ("status", {"selfDeclaredMadeForKids": "no"}),
            ("status", {"privacyStatus": []}),
            ("snippet", {"title": "<bad>"}),
            ("snippet", {"description": "🦊" * 1251}),
            ("snippet", {"tags": ["x" * 501]}),
            ("snippet", {"tags": "timer"}),
            ("snippet", {"tags": [""]}),
            ("snippet", {"categoryId": "gaming"}),
            ("snippet", {"defaultLanguage": "English"}),
            ("status", {"publishAt": "tomorrow"}),
            ("status", {"embeddable": "yes"}),
            ("status", {"license": "unknown"}),
            (None, {"notifySubscribers": "yes"}),
            (None, {"thumbnail": []}),
            (None, {"snippet": []}),
            (None, {"status": []}),
        ],
        ids=[
            "public-schedule",
            "naive-date",
            "past-date",
            "audience-type",
            "visibility-type",
            "title",
            "description-size",
            "tags-size",
            "tags-type",
            "empty-tag",
            "category",
            "language",
            "date-format",
            "embedding",
            "licence",
            "notifications",
            "thumbnail",
            "snippet-type",
            "status-type",
        ],
    )
    def test_invalid(self, draft, section, change):
        draft["status"]["publishAt"] = "2099-01-01T18:00:00+10:00"
        (draft[section] if section else draft).update(change)
        with pytest.raises(MiniError):
            youtube.validate(draft)

    @pytest.mark.parametrize(
        "content", ["{broken", "[]", " " * 65537], ids=["invalid-json", "wrong-shape", "too-large"]
    )
    def test_draft(self, tmp_path, content):
        draft = tmp_path / "details.json"
        draft.write_text(content)
        with pytest.raises(MiniError):
            youtube.read_details(draft)

    def test_chunks(self, tmp_path, monkeypatch):
        if youtube.build is None:
            pytest.skip("Google's upload client is an optional Timey dependency")
        data = {
            "snippet": {"title": "Timer"},
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": False,
            },
        }
        video, draft, token, thumbnail = (
            tmp_path / name for name in ("timer.mp4", "details.json", "token.json", "thumb.png")
        )
        video.write_bytes(b"video")
        token.write_text("{}")
        thumbnail.write_bytes(b"png")
        draft.write_text(json.dumps({**data, "thumbnail": str(thumbnail)}))
        credentials = SimpleNamespace(
            valid=True, expired=False, to_json=lambda: '{"token":"private"}'
        )
        monkeypatch.setattr(
            youtube.Credentials, "from_authorized_user_file", lambda *args: credentials
        )
        replies = iter(
            [
                (SimpleNamespace(progress=lambda: 0.5), None),
                (None, {"id": "abcdefghijk", "status": {"privacyStatus": "private"}}),
            ]
        )
        called, closed, progress = [], [], []

        def insert(**kwargs):
            called.append(kwargs)
            return SimpleNamespace(next_chunk=lambda num_retries: next(replies))

        def thumbnail_set(**kwargs):
            assert video.with_suffix(".uploaded.json").exists()
            raise youtube.HttpError(SimpleNamespace(status=403, reason="Forbidden"), b"{}")

        service = SimpleNamespace(
            videos=lambda: SimpleNamespace(insert=insert),
            thumbnails=lambda: SimpleNamespace(set=thumbnail_set),
            close=lambda: closed.append(True),
        )
        monkeypatch.setattr(youtube, "build", lambda *args, **kwargs: service)
        with pytest.raises(MiniError, match="Video uploaded to .*thumbnail failed"):
            youtube.upload(
                video,
                draft,
                tmp_path / "missing-client.json",
                token,
                progress=lambda done, stage: progress.append(done),
            )
        assert [done for done in progress if done is not None] == [0.5] and closed == [True]
        if os.name == "posix":
            assert token.stat().st_mode & 0o777 == 0o600
        assert called[0]["media_body"].resumable()
        assert called[0]["media_body"].chunksize() == 8 * 1024 * 1024
        assert not called[0]["notifySubscribers"]
        with pytest.raises(MiniError, match="upload receipt"):
            youtube.upload(video, draft, tmp_path / "missing-client.json", token)
        assert len(called) == 1


class TestWizard:
    def test_metadata(self, tmp_path, monkeypatch, runner, tty):
        context = {
            "video_title": "Unverified Minecraft gameplay title",
            "style": "temple-run",
            "countdown_seconds": 60,
            "start_gap": 5,
            "end_gap": 5,
            "total_seconds": 70,
            "source_start": 80,
            "audio": "muted",
            "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "instructions": "A focus timer for study breaks",
        }
        draft = youtube.metadata(context, tmp_path)
        assert "1 Minute Countdown Timer" in draft["title"]
        assert "00:05" in draft["description"] and "01:05" in draft["description"]
        assert context["source_url"] in draft["description"] and "Minecraft" not in draft["title"]
        assert "Audio: muted" in draft["description"]
        prompts = []

        def generate(prompt, schema, directory, **kwargs):
            prompts.append(prompt)
            assert schema == youtube.METADATA and kwargs["agent"] == "claude"
            assert kwargs["task"] == "Writing your YouTube metadata"
            return {**draft, "title": "1 Minute Countdown Timer | Temple-Inspired Stone & Gold"}

        monkeypatch.setattr(youtube, "generate", generate)
        generated = youtube.metadata(context, tmp_path, agent="claude")
        assert "Stone & Gold" in generated["title"] and "unverified data" in prompts[0]
        assert "AI search" in prompts[0] and "No keyword stuffing" in prompts[0]
        for bad in ({"seconds": "60"}, {"seconds": True}, {"seconds": 0}):
            with pytest.raises(MiniError, match="Metadata"):
                youtube.metadata({**context, "countdown_seconds": bad["seconds"]}, tmp_path)
        monkeypatch.setattr(
            youtube, "generate", lambda *args, **kwargs: {**draft, "title": "x" * 101}
        )
        with pytest.raises(MiniError, match="title"):
            youtube.metadata(context, tmp_path, agent="claude")
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "_metadata", lambda *args: generated)
        path = tmp_path / "wizard.youtube.json"
        monkeypatch.setattr(
            wizard, "prepare_upload", lambda *args, **kwargs: youtube.read_details(path)
        )
        result = runner.invoke(
            cli.app,
            [
                "timey",
                "game.mp4",
                "--upload-only",
                "--details",
                str(path),
                "--metadata",
                "--first-frame",
            ],
            input="Study timer\nEdited timer title\n\ncountdown,study\nunlisted\nn\nn\nn\nn\n",
        )
        # Exercise the draft questions without a real video or Google sign-in
        data = youtube.read_details(path)
        assert data["snippet"]["title"] == "Edited timer title"
        assert data["snippet"]["description"] == generated["description"]
        assert (
            data["thumbnail"] == "first-frame" and data["context"]["instructions"] == "Study timer"
        )
        assert result.exit_code == 0 and "Upload skipped" in result.output

    def test_tab(self, tmp_path, monkeypatch, pipe, tab, screen):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "moon timer.mp4").touch()
        styles = tmp_path / ".minis/timey/styles"
        styles.mkdir(parents=True)
        (styles / "frosted-orbit.json").touch()
        screen(live=True)
        for prefix, options, expected in (
            ("mine", {"suggestions": wizard._styles(), "paths": True}, "minecraft"),
            ("frost", {"suggestions": wizard._styles(), "paths": True}, "frosted-orbit"),
            ("cent", {"choices": video.POSITIONS}, "centre"),
            (
                "237",
                {"choices": ["03-237 · 26 seats · Seminar"], "show_choices": False, "search": True},
                "03-237 · 26 seats · Seminar",
            ),
            ("moo", {"paths": True}, "moon timer.mp4"),
        ):
            tab(prefix)
            assert terminal.ask("Choose", **options) == expected
        pipe.send_text("An icy moon with carved numbers\n")
        assert (
            terminal.ask("Style", suggestions=wizard._styles(), paths=True)
            == "An icy moon with carved numbers"
        )
        pipe.send_text("https://youtu.be/abcdefghijk\n")
        assert terminal.ask("Music", paths=True) == "https://youtu.be/abcdefghijk"
        pipe.send_text("\n")
        assert terminal.ask("Font", paths=True) == ""
        pipe.send_text("wrong\ncentre\n")
        assert terminal.ask("Position", choices=video.POSITIONS) == "centre"

    @pytest.mark.parametrize(
        "args",
        [
            [],
            ["source.mp4", "--no-input"],
            [
                "source.mp4",
                "--length",
                "1s",
                "--no-input",
                "--upload",
                "--yes",
                "--details",
                "missing.json",
            ],
            ["source.mp4", "--upload-only", "--no-input"],
            [
                "source.mp4",
                "--length",
                "1s",
                "--metadata",
                "--no-upload",
                "--no-input",
                "--details",
                "same.mp4",
                "-o",
                "same.mp4",
            ],
        ],
        ids=[
            "missing-source",
            "missing-length",
            "missing-details",
            "missing-upload-draft",
            "output-collision",
        ],
    )
    def test_guards(self, tmp_path, monkeypatch, args, runner):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli.app, ["timey", *args])
        assert result.exit_code == 2 and "Traceback" not in result.output

    def test_preview(self, tmp_path, monkeypatch, runner, tty):
        assert "--start-gap" in runner.invoke(cli.app, ["timey", "--help"]).output
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        monkeypatch.setattr(
            wizard, "download", lambda *args, **kwargs: (tmp_path / "source.mp4", "Minecraft")
        )
        renders = []

        def render(source, output, timer, **kwargs):
            renders.append((timer, kwargs))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.touch()

        monkeypatch.setattr(wizard, "render", render)
        monkeypatch.setattr(
            wizard, "upload", lambda *args, **kwargs: pytest.fail("upload was declined")
        )
        result = runner.invoke(
            cli.app,
            ["timey", "local.mp4", "-o", str(tmp_path / "timer.mp4")],
            input="3s\n0s\n2s\n4s\nauto\nn\nn\nn\ny\n",
        )
        assert result.exit_code == 0, result.output
        assert "upload the finished timer" in result.output
        assert len(renders) == 2 and renders[0][1]["sample"] and not renders[0][1]["preview"]
        assert renders[1][0] == timey.Timer(seconds=3, start_gap=2, end_gap=4, style="minecraft")
        assert not list(tmp_path.glob(".timey-*"))

    def test_upload(self, tmp_path, monkeypatch, runner, tty):
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        monkeypatch.setattr(
            wizard, "download", lambda *args, **kwargs: (tmp_path / "source.mp4", "Minecraft")
        )
        monkeypatch.setattr(
            wizard, "render", lambda source, output, timer, **kwargs: output.touch()
        )
        monkeypatch.setattr(
            wizard, "upload", lambda *args, **kwargs: pytest.fail("upload was declined")
        )
        output, details, description = (
            tmp_path / name for name in ("timer.mp4", "details.json", "description.txt")
        )
        description.write_text("Focus time\nA short timer")
        answers = [
            "n",
            "n",
            "",
            f"@{description}",
            "timer,minecraft",
            "unlisted",
            "y",
            "n",
            "youtube",
            "y",
            "gaming",
            "en-AU",
            "creativeCommon",
            "n",
            "y",
            "2099-01-01T18:00:00+10:00",
            "n",
            "y",
            "n",
        ]
        result = runner.invoke(
            cli.app,
            [
                "timey",
                "game.mp4",
                "--length",
                "3s",
                "--video-start",
                "0s",
                "--start-gap",
                "0s",
                "--end-gap",
                "0s",
                "--style",
                "auto",
                "--upload",
                "--details",
                str(details),
                "-o",
                str(output),
            ],
            input="\n".join(answers) + "\n",
        )
        assert result.exit_code == 0, result.output
        data = json.loads(details.read_text())
        assert data["snippet"]["title"] == "00:03 minecraft timer"
        assert data["snippet"]["description"] == description.read_text()
        assert data["snippet"]["defaultLanguage"] == "en-AU"
        assert data["status"]["selfDeclaredMadeForKids"] and data["notifySubscribers"]
        assert not data["status"]["embeddable"]
        assert data["status"]["privacyStatus"] == "private"
        assert data["status"]["license"] == "creativeCommon"
        assert output.exists() and "Upload skipped" in result.output

    def test_music(self, tmp_path, monkeypatch, runner, art, tty, screen):
        console, _ = screen()
        monkeypatch.setattr(wizard, "CONSOLE", console)
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        monkeypatch.setattr(wizard, "reference", lambda *args, **kwargs: None)
        monkeypatch.setattr(wizard, "choose_designer", lambda value: value)
        data, downloads, renders = art, [], []

        def download(source, directory, **kwargs):
            downloads.append((source, kwargs))
            return tmp_path / ("music.m4a" if kwargs.get("audio") else "game.mp4"), "Hollow Knight"

        monkeypatch.setattr(wizard, "download", download)
        monkeypatch.setattr(
            wizard, "design", lambda *args, **kwargs: (data, tmp_path / "custom.json")
        )
        monkeypatch.setattr(wizard, "resolve_font", lambda *args, **kwargs: "")
        monkeypatch.setattr(
            wizard,
            "render",
            lambda source, output, timer, **kwargs: (
                renders.append((timer, kwargs)),
                output.touch(),
            ),
        )
        result = runner.invoke(
            cli.app,
            [
                "timey",
                "game.mp4",
                "--length",
                "3s",
                "--start-gap",
                "0s",
                "--end-gap",
                "0s",
                "--style",
                "custom",
                "--customise",
                "-o",
                str(tmp_path / "timer.mp4"),
            ],
            input="0s\nHollow Knight mask\ncodex\n\n1.6\nn\n0.4\nFocus\n\nhttps://fonts.google.com/specimen/Cinzel\ny\nhttps://youtu.be/abcdefghijk\n0.4\ny\nn\nn\nn\ny\n",
        )
        assert result.exit_code == 0, result.output
        assert len(downloads) == 2 and downloads[1][1]["audio"]
        assert renders[-1][0].artwork == data
        assert renders[-1][1]["music_volume"] == 0.4 and renders[-1][1]["mix_audio"]
        assert renders[-1][0].size == 1.6 and not renders[-1][0].motion
        assert renders[-1][0].loop_blend == 0.4 and renders[-1][0].position == "centre"
        assert not list(tmp_path.glob(".timey-*"))


class TestRender:
    def test_timing(self, tmp_path, clip):
        source = clip(
            "source.mp4",
            "color=c=black:s=320x180:r=24,geq=lum='20+150*N/143':cb=128:cr=128",
            6,
            audio=True,
            options=("-crf", "10"),
        )
        timer = timey.Timer(seconds=7, start_gap=1, end_gap=1, motion=False, loop_blend=0)
        still, output = tmp_path / "preview.png", tmp_path / "timer.mp4"
        video.render(source, still, timer, start=3, preview=True, height=480)
        assert Image.open(still).getpixel((5, 5))[0] > 75
        video.render(source, output, timer, start=3, height=480)
        assert video._inspect(output)[2:][0]
        assert video._inspect(output)[3] == pytest.approx(9, abs=0.05)
        for second in (0.1, 2.7, 3.1, 6.1, 8.7):
            image = tmp_path / "frame.png"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    str(second),
                    "-i",
                    str(output),
                    "-frames:v",
                    "1",
                    str(image),
                ],
                check=True,
                capture_output=True,
            )
            assert Image.open(image).getpixel((5, 5))[0] > 75
        details = output.with_suffix(".youtube.json")
        details.write_text(
            json.dumps(
                {
                    "snippet": {"title": "Timestamped timer", "description": "", "tags": ["timer"]},
                    "status": {
                        "privacyStatus": "private",
                        "selfDeclaredMadeForKids": False,
                        "containsSyntheticMedia": False,
                    },
                    "thumbnail": "first-frame",
                }
            )
        )
        data = youtube.prepare(output, details)
        thumbnail = Path(data["thumbnail"])
        assert thumbnail.suffix == ".jpg" and thumbnail.stat().st_size < youtube.THUMBNAIL_LIMIT
        with Image.open(thumbnail) as actual:
            video.reference(output, tmp_path / "expected.png", size=1920)
            with Image.open(tmp_path / "expected.png") as expected:
                assert actual.size == expected.size
                assert (
                    max(
                        ImageStat.Stat(
                            ImageChops.difference(actual.convert("RGB"), expected.convert("RGB"))
                        ).mean
                    )
                    < 3
                )
        assert youtube.prepare(output, details) == data
        details.write_text(json.dumps({**data, "thumbnail": "first-frame"}))
        old = thumbnail.read_bytes()
        with pytest.raises(MiniError, match="overwrite"):
            youtube.prepare(output, details)
        assert thumbnail.read_bytes() == old
        for start in (6, -1, True):
            with pytest.raises(MiniError, match="start"):
                video.render(source, tmp_path / "invalid.mp4", timer, start=start)
        with pytest.raises(MiniError, match="overwrite the video"):
            youtube.prepare(output, output)
        video.render(
            source, tmp_path / "smooth.mp4", replace(timer, loop_blend=0.6), start=3, height=480
        )
        assert video._inspect(tmp_path / "smooth.mp4")[3] == pytest.approx(9, abs=0.05)
        assert not list(tmp_path.glob(".thumbnail-*")) and not list(tmp_path.glob(".timey-*"))

    def test_export(self, tmp_path, clip):
        source = clip(
            "source.mp4",
            "color=c=navy:s=640x360:r=30",
            audio=True,
            options=("-pix_fmt", "yuv420p"),
        )
        output, preview = tmp_path / "timer.mp4", tmp_path / "preview.png"
        timer = timey.Timer(seconds=2, start_gap=1, end_gap=1, style="minecraft")
        timey.render(source, output, timer, height=480)
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)],
            check=True,
            capture_output=True,
            text=True,
        )
        streams = json.loads(result.stdout)["streams"]
        assert {item["codec_type"] for item in streams} == {"video", "audio"}
        assert float(
            next(item for item in streams if item["codec_type"] == "video")["duration"]
        ) == pytest.approx(4, abs=0.04)
        crops = []
        x, y, scale = timey.placement(timer, 640, 360)
        for second in (0.1, 1.1, 2.1, 3.1):
            png = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-ss",
                    str(second),
                    "-i",
                    str(output),
                    "-frames:v",
                    "1",
                    "-f",
                    "image2pipe",
                    "-c:v",
                    "png",
                    "pipe:1",
                ],
                check=True,
                capture_output=True,
            ).stdout
            frame = Image.open(BytesIO(png))
            crops.append(
                frame.crop((x, y, x + round(540 * scale), y + round(234 * scale))).tobytes()
            )
        assert len(set(crops)) == 4
        timey.render(source, preview, timey.Timer(start_gap=3600), preview=True)
        assert Image.open(preview).size == (640, 360)
        old = output.read_bytes()
        with pytest.raises(MiniError, match="overwrite"):
            timey.render(source, output, timer)

        def cancel(*args):
            if args[1].startswith("Rendering the timer"):
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            timey.render(source, output, timey.Timer(seconds=120), force=True, progress=cancel)
        assert output.read_bytes() == old
        assert not list(tmp_path.glob(".timey-*"))
        assert not any(thread.name == "timey-overlay" for thread in threading.enumerate())

    def test_loop(self, tmp_path, clip):
        source = clip(
            "twenty.mp4",
            "color=c=black:s=320x180:r=24,"
            "geq=lum='40+160*N/479+20*mod(floor(X/2)+floor(Y/2),2)':cb=128:cr=128",
            20,
            options=("-crf", "10"),
        )
        timer = timey.Timer(seconds=60, start_gap=2, end_gap=1, style="glass")
        animated, still, hard = (
            tmp_path / name for name in ("animated.mp4", "still.mp4", "hard.mp4")
        )
        stages = []
        timey.render(
            source, animated, timer, fps=24, progress=lambda done, stage: stages.append(stage)
        )
        timey.render(source, still, replace(timer, motion=False), fps=24)
        timey.render(
            source, hard, replace(timer, style="minimal", motion=False, loop_blend=0), fps=24
        )
        assert any("Smoothing the loop" in stage for stage in stages)
        assert timey.probe(animated) == (320, 180, False)
        duration = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(animated),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert float(duration) == pytest.approx(63, abs=0.04)
        jumps = []
        for output in (animated, hard):
            pixels = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(output),
                    "-vf",
                    "crop=2:2:4:4,scale=1:1,format=gray",
                    "-f",
                    "rawvideo",
                    "pipe:1",
                ],
                check=True,
                capture_output=True,
            ).stdout
            assert len(pixels) == 63 * 24
            jumps.append(max(abs(a - b) for a, b in zip(pixels, pixels[1:])))
        assert jumps[0] < 30 and jumps[1] > 150

        def frame(output):
            png = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-ss",
                    "1.7",
                    "-i",
                    str(output),
                    "-frames:v",
                    "1",
                    "-f",
                    "image2pipe",
                    "-c:v",
                    "png",
                    "pipe:1",
                ],
                check=True,
                capture_output=True,
            ).stdout
            with Image.open(BytesIO(png)) as image:
                return image.convert("RGB")

        moving, quiet = frame(animated), frame(still)
        x, y, scale = timey.placement(timer, 320, 180)
        crop = quiet.crop((x + 10, y + 22, x + 18, y + 34))
        outside = quiet.crop((10, 10, 18, 22))
        assert max(ImageStat.Stat(crop).stddev) < max(ImageStat.Stat(outside).stddev) / 3
        delta = ImageChops.difference(moving, quiet)
        centre = delta.crop(
            (x + 20, y + 10, x + round(540 * scale) - 20, y + round(234 * scale) - 10)
        )
        assert max(ImageStat.Stat(centre).mean) < 2
        assert max(high for low, high in delta.getextrema()) > 10

        old = animated.read_bytes()

        def cancel(done, stage):
            if stage.startswith("Smoothing the loop"):
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            timey.render(source, animated, timer, force=True, progress=cancel)
        assert animated.read_bytes() == old and not list(tmp_path.glob(".timey-*"))

    def test_audio(self, tmp_path, clip):
        source = clip("source.mp4", "color=s=320x180:r=30", audio=True)
        music = tmp_path / "music.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:sample_rate=48000",
                "-t",
                "1",
                str(music),
            ],
            check=True,
            capture_output=True,
        )
        timer = timey.Timer(seconds=3, start_gap=0, end_gap=1)
        measured = []
        for mix, volume in ((False, 1), (True, 1), (False, 0.5)):
            output = tmp_path / f"{mix}-{volume}.mp4"
            progress = []
            video.render(
                source,
                output,
                timer,
                music=music,
                mix_audio=mix,
                music_volume=volume,
                progress=lambda done, stage: progress.append((done, stage)),
            )
            raw = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-ss",
                    "1.8",
                    "-i",
                    str(output),
                    "-t",
                    "0.4",
                    "-ar",
                    "8000",
                    "-ac",
                    "1",
                    "-f",
                    "f32le",
                    "pipe:1",
                ],
                check=True,
                capture_output=True,
            ).stdout
            samples = array("f", raw)
            energy = [
                math.hypot(
                    sum(
                        value * math.sin(2 * math.pi * frequency * index / 8000)
                        for index, value in enumerate(samples)
                    ),
                    sum(
                        value * math.cos(2 * math.pi * frequency * index / 8000)
                        for index, value in enumerate(samples)
                    ),
                )
                / len(samples)
                for frequency in (440, 880)
            ]
            measured.append(energy)
            assert any("frame " in stage and "fps" in stage for _, stage in progress)
            assert progress[-1][0] == 1
        assert measured[0][0] < measured[0][1] / 20
        assert measured[1][0] > measured[1][1] / 2
        assert measured[2][1] == pytest.approx(measured[0][1] / 2, rel=0.1)
        with pytest.raises(MiniError, match="existing file"):
            video.render(source, tmp_path / "invalid.mp4", timer, music=tmp_path / "missing.wav")
        silent = tmp_path / "silent.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(source), "-c:v", "copy", "-an", str(silent)],
            check=True,
            capture_output=True,
        )
        with pytest.raises(MiniError, match="audio stream"):
            video.render(source, tmp_path / "silent-music.mp4", timer, music=silent)
