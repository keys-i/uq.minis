import json
import os
import subprocess
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, Mock

import pytest

from tests.fixtures import Clip
from uq_minis.core import cache
from uq_minis.core.common import MiniError
from uq_minis.minis.timey import cache as media
from uq_minis.minis.timey import clip as clips


def test_complete_cache_hit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "complete.mp4"
    source.write_bytes(b"cached-video")
    root = tmp_path / "media"
    key = media.identity("browser-full-v1:https://www.youtube.com/watch?v=abcdefghijk", 540, False)
    media.save(root, key, source, "Forest", 0, None, True, 300)
    download = Mock(side_effect=AssertionError("Complete cached videos must open directly"))
    monkeypatch.setattr(clips, "download", download)
    output, title = clips.prepare("https://youtu.be/abcdefghijk", root, start=80)
    assert output.read_bytes() == b"cached-video" and title == "Forest"
    download.assert_not_called()


@pytest.mark.parametrize("suffix", ["png", "jpg", "webp"])
def test_images_render_as_a_still_background(tmp_path: Path, suffix: str) -> None:
    from PIL import Image

    from uq_minis.minis.timey.video import Timer, inspect, render

    source = tmp_path / f"garden.{suffix}"
    with Image.new("RGB", (160, 90), "green") as image:
        image.save(source)
    background, title = clips.prepare(str(source), tmp_path / "media")
    assert background.is_relative_to(tmp_path / "media") and title == "garden"
    assert clips.prepare(str(source), tmp_path / "media") == (background, title)
    output = render(
        source,
        tmp_path / "timer.mp4",
        Timer(seconds=2, start_gap=0, end_gap=0, motion=False),
        height=0,
        fps=24,
    )
    assert inspect(output) == (160, 90, False, pytest.approx(2, abs=0.1))


def test_picture_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from PIL import Image

    source, output = tmp_path / "photo.jpg", tmp_path / "background.png"
    with Image.new("RGB", (3, 2), "blue") as image:
        exif = Image.Exif()
        exif[274] = 6
        image.save(source, exif=exif)
    clips.picture(source, output)
    with Image.open(output) as normalized:
        assert normalized.size == (2, 3) and normalized.mode == "RGB"
    source = tmp_path / "clear.png"
    with Image.new("RGBA", (2, 2), (0, 0, 0, 0)) as image:
        image.save(source)
    clips.picture(source, output)
    with Image.open(output) as normalized:
        assert normalized.getpixel((0, 0)) == (245, 240, 223)
    large = MagicMock(format="PNG", width=16385, height=1024)
    large.__enter__.return_value = large
    monkeypatch.setattr(Image, "open", Mock(return_value=large))
    with pytest.raises(MiniError, match="16 megapixels"):
        clips.picture(source, output)


