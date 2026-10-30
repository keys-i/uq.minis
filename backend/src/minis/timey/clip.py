"""Seekable browser backdrops and short samples under Timey's shared cache budgets

Prepare short timestamped samples first and reuse a complete cached source
when available. Decoding, cancellation and atomic publication preserve a
working preview when a new download, image or encoding step fails
"""

import math
import subprocess
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic

from uq_minis.core.cache import LIMIT, entries
from uq_minis.core.common import MiniError
from uq_minis.minis.timey import cache
from uq_minis.minis.timey.video import (
    PICTURES,
    download,
    inspect,
    probe,
    require_ffmpeg,
    youtube_url,
)


def picture(
    source: Path, output: Path, *, preview: bool = False, height: int | None = None
) -> None:
    """Decode a bounded raster image, apply its orientation and save a safe background"""
    from uq_minis.minis.timey.video import Image

    if Image is None:
        raise MiniError("Enable Timey support to open image backgrounds")
    from PIL import ImageOps

    import_module("pillow_heif.HeifImagePlugin")
    try:
        with Image.open(source) as original:
            if original.width * original.height > 16_000_000:
                raise MiniError("Choose an image under 16 megapixels")
            with ImageOps.exif_transpose(original) as oriented:
                if height:
                    oriented.thumbnail((
                        max(1, round(oriented.width * height / oriented.height)),
                        height,
                    ))
                elif preview and height is None:
                    oriented.thumbnail((960, 540))
                with (
                    oriented.convert("RGBA") as rgba,
                    Image.new("RGB", oriented.size, "#f5f0df") as background,
                    rgba.getchannel("A") as alpha,
                ):
                    background.paste(rgba, mask=alpha)
                    background.save(output, format="PNG")
    except MiniError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise MiniError(
            "This picture could not be decoded; export it as PNG or JPEG and try again"
        ) from exc


