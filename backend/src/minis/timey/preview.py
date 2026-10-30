"""Bounded media and overlay samples for Timey's terminal choices

Previews use the actual font and overlay renderer, bounded to the available
terminal cells. Thumbnail and still-frame reads stay separate from complete
media downloads and retain meaningful text alternatives
"""

from collections.abc import Callable
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import httpx
from rich.text import Text

from uq_minis.assets import ROOT as ASSETS
from uq_minis.core.art import Preview, image
from uq_minis.core.common import MiniError
from uq_minis.minis.timey.video import (
    FONTS,
    STYLES,
    Image,
    Timer,
    frames,
    placement,
    reference,
    typeface,
    youtube_url,
)
from uq_minis.minis.timey.video import (
    layers as timer_layers,
)


def picture(
    source: Path | bytes,
    description: str,
    *,
    height: int = 0,
    paint: Callable[[Image.Image, float], None] | None = None,
) -> Preview:
    """Decode a bounded image and redraw it for the available terminal cells

    Accept a local path or encoded bytes up to 8 MiB and 16 megapixels
    ``height=0`` keeps original quality; a positive height supplies a ceiling
    Render two image pixels per terminal cell without stretching the aspect ratio
    ``paint`` may add live overlay effects to each resized canvas
    Unsupported or unsafe images raise MiniError before panel rendering
    """
    if not Image:
        raise MiniError("Use uv run --extra timey mini timey to enable image previews")
    if type(height) is not int or height != 0 and height < 240:
        raise MiniError("Preview height must be at least 240p, or 0 for the original image")
    quality = height
    try:
        if isinstance(source, Path):
            with source.open("rb") as file:
                data = file.read(8 * 1024 * 1024 + 1)
        else:
            data = source
        if len(data) > 8 * 1024 * 1024:
            raise MiniError("Preview images must be at most 8 MiB")
        with Image.open(BytesIO(data)) as original:
            if original.width * original.height > 16_000_000:
                raise MiniError("Preview images must be at most 16 megapixels")
            original.verify()
    except (OSError, Image.DecompressionBombError) as exc:
        raise MiniError(f"Cannot preview this image: {exc}") from exc

    def draw(width: int, height: int, elapsed: float | None = None) -> Text:
        with Image.open(BytesIO(data)) as original:
            ceiling = quality / original.height if 0 < quality < original.height else 1
            original.thumbnail(
                (
                    max(1, min(512, width, round(original.width * ceiling))),
                    max(
                        1,
                        min(
                            512,
                            (height - len(description.splitlines())) * 2,
                            round(original.height * ceiling),
                        ),
                    ),
                ),
                Image.Resampling.LANCZOS,
            )
            scaled = original.convert("RGBA" if paint and elapsed is not None else "RGB")
        if paint and elapsed is not None:
            paint(scaled, elapsed)
            scaled = scaled.convert("RGB")
        rows = [
            [cast(tuple[int, int, int], scaled.getpixel((x, y))) for x in range(scaled.width)]
            for y in range(scaled.height)
        ]
        return image(rows, description).picture

    try:
        return Preview(
            draw(40, 16 + len(description.splitlines())), description, draw, draw if paint else None
        )
    except (OSError, Image.DecompressionBombError) as exc:
        raise MiniError(f"Cannot preview this image: {exc}") from exc


def thumbnail(result: dict[str, Any], *, height: int = 0) -> Preview:
    """Preview a search result's thumbnail, title and duration without media download

    Use a validated YouTube URL and try the largest thumbnail before smaller
    variants; each response is bounded to 1 MiB and uses a short timeout
    Network or image failures return a readable text preview so selection can
    continue, while an invalid video URL raises MiniError
    """
    description = f"{result['title']}\n{result['length']}"
    id = youtube_url(result["url"]).partition("v=")[2]
    data = bytearray()
    try:
        for size in ("maxresdefault", "sddefault", "hqdefault", "mqdefault"):
            with httpx.stream("GET", f"https://i.ytimg.com/vi/{id}/{size}.jpg", timeout=5) as reply:
                if reply.status_code == 404 and size != "mqdefault":
                    continue
                reply.raise_for_status()
                data = bytearray()
                for chunk in reply.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 1024 * 1024:
                        raise MiniError("The YouTube thumbnail exceeded 1 MiB")
            break
        preview = picture(bytes(data), description, height=height)
    except (httpx.HTTPError, MiniError) as exc:
        return Preview(Text(f"Thumbnail unavailable\n{description}"), f"{description} ({exc})")
    return preview


