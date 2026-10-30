"""Timey render behaviour and failure paths"""

import json
import math
import subprocess
import threading
from array import array
from contextlib import nullcontext
from dataclasses import replace
from errno import EINVAL, EIO, EPIPE
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest
from PIL import Image, ImageChops, ImageStat

from tests.fixtures import Clip
from uq_minis.core.common import MiniError
from uq_minis.minis import timey
from uq_minis.minis.timey import video, youtube


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
class TestRender:
    @pytest.mark.parametrize("height", [0, 240, 360, 480, 720, 1080, 2160])
    def test_quality(self, tmp_path: Path, clip: Clip, height: int) -> None:
        source = clip("source.mp4", "color=c=navy:s=1920x1080:r=24", seconds=0.1)
        output = tmp_path / "timer.mp4"
        video.render(
            source,
            output,
            video.Timer(seconds=1, start_gap=0, end_gap=0, motion=False),
            height=height,
            fps=24,
        )
        width, actual, _ = video.probe(output)
        assert actual == (min(height, 1080) if height else 1080)
        assert width % 2 == 0

    @pytest.mark.parametrize(
        "error,cancelled,fails",
        [
            (EPIPE, False, False),
            (EINVAL, True, False),
            (EINVAL, False, True),
            (EIO, True, True),
        ],
        ids=["closed", "cancelled", "invalid", "io"],
    )
    def test_pipe(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        error: Exception | None,
        cancelled: bool,
        fails: bool,
    ) -> None:
        stopped = threading.Event()
        if cancelled:
            stopped.set()
        monkeypatch.setattr(video, "Event", lambda: stopped)
        process = Mock(stdout=BytesIO(), wait=Mock(return_value=0), poll=Mock(return_value=0))
        process.stdin.close.side_effect = OSError(error, "closed pipe")
        monkeypatch.setattr(subprocess, "Popen", Mock(return_value=process))
        with pytest.raises(OSError) if fails else nullcontext():
            video._encode(["ffmpeg"], tmp_path, 1, "Timer", None, iter([b"frame"]))
        process.stdin.close.assert_called_once()
        assert not any(thread.name == "timey-overlay" for thread in threading.enumerate())

    def test_timing(self, tmp_path: Path, clip: Clip) -> None:
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
        assert cast(tuple[int, int, int], Image.open(still).getpixel((5, 5)))[0] > 75
        video.render(source, output, timer, start=3, height=480)
        assert video.inspect(output)[2:][0]
        assert video.inspect(output)[3] == pytest.approx(9, abs=0.05)
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
            assert cast(tuple[int, int, int], Image.open(image).getpixel((5, 5)))[0] > 75
        details = output.with_suffix(".youtube.json")
        details.write_text(
            json.dumps({
                "snippet": {
                    "title": "Timestamped timer",
                    "description": "",
                    "tags": ["timer"],
                },
                "status": {
                    "privacyStatus": "private",
                    "selfDeclaredMadeForKids": False,
                    "containsSyntheticMedia": False,
                },
                "thumbnail": "first-frame",
            })
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
            source,
            tmp_path / "smooth.mp4",
            replace(timer, loop_blend=0.6),
            start=3,
            height=480,
        )
        assert video.inspect(tmp_path / "smooth.mp4")[3] == pytest.approx(9, abs=0.05)
        assert not list(tmp_path.glob(".thumbnail-*")) and not list(tmp_path.glob(".timey-*"))

    def test_export(self, tmp_path: Path, clip: Clip) -> None:
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
        crops: list[bytes] = []
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

        def cancel(*args: Any):
            if args[1].startswith("Rendering the timer"):
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            timey.render(source, output, timey.Timer(seconds=120), force=True, progress=cancel)
        assert output.read_bytes() == old
        assert not list(tmp_path.glob(".timey-*"))
        assert not any(thread.name == "timey-overlay" for thread in threading.enumerate())

    def test_loop(self, tmp_path: Path, clip: Clip) -> None:
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
        stages: list[str] = []
        timey.render(
            source,
            animated,
            timer,
            fps=24,
            progress=lambda done, stage: stages.append(stage),
        )
        timey.render(source, still, replace(timer, motion=False), fps=24)
        timey.render(
            source,
            hard,
            replace(timer, style="minimal", motion=False, loop_blend=0),
            fps=24,
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
        jumps: list[float] = []
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

        def frame(output: Path):
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
        crop = quiet.crop((x + 28, y + 22, x + 36, y + 34))
        outside = quiet.crop((10, 10, 18, 22))
        assert max(ImageStat.Stat(crop).stddev) < max(ImageStat.Stat(outside).stddev) / 3
        delta = ImageChops.difference(moving, quiet)
        centre = delta.crop((
            x + 20,
            y + 10,
            x + round(540 * scale) - 20,
            y + round(234 * scale) - 10,
        ))
        # Refraction now moves behind the digits as well as along the meniscus
        assert 0 < max(ImageStat.Stat(centre).mean) < 8
        assert max(high for _, high in cast(tuple[tuple[int, int], ...], delta.getextrema())) > 10

        old = animated.read_bytes()

        def cancel(done: float | None, stage: str):
            if stage.startswith("Smoothing the loop"):
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            timey.render(source, animated, timer, force=True, progress=cancel)
        assert animated.read_bytes() == old and not list(tmp_path.glob(".timey-*"))

    def test_audio(self, tmp_path: Path, clip: Clip) -> None:
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
        measured: list[list[float]] = []
        for mix, volume in ((False, 1), (True, 1), (False, 0.5)):
            output = tmp_path / f"{mix}-{volume}.mp4"
            progress: list[tuple[float | None, str]] = []
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
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(source),
                "-c:v",
                "copy",
                "-an",
                str(silent),
            ],
            check=True,
            capture_output=True,
        )
        with pytest.raises(MiniError, match="audio stream"):
            video.render(source, tmp_path / "silent-music.mp4", timer, music=silent)