def test_preview_range_and_reuse(
    clip: Clip, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = clip(
        "source.mp4",
        "color=c=red:s=160x90:r=10:d=5[red];color=c=blue:s=160x90:r=10:d=20[blue];[red][blue]concat=n=2:v=1:a=0",
        25,
        audio=True,
    )
    root = tmp_path / "media"
    output, title = clips.prepare(str(source), root, start=7)
    assert output.is_relative_to(root) and title == "source"
    metadata = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert float(metadata["format"]["duration"]) == pytest.approx(10, abs=0.1)
    assert {stream["codec_name"] for stream in metadata["streams"]} == {"h264", "aac"}
    assert metadata["streams"][0]["width"] == 160
    pixel = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(output),
            "-frames:v",
            "1",
            "-vf",
            "scale=1:1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    assert pixel[2] > 200 and pixel[0] < 20
    index = output.parent / "info.json"
    assert json.loads(index.read_text())["duration"] == pytest.approx(25, abs=0.1)
    os.utime(index, (1, 1))
    download = Mock(side_effect=AssertionError("A cache hit must not download"))
    encode = Mock(side_effect=AssertionError("A cache hit must not encode"))
    monkeypatch.setattr(clips, "download", download)
    monkeypatch.setattr("uq_minis.minis.timey.clip.subprocess.run", encode)
    assert clips.prepare(str(source), root, start=7) == (output, title)
    assert index.stat().st_mtime > 1
    download.assert_not_called()
    encode.assert_not_called()


def test_partial_download(clip: Clip, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = clip("downloaded.mp4", "color=c=blue:s=160x90:r=10", 10)
    download = Mock(return_value=(source, "A backdrop"))
    monkeypatch.setattr(clips, "download", download)
    root = tmp_path / "media"
    output, title = clips.prepare("https://youtu.be/abcdefghijk", root, start=80)
    assert output.is_file() and title == "A backdrop"
    assert download.call_args.kwargs == {
        "seconds": 10,
        "height": 540,
        "audio": False,
        "start": 80,
        "cache": root,
        "limit": None,
        "cancelled": None,
    }
    assert download.call_args.args[0] == "https://www.youtube.com/watch?v=abcdefghijk"


def test_complete_download_and_reuse(
    clip: Clip, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uq_minis.minis.timey.video import inspect

    source = clip("source.mp4", "testsrc2=s=160x90:r=10", 25, audio=True)
    root = tmp_path / "media"
    output, title = clips.prepare(str(source), root, complete=True, start=7)
    assert inspect(output)[3] == pytest.approx(25, abs=0.1)
    data = json.loads((output.parent / "info.json").read_text())
    assert data["complete"] is True and data["start"] == 0 and data["seconds"] is None
    assert data["duration"] == pytest.approx(25, abs=0.1)
    monkeypatch.setattr(
        clips, "download", Mock(side_effect=AssertionError("Must reuse the full video"))
    )
    assert clips.prepare(str(source), root, complete=True, start=21) == (output, title)


def test_cancelled_encoder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    cancelled = Event()
    process = Mock()
    process.poll.return_value = None

    def communicate(*, timeout: float | None = None) -> tuple[None, str]:
        if timeout is not None:
            cancelled.set()
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        return None, ""

    process.communicate.side_effect = communicate
    monkeypatch.setattr(clips, "download", Mock(return_value=(source, "Video")))
    monkeypatch.setattr(clips, "inspect", Mock(return_value=(160, 90, False, 25)))
    monkeypatch.setattr(clips, "require_ffmpeg", Mock())
    monkeypatch.setattr(subprocess, "Popen", Mock(return_value=process))
    root = tmp_path / "media"
    with pytest.raises(MiniError, match="cancelled"):
        clips.prepare(str(source), root, complete=True, cancelled=cancelled)
    process.kill.assert_called_once()
    assert not list(cache.entries(root))


@pytest.mark.parametrize("reason", ["cancelled", "budget"])
def test_full_download_stops_when_cancelled_or_over_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    from uq_minis.minis.timey import video

    cancelled = Event()
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.extract_info.return_value = {"duration": 60}

    def transfer(*args: object, **kwargs: object) -> None:
        if reason == "cancelled":
            cancelled.set()
        factory.call_args.args[0]["progress_hooks"][0]({
            "status": "downloading",
            "downloaded_bytes": 9,
        })

    client.process_ie_result.side_effect = transfer
    monkeypatch.setattr(video, "YoutubeDL", factory)
    with pytest.raises(MiniError, match=reason):
        video.download("https://youtu.be/abcdefghijk", tmp_path, limit=8, cancelled=cancelled)
    assert factory.call_args.args[0]["max_filesize"] == 8


def test_failed_section_preserves_preview(clip: Clip, tmp_path: Path) -> None:
    source = clip("short.mp4", "color=c=red:s=160x90:r=10", 2)
    root = tmp_path / "media"
    working, _ = clips.prepare(str(source), root)
    before = working.read_bytes()
    with pytest.raises(MiniError):
        clips.prepare(str(source), root, start=20)
    assert working.read_bytes() == before
    assert len(list(cache.entries(root))) == 1


@pytest.mark.parametrize(
    "source,start",
    [
        ("https://example.org/video", 0),
        ("", 0),
        ("missing.mp4", 0),
        ("https://youtu.be/abcdefghijk", -1),
    ],
)
def test_preview_rejects_invalid_sources_and_timestamps(
    tmp_path: Path, source: str, start: int
) -> None:
    with pytest.raises(MiniError):
        clips.prepare(source, tmp_path / "media", start=start)


def test_music_is_cached_as_audio_and_reused_at_any_start(
    clip: Clip, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uq_minis.minis.timey.video import inspect

    source = clip("music.mp4", "color=c=blue:s=160x90:r=10", 3, audio=True)
    root = tmp_path / "media"
    output, title = clips.prepare(str(source), root, audio=True, complete=True)
    assert output.suffix == ".m4a" and title == "music"
    assert inspect(output, audio=True) == (0, 0, True, pytest.approx(3, abs=0.1))
    with pytest.raises(MiniError, match="video stream"):
        inspect(output)
    monkeypatch.setattr(
        clips, "download", Mock(side_effect=AssertionError("Reuse the cached track"))
    )
    assert clips.prepare(str(source), root, audio=True, complete=True, start=2) == (output, title)


def test_music_rejects_silent_video_and_images(clip: Clip, tmp_path: Path) -> None:
    from PIL import Image

    silent = clip("silent.mp4", "color=c=blue:s=160x90:r=10", 1)
    picture = tmp_path / "garden.png"
    Image.new("RGB", (4, 4)).save(picture)
    root = tmp_path / "media"
    for source in (silent, picture):
        with pytest.raises(MiniError, match="audio"):
            clips.prepare(str(source), root, audio=True, complete=True)
    assert not list(cache.entries(root))


@pytest.mark.parametrize("reason", ["cancelled", "timeout"])
def test_animation_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    from PIL import Image

    source = tmp_path / "motion.gif"
    with Image.new("RGB", (8, 8), "red") as first, Image.new("RGB", (8, 8), "blue") as second:
        first.save(source, save_all=True, append_images=[second], duration=100)
    stopped = Event()
    if reason == "cancelled":
        stopped.set()
    else:
        monkeypatch.setattr(clips, "monotonic", Mock(side_effect=[0, 121]))
    with pytest.raises(
        MiniError, match="cancelled" if reason == "cancelled" else "taking too long"
    ):
        clips.animation(source, tmp_path / "motion.mp4", stopped)