def overlay(
    timer: Timer,
    description: str,
    *,
    background: Image.Image | None = None,
    first: bool = False,
    height: int = 0,
) -> Preview:
    """Preview the actual timer overlay, including its resolved font family and face

    Use a neutral landscape sample unless a background image is supplied
    ``first`` shows the opening state; otherwise display the countdown itself
    Apply the export's frame details and ambient motion through a bounded live
    renderer, retaining a still version for paused or reduced-motion terminals
    """
    if not Image:
        raise MiniError("Use uv run --extra timey mini timey to enable timer previews")
    font = timer.font or (
        str(ASSETS / "timey/fonts" / f"{FONTS[timer.style]}.ttf")
        if timer.style in FONTS and not timer.artwork
        else ""
    )
    kind = timer.artwork["font"] if timer.artwork else STYLES.get(timer.style, STYLES["minimal"])[3]
    family, face = typeface("mono" if kind == "pixel" else kind, 12, font).getname()
    description += f"\nFont: {family} {face}"

    background = (
        background.convert("RGBA")
        if background is not None
        else Image.new("RGBA", (480, 270), "#20262d")
    )
    from uq_minis.minis.timey.scene import Scene, liquid

    playing = replace(
        timer, start_gap=timer.start_gap if first else 0, end_gap=max(1, timer.end_gap)
    )
    layers = timer_layers(playing, *background.size)
    plate, mask = next(layers)
    colour = "#" + (
        timer.accent
        or (
            "E4C36E"
            if timer.style == "temple-run"
            else STYLES.get(timer.style, STYLES["minimal"])[1]
        )
    ).lstrip("#")
    scene = Scene(
        timer.style if not timer.artwork else "custom",
        plate.size,
        colour,
        f"{timer.label}:{timer.seconds}",
        seconds=playing.seconds,
        start_gap=playing.start_gap,
    )
    scene.set(mask if not timer.artwork else Image.new("L", mask.size))
    origin: float | None = None
    second = 0
    x, y, _ = placement(timer, *background.size)

    def paint(canvas: Image.Image, elapsed: float) -> None:
        nonlocal origin, second, layers, plate, mask
        if origin is None or elapsed < origin:
            origin = elapsed
        moment = max(0, elapsed - origin)
        target = min(playing.total - 1, int(moment))
        if target != second:
            previous = mask
            # A long pause seeks directly instead of drawing every obsolete countdown state
            if target < second or target > second + 2:
                layers.close()
                layers = timer_layers(playing, *background.size, offset=target)
                plate, mask = next(layers)
            else:
                for _ in range(target - second):
                    plate, mask = next(layers)
            scene.set(
                mask if not timer.artwork else Image.new("L", mask.size), previous, moment=target
            )
            second = target
        rendered = background.copy()
        if timer.style == "glass":
            liquid(rendered, (x, y, plate.width, plate.height), moment)
        rendered.alpha_composite(scene.paint(plate, moment), (x, y))
        canvas.paste(rendered.resize(canvas.size, Image.Resampling.LANCZOS))  # pyright: ignore[reportUnknownMemberType]

    encoded_plate = next(frames(timer, *background.size, preview=not first))
    still = background.copy()
    if timer.style == "glass":
        liquid(still, (x, y, plate.width, plate.height), 0)
    with Image.open(BytesIO(encoded_plate)) as still_plate:
        still.alpha_composite(still_plate, (x, y))
        with BytesIO() as encoded:
            still.save(encoded, format="PNG")
            return picture(
                encoded.getvalue(),
                description,
                height=height,
                paint=paint if timer.motion else None,
            )


def frame(source: Path, timer: Timer | None = None, *, start: int = 0, height: int = 0) -> Preview:
    """Read one video frame and optionally composite the draft timer over it

    ``start`` is a timestamp in seconds and ``height`` limits preview quality
    Extract a 1024-pixel reference to preserve terminal detail without decoding
    a full 8K frame, and remove the temporary image before returning the preview
    FFmpeg and image failures propagate without replacing the source footage
    """
    with TemporaryDirectory(prefix=".timey-preview-", dir=Path.cwd()) as directory:
        path = Path(directory) / "frame.png"
        # Twice the terminal raster budget preserves detail without decoding an 8K frame
        reference(source, path, start=start, size=1024)
        if timer is None:
            return picture(path, "First frame of the finished video", height=height)
        with Image.open(path) as background:
            return overlay(
                timer, "Opening frame with timer", background=background, first=True, height=height
            )