def animation(source: Path, output: Path, cancelled: Event | None = None) -> bool:
    """Stream animated raster frames into a bounded, browser-compatible video

    Return False for still pictures without starting an encoder
    Retain frame timing at 30 fps with a single decoded frame in memory
    Animated imports are limited to five minutes and a 1920 × 1080 canvas
    """
    from PIL import Image, ImageOps, ImageSequence

    import_module("pillow_heif.HeifImagePlugin")
    try:
        with Image.open(source) as image:
            if not getattr(image, "is_animated", False):
                return False
            if image.width * image.height > 16_000_000:
                raise MiniError("Choose an animation under 16 megapixels per frame")
            require_ffmpeg()
            factor = min(1, 1920 / image.width, 1080 / image.height)
            size = (
                max(2, int(image.width * factor) // 2 * 2),
                max(2, int(image.height * factor) // 2 * 2),
            )
            process = subprocess.Popen(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgba",
                    "-s",
                    f"{size[0]}x{size[1]}",
                    "-r",
                    "30",
                    "-i",
                    "pipe:0",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-y",
                    str(output),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline, elapsed, emitted = monotonic() + 120, 0.0, 0
            try:
                assert process.stdin is not None
                for original in ImageSequence.Iterator(image):
                    if cancelled and cancelled.is_set():
                        raise MiniError("Animation preparation cancelled")
                    if monotonic() > deadline:
                        raise MiniError("This animation is taking too long; try a shorter copy")
                    elapsed += max(20, original.info.get("duration", 100)) / 1000
                    if elapsed > 300:
                        raise MiniError("Choose an animation shorter than five minutes")
                    count = max(0, round(elapsed * 30) - emitted)
                    if not count:
                        continue
                    with original.convert("RGBA") as frame, ImageOps.fit(frame, size) as scaled:
                        pixels = scaled.tobytes()
                    for _ in range(count):
                        if cancelled and cancelled.is_set():
                            raise MiniError("Animation preparation cancelled")
                        if monotonic() > deadline:
                            raise MiniError("This animation is taking too long; try a shorter copy")
                        process.stdin.write(pixels)
                    emitted += count
                process.stdin.close()
                if process.wait(timeout=30):
                    raise MiniError("This animation could not be converted; try an MP4 copy")
            finally:
                if process.poll() is None:
                    process.kill()
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
                process.wait()
    except MiniError:
        raise
    except (OSError, ValueError, subprocess.TimeoutExpired, Image.DecompressionBombError) as exc:
        raise MiniError("This animation could not be read; try an MP4 or GIF copy") from exc
    return True


def prepare(
    source: str,
    root: Path,
    *,
    start: int = 0,
    complete: bool = False,
    audio: bool = False,
    height: int = 540,
    fps: int = 30,
    cancelled: Event | None = None,
) -> tuple[Path, str]:
    """Cache browser-compatible video or music, or prepare a short hover sample"""
    if type(start) is not int or not 0 <= start <= 2**31 - 1:
        raise MiniError("Video start must be a non-negative timestamp")
    if (
        type(height) is not int
        or height not in {0, 240, 360, 480, 540, 720, 1080, 1440, 2160}
        or fps not in {24, 30, 60}
    ):
        raise MiniError("Choose a listed video quality and 24, 30 or 60 fps")
    local = not source.lstrip().lower().startswith(("http://", "https://"))
    path = Path(source).expanduser()
    title = path.stem
    if local:
        if not source or not path.is_file():
            raise MiniError("Choose a YouTube video or an existing local video or image")
        info = path.stat()
        identity = f"{path.resolve()}:{info.st_mtime_ns}:{info.st_size}"
        if path.suffix.lower() in PICTURES and start:
            raise MiniError("Images don't need a start timestamp")
    else:
        source = youtube_url(source)
        identity = source
    if local and path.suffix.lower() in PICTURES:
        if audio:
            raise MiniError("Choose an audio file or a video with sound")
        complete = False
        fps = 30
    offset, seconds = (0, None) if complete else (start, 10)
    if fps != 30:
        identity += f":fps{fps}"
    key = cache.identity(
        f"{'browser-full-v1' if complete else 'browser-v1'}:{identity}", height, audio
    )
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise MiniError("The media cache must not be a symlink")
    if local:
        title = next(
            (data["title"] for data, entry in entries(root) if entry.resolve() == path.resolve()),
            title,
        )
    if cancelled and cancelled.is_set():
        raise MiniError("Video preparation cancelled")
    if not complete and not (local and path.suffix.lower() in PICTURES):
        full = cache.find(
            root, cache.identity(f"browser-full-v1:{identity}", height, audio), 0, None
        )
        if full:
            return full
    cached = cache.find(root, key, offset, seconds)
    if cached:
        return cached
    if local and path.suffix.lower() in PICTURES:
        root.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".preview-", dir=root.parent) as directory:
            output = Path(directory) / "preview.png"
            picture(path, output, height=height)
            cache.save(root, key, output, title, 0, 10, True)
        cached = cache.find(root, key, 0, 10)
        if cached is None:
            raise MiniError("Couldn't store the image preview in the media cache")
        return cached
    require_ffmpeg()
    root.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".preview-", dir=root.parent) as directory:
        work = Path(directory)
        media, downloaded_title = download(
            source,
            work,
            seconds=seconds,
            height=height,
            audio=audio,
            start=offset,
            cache=root,
            limit=LIMIT if complete else None,
            cancelled=cancelled,
        )
        if complete and media.stat().st_size > LIMIT:
            raise MiniError("This video exceeds the local cache budget; choose a smaller video")
        if not local:
            title = downloaded_title
        duration = (
            (inspect(media, audio=True) if audio else inspect(media))[3]
            if local
            else next(
                (
                    data.get("duration", 0)
                    for data, _ in entries(root, cache.identity(source, height, audio))
                    if data.get("start") == offset
                ),
                0,
            )
        )
        if type(duration) not in {int, float} or not math.isfinite(duration) or duration < 0:
            duration = 0
        if complete and not duration:
            raise MiniError("Choose a video with a finite length")
        output = work / ("preview.m4a" if audio else "preview.mp4")
        process = subprocess.Popen(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                *(["-ss", str(offset)] if local and offset else []),
                "-i",
                str(media),
                *([] if complete else ["-t", "10"]),
                "-map",
                "0:a:0" if audio else "0:v:0",
                *(
                    []
                    if audio
                    else [
                        "-map",
                        "0:a:0?",
                        "-vf",
                        (
                            f"scale=w=-2:h='min(ih,{height})':force_divisible_by=2"
                            if height
                            else "scale=trunc(iw/2)*2:trunc(ih/2)*2"
                        ),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "23",
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        str(fps),
                    ]
                ),
                "-c:a",
                "aac",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                *(["-fs", str(LIMIT)] if complete else []),
                str(output),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = monotonic() + (300 if complete else 120)
        try:
            while True:
                if cancelled and cancelled.is_set():
                    raise MiniError("Video preparation cancelled")
                try:
                    _, error = process.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    if monotonic() >= deadline:
                        raise MiniError(
                            "The video preview took too long; try a shorter video"
                        ) from None
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()
        if process.returncode or not output.is_file() or not output.stat().st_size:
            raise MiniError(f"Couldn't prepare this video preview: {error[-1000:]}")
        if complete:
            if (inspect(output, audio=True) if audio else inspect(output))[3] < duration - 0.5:
                raise MiniError("This video exceeds the local cache budget; choose a smaller video")
        else:
            inspect(output, audio=True) if audio else probe(output)
        cache.save(root, key, output, title, offset, seconds, complete, duration)
    cached = cache.find(root, key, offset, seconds)
    if cached is None:
        raise MiniError("Couldn't store the preview in the media cache")
    return cached
