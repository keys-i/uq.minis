"""Timey video behaviour and failure paths"""

import shutil
import threading
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from uq_minis.core import cache
from uq_minis.core.common import MiniError
from uq_minis.minis import timey
from uq_minis.minis.timey import cache as media_cache
from uq_minis.minis.timey import video


class TestVideo:
    def test_runtime(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from types import SimpleNamespace

        module = tmp_path / "__init__.py"
        node = tmp_path / "driver" / "node"
        node.parent.mkdir()
        node.touch()
        monkeypatch.setattr(shutil, "which", Mock(return_value=None))
        monkeypatch.setattr(
            video, "find_spec", Mock(return_value=SimpleNamespace(origin=str(module)))
        )
        assert video.runtimes() == {"node": {"path": str(node)}}

    def test_denial(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        downloader = Mock()
        downloader.__enter__ = Mock(return_value=downloader)
        downloader.__exit__ = Mock(return_value=False)
        downloader.extract_info.side_effect = video.DownloadError(
            "Sign in to confirm you’re not a bot. Use --cookies-from-browser"
        )
        monkeypatch.setattr(video, "YoutubeDL", Mock(return_value=downloader))
        with pytest.raises(MiniError, match="YouTube is blocking downloads") as caught:
            video.download("https://youtu.be/abcdefghijk", tmp_path)
        assert "cookies" not in str(caught.value)

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
    def test_url(self, source: str, valid: bool) -> None:
        with nullcontext() if valid else pytest.raises(MiniError):
            assert timey.youtube_url(source) == "https://www.youtube.com/watch?v=abcdefghijk"

    def test_download(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        source = tmp_path / "minecraft.mp4"
        source.write_bytes(b"local")
        assert timey.download(str(source), tmp_path) == (source, "minecraft")
        options: dict[str, Any] = {}

        class Downloader:
            def __init__(self, config: dict[str, Any]):
                options.update(config)
                self.params = config

            def __enter__(self):
                return self

            def __exit__(self, *_: Any):
                pass

            def extract_info(self, url: str, download: bool, process: Mock):
                assert (
                    url == "https://www.youtube.com/watch?v=abcdefghijk"
                    and not download
                    and not process
                )
                return {"title": "Minecraft gameplay", "duration": 20}

            def process_ie_result(self, info: dict[str, Any], download: bool):
                assert download
                (tmp_path / "source.mp4").write_bytes(b"download")
                return info

        monkeypatch.setattr(video, "YoutubeDL", Downloader)
        monkeypatch.setattr(video, "DownloadError", RuntimeError)
        path, title = timey.download(
            "https://youtu.be/abcdefghijk?tracking=" + "x" * 600,
            tmp_path,
            seconds=12,
            height=720,
        )
        assert path.name == "source.mp4" and title == "Minecraft gameplay"
        assert options["noplaylist"] and "height<=720" in options["format"]
        assert options["match_filter"]({"is_live": True})
        assert options["download_ranges"]({"duration": 20}, None)[0]["end_time"] == 12
        assert options["download_ranges"]({"duration": 5}, None)[0]["end_time"] == 5

    def test_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = tmp_path / "cache"
        calls: list[str] = []
        updates: list[str] = []

        class Downloader:
            def __init__(self, options: dict[str, Any]):
                self.params = options

            def __enter__(self):
                return self

            def __exit__(self, *_: Any):
                pass

            def extract_info(self, url: str, download: bool, process: Mock):
                calls.append(url)
                return {"title": "Minecraft gameplay", "duration": 20}

            def process_ie_result(self, info: dict[str, Any], download: bool):
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

    def test_progress(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        updates: list[tuple[float | None, str]] = []
        measured = threading.Event()

        def progress(done: float | None, stage: str):
            updates.append((done, stage))
            if done == 0.5 and "speed" in stage:
                measured.set()

        class Downloader:
            def __init__(self, options: dict[str, Any]):
                self.options = options
                self.params = options

            def __enter__(self):
                return self

            def __exit__(self, *_: Any):
                pass

            def extract_info(self, url: str, download: bool, process: Mock):
                assert not download and not process
                return {"title": "Music", "duration": 30}

            def process_ie_result(self, info: dict[str, Any], download: bool):
                assert self.options["format"] == "bestaudio/best"
                self.options["download_ranges"]({"duration": 30}, None)
                arguments = self.options["external_downloader_args"]["ffmpeg_o"]
                log = Path(arguments[arguments.index("-progress") + 1])
                log.write_text(
                    "out_time_us=5000000\ntotal_size=1048576\nspeed=2.0x\nprogress=continue\n"
                )
                assert measured.wait(1)
                self.options["progress_hooks"][0]({
                    "status": "downloading",
                    "downloaded_bytes": 10,
                    "speed": 5,
                    "eta": 2,
                })
                (tmp_path / "source.m4a").write_bytes(b"music")
                return {"title": "Music"}

        monkeypatch.setattr(video, "YoutubeDL", Downloader)
        path, title = video.download(
            "https://youtu.be/abcdefghijk",
            tmp_path,
            seconds=10,
            audio=True,
            progress=progress,
        )
        assert path.suffix == ".m4a" and title == "Music"
        assert any(done is None and "ETA" in stage for done, stage in updates)
        assert updates[-1] == (1, "Music ready · Music")
        assert not any(thread.name == "timey-download" for thread in threading.enumerate())
        measured.clear()

        def fail(done: float | None, stage: str):
            if done == 0.5 and "speed" in stage:
                measured.set()
                raise RuntimeError("progress callback failed")

        with pytest.raises(RuntimeError, match="callback failed"):
            video.download(
                "https://youtu.be/abcdefghijk",
                tmp_path,
                seconds=10,
                audio=True,
                progress=fail,
            )
        assert not any(thread.name == "timey-download" for thread in threading.enumerate())
