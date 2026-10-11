"""Bounded media and overlay samples for Timey's terminal choices"""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from rich.text import Text

from uq_minis.core.art import Preview, image
from uq_minis.core.common import MiniError
from uq_minis.minis.timey.video import Image, Timer, frames, placement, reference, youtube_url


def picture(source: Path | bytes, description: str) -> Preview:
    """Decode a small image and keep its terminal sample in memory"""
    if Image is None:
        raise MiniError("Use uv run --extra timey mini timey to enable image previews")
    try:
        if isinstance(source, bytes) and len(source) > 8 * 1024 * 1024:
            raise MiniError("Preview images must be at most 8 MiB")
        if isinstance(source, Path) and source.stat().st_size > 8 * 1024 * 1024:
            raise MiniError("Preview images must be at most 8 MiB")
        with Image.open(BytesIO(source) if isinstance(source, bytes) else source) as original:
            if original.width * original.height > 16_000_000:
                raise MiniError("Preview images must be at most 16 megapixels")
            original.thumbnail((40, 32), Image.Resampling.LANCZOS)
            sample = original.convert("RGB")
            rows = [
                [sample.getpixel((x, y)) for x in range(sample.width)] for y in range(sample.height)
            ]
    except (OSError, Image.DecompressionBombError) as exc:
        raise MiniError(f"Cannot preview this image: {exc}") from exc
    return image(rows, description)


def thumbnail(result: dict) -> Preview:
    """Fetch only YouTube's bounded thumbnail for a validated video ID"""
    description = f"{result['title']} · {result['length']}"
    id = youtube_url(result["url"]).partition("v=")[2]
    try:
        for size in ("sddefault", "hqdefault"):
            with httpx.stream("GET", f"https://i.ytimg.com/vi/{id}/{size}.jpg", timeout=5) as reply:
                if reply.status_code == 404 and size == "sddefault":
                    continue
                reply.raise_for_status()
                data = bytearray()
                for chunk in reply.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 1024 * 1024:
                        raise MiniError("The YouTube thumbnail exceeded 1 MiB")
            break
        preview = picture(bytes(data), description)
    except (httpx.HTTPError, MiniError) as exc:
        return Preview(Text(f"Thumbnail unavailable\n{description}"), f"{description} ({exc})")
    preview.picture.append(f"\n{result['length']}")
    # Keep the duration visible even when a long video title is shortened
    return preview


def overlay(timer: Timer, description: str, *, background=None, first: bool = False) -> Preview:
    """Use the exported overlay on a neutral landscape sample"""
    if Image is None:
        raise MiniError("Use uv run --extra timey mini timey to enable timer previews")
    background = (
        background.convert("RGBA")
        if background is not None
        else Image.new("RGBA", (480, 270), "#20262d")
    )
    with Image.open(BytesIO(next(frames(timer, *background.size, preview=not first)))) as plate:
        x, y, _ = placement(timer, *background.size)
        background.alpha_composite(plate, (x, y))
        with BytesIO() as encoded:
            background.save(encoded, format="PNG")
            return picture(encoded.getvalue(), description)


def frame(source: Path, timer: Timer | None = None, *, start: int = 0) -> Preview:
    """Preview an existing video's opening frame, with the timer when still drafting"""
    with TemporaryDirectory(prefix=".timey-preview-", dir=Path.cwd()) as directory:
        path = Path(directory) / "frame.png"
        reference(source, path, start=start, size=480)
        if timer is None:
            return picture(path, "First frame of the finished video")
        with Image.open(path) as background:
            return overlay(timer, "Opening frame with timer", background=background, first=True)
