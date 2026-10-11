"""Game-inspired countdown videos with small overlays streamed into FFmpeg"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from errno import EINVAL, EPIPE
from io import BytesIO
from itertools import chain, islice, repeat
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from urllib.parse import parse_qs, urlsplit

from uq_minis.assets import ROOT as ASSETS
from uq_minis.core.common import MiniError, ensure_outputs
from uq_minis.minis.timey import cache as media_cache
from uq_minis.minis.timey.style import validate as validate_style

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
except ImportError:
    Image = ImageChops = ImageDraw = ImageFilter = ImageFont = None

try:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError
except ImportError:
    YoutubeDL = None
    DownloadError = MiniError

STYLES = frozendict(
    {
        "temple-run": (
            "Weathered temple stone, emerald gems and cracked gold numerals",
            "8EE62C",
            "171B13",
            "serif",
        ),
        "minecraft": (
            "Stone hotbar, pixel digits and an emerald XP meter",
            "8FDA53",
            "20221F",
            "mono",
        ),
        "subway-surfers": (
            "Bright blue badge, chunky lettering and a yellow rail",
            "FFD34D",
            "123B67",
            "sans",
        ),
        "neon": (
            "Violet arcade frame and a luminous cyan countdown",
            "6FE9EF",
            "19142F",
            "mono",
        ),
        "minimal": (
            "Quiet charcoal panel with a clean white countdown",
            "E9EDEA",
            "161B20",
            "sans",
        ),
        "glass": (
            "Frosted video glass, clear digits and a soft reflected edge",
            "E4EDF5",
            "18212D",
            "sans",
        ),
    }
)
FONTS = frozendict(
    {
        "temple-run": "skranji",
        "minecraft": "pressstart2p",
        "subway-surfers": "bungee",
    }
)
POSITIONS = (
    "top-right",
    "top-left",
    "bottom-right",
    "bottom-left",
    "bottom-centre",
    "centre",
)
Progress = Callable[[float | None, str], None]


def duration(value: str) -> int:
    """Read seconds, MM:SS, HH:MM:SS or a duration such as 1h 20m 5s"""
    value = value.strip().lower()
    if re.fullmatch(r"\d+", value):
        return int(value)
    if re.fullmatch(r"\d+:\d{2}(?::\d{2})?", value):
        parts = [int(part) for part in value.split(":")]
        if any(part >= 60 for part in parts[1:]):
            raise MiniError("Minutes and seconds after a colon must be below 60")
        return sum(part * 60**index for index, part in enumerate(reversed(parts)))
    match = re.fullmatch(r"\s*(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s\s*)?", value)
    if match and any(match.groups()):
        return sum(int(part or 0) * factor for part, factor in zip(match.groups(), (3600, 60, 1)))
    raise MiniError("Use seconds, MM:SS, HH:MM:SS or a duration like 10m or 1h 30m")


def clock(seconds: int, *, hours: bool = False) -> str:
    """Format the countdown without dropping hours"""
    hour, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hour:02}:{minutes:02}:{seconds:02}" if hour or hours else f"{minutes:02}:{seconds:02}"


@dataclass(frozen=True)
class Timer:
    """Bounded countdown settings shared by previews and exports"""

    seconds: int = 600
    start_gap: int = 5
    end_gap: int = 5
    style: str = "minimal"
    position: str = "centre"
    label: str = ""
    accent: str = ""
    font: str = ""
    artwork: dict | None = None
    size: float = 2.4
    motion: bool = True
    loop_blend: float = 0.6

    def __post_init__(self) -> None:
        """Reject invalid settings before any rendering work"""
        if any(type(value) is not int for value in (self.seconds, self.start_gap, self.end_gap)):
            raise MiniError("Timer length and gaps must be whole seconds")
        if not 1 <= self.seconds <= 86400 or not all(
            0 <= gap <= 3600 for gap in (self.start_gap, self.end_gap)
        ):
            raise MiniError("Timer must be 1 second–24 hours; each gap must be 0–60 minutes")
        if (self.style not in STYLES and not self.artwork) or self.position not in POSITIONS:
            raise MiniError("Choose a listed timer style and position")
        if self.artwork is not None:
            validate_style(self.artwork)
        if self.accent and not re.fullmatch(r"#?[0-9a-fA-F]{6}", self.accent):
            raise MiniError("Accent must be a six-digit hex colour such as #8FDA53")
        if len(self.label) > 32 or any(ord(char) < 32 for char in self.label):
            raise MiniError("Use a one-line label of at most 32 characters")
        if self.font and not Path(self.font).expanduser().is_file():
            raise MiniError("Custom font must be an existing .ttf, .otf or .ttc file")
        if type(self.size) not in {int, float} or not 0.5 <= self.size <= 3:
            raise MiniError("Overlay size must be between 0.5 and 3")
        if type(self.loop_blend) not in {int, float} or not 0 <= self.loop_blend <= 2:
            raise MiniError("Loop crossfade must be between 0 and 2 seconds")

    @property
    def total(self) -> int:
        """Include both gaps in the exported video length"""
        return self.start_gap + self.seconds + self.end_gap


def youtube_url(value: str) -> str:
    """Accept a single YouTube video and discard playlist and tracking parameters"""
    try:
        url = urlsplit(value.strip())
    except ValueError as exc:
        raise MiniError("This YouTube link is malformed; paste the video link again") from exc
    if url.scheme not in {"http", "https"} or url.username or url.password:
        raise MiniError("Enter a YouTube video link or an existing local video path")
    if url.hostname == "youtu.be":
        video_id = url.path.strip("/")
    elif url.hostname in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }:
        pieces = url.path.strip("/").split("/")
        video_id = (
            parse_qs(url.query).get("v", [""])[0]
            if url.path == "/watch"
            else pieces[1]
            if len(pieces) == 2 and pieces[0] in {"shorts", "embed", "live"}
            else ""
        )
    else:
        video_id = ""
    if not re.fullmatch(r"[\w-]{11}", video_id, flags=re.ASCII):
        raise MiniError("Use a single youtube.com/watch?v=… or youtu.be/… video link")
    return f"https://www.youtube.com/watch?v={video_id}"


def search(query: str) -> list[dict]:
    """Read five video results without downloading media or following result links"""
    if not query.strip() or len(query) > 200:
        raise MiniError("Search with between 1 and 200 characters")
    if YoutubeDL is None:
        raise MiniError("Use uv run --extra timey mini timey to enable YouTube search")
    try:
        with YoutubeDL(
            {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "skip_download": True,
                "socket_timeout": 10,
                "retries": 1,
                "extractor_retries": 1,
                "playlistend": 5,
            }
        ) as client:
            data = client.extract_info(f"ytsearch5:{query.strip()}", download=False)
    except DownloadError as exc:
        raise MiniError(f"YouTube search failed: {exc}") from exc
    if data is not None and not isinstance(data, dict):
        raise MiniError("YouTube returned malformed search results; try again")
    results = []
    seen = set()
    for entry in islice((data or {}).get("entries", []) or [], 10):
        if not isinstance(entry, dict):
            continue
        id = entry.get("id", "")
        if not isinstance(id, str) or not re.fullmatch(r"[\w-]{11}", id, flags=re.ASCII):
            continue
        if id in seen or entry.get("is_live") or entry.get("live_status") == "is_live":
            continue
        seen.add(id)
        title = entry.get("title")
        title = " ".join((title if isinstance(title, str) else id)[:400].split())
        title = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", title)[:200]
        seconds = entry.get("duration")
        length = (
            clock(round(seconds))
            if type(seconds) in {int, float} and 0 < seconds < 10**8
            else "duration unavailable"
        )
        results.append(
            {"url": youtube_url(f"https://youtu.be/{id}"), "title": title, "length": length}
        )
        if len(results) == 5:
            break
    return results


def download(
    source: str,
    directory: Path,
    *,
    seconds: int | None = None,
    height: int = 1080,
    progress: Progress | None = None,
    audio: bool = False,
    start: int = 0,
    cache: Path | None = None,
) -> tuple[Path, str]:
    """Reuse cached media or download only the needed section at bounded quality"""
    if type(start) is not int or not 0 <= start <= 2**31 - 1:
        raise MiniError("Video start must be a non-negative timestamp")
    if seconds is not None and (type(seconds) is not int or seconds < 1):
        raise MiniError("Download length must be at least one second")
    path = Path(source).expanduser()
    if not source.lstrip().lower().startswith(("http://", "https://")) and path.is_file():
        if progress:
            progress(
                1,
                f"Music ready · {path.name}" if audio else f"Background ready · {path.name}",
            )
        return path.resolve(), path.stem
    url = youtube_url(source)
    key = media_cache.identity(url, height, audio)
    if cache:
        cache = cache.expanduser().absolute()
        if cache.is_symlink():
            raise MiniError("The media cache must not be a symlink")
        cached = media_cache.find(cache, key, start, seconds, directory)
        if cached:
            if progress:
                progress(1, f"{'Music' if audio else 'Background'} ready · cache hit · {cached[1]}")
            return cached
    if YoutubeDL is None:
        raise MiniError("Run with uv run --extra timey mini timey to enable YouTube downloads")

    noun = "music" if audio else "background"
    transferred = Event()
    if progress:
        progress(
            None,
            f"Grokking the {'music video' if audio else 'video'} · reading YouTube metadata",
        )

    def update(data: dict) -> None:
        if progress and data["status"] == "downloading":
            transferred.clear()
            size = data.get("total_bytes") or data.get("total_bytes_estimate")
            received = data.get("downloaded_bytes", 0)
            detail = f"{received / 1048576:.1f} MiB"
            if size:
                detail += f" / {size / 1048576:.1f} MiB"
            if data.get("speed"):
                detail += f" · {data['speed'] / 1048576:.1f} MiB/s"
            if data.get("eta") is not None:
                detail += f" · ETA {clock(round(data['eta']))}"
            progress(
                min(1, received / size) if size else None,
                f"Downloading {noun} · {detail}",
            )
        elif progress and data["status"] == "finished":
            transferred.set()
            progress(None, f"Stitching the {noun} · checking downloaded streams")

    def postprocess(data: dict) -> None:
        if progress and data["status"] == "started":
            transferred.set()
            progress(
                None,
                f"Stitching the {noun} · {data.get('postprocessor', 'merging streams')}",
            )

    options = {
        "format": "bestaudio/best" if audio else f"bv*[height<={height}]+ba/b[height<={height}]",
        "outtmpl": str(directory / "source.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "cachedir": str(cache / "extractor") if cache else False,
        "concurrent_fragment_downloads": 8,
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
        "progress_hooks": [update],
        "postprocessor_hooks": [postprocess],
        "js_runtimes": {name: {} for name in ("deno", "node") if shutil.which(name)},
        "match_filter": lambda info, *, incomplete=False: (
            "Live streams cannot be used as timer backgrounds" if info.get("is_live") else None
        ),
    }
    stopped, length, failures = Event(), [seconds], []
    progress_file = directory / "download.log"
    watcher = None
    if seconds is not None or start:

        def section(info, ydl):
            available = info.get("duration")
            if available and start >= available:
                raise MiniError("Video start must be before the end of the source video")
            length[0] = (
                min(seconds or available - start, available - start) if available else seconds
            )
            if not length[0]:
                raise MiniError("Set a download length for a source with an unknown duration")
            if progress:
                progress(
                    None,
                    f"Downloading {noun} · from {clock(start)}, {clock(round(length[0]))} of media",
                )
            return [{"start_time": start, "end_time": start + length[0]}]

        options["download_ranges"] = section
        # yt-dlp's ranged FFmpeg downloads only fire a hook at completion
        options["external_downloader_args"] = {
            "ffmpeg_o": [
                "-progress",
                str(progress_file.resolve()),
                "-stats_period",
                "0.25",
            ]
        }

        def track() -> None:
            state, position = {}, 0
            while not stopped.wait(0.15):
                if not progress_file.exists():
                    continue
                with progress_file.open("rb") as stream:
                    stream.seek(position)
                    for line in stream:
                        if not line.endswith(b"\n"):
                            break
                        position += len(line)
                        key, _, value = (
                            line.decode("utf-8", errors="replace").strip().partition("=")
                        )
                        state[key] = value
                        if key != "progress":
                            continue
                        try:
                            seconds_done = max(0, float(state.get("out_time_us", 0)) / 1_000_000)
                            size = max(0, int(state.get("total_size", 0)))
                        except ValueError:
                            continue
                        detail = f"{clock(round(seconds_done))} / {clock(round(length[0]))} · {size / 1048576:.1f} MiB · {state.get('speed', '?')} speed"
                        if progress and not transferred.is_set():
                            progress(
                                min(1, seconds_done / length[0]),
                                f"Downloading {noun} · {detail}",
                            )

        def watch() -> None:
            try:
                track()
            except Exception as exc:
                failures.append(exc)

    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False, process=False)
            if not info or info.get("is_live"):
                raise MiniError("Choose a completed YouTube video, rather than a live stream")
            available = info.get("duration")
            if available and start >= available:
                raise MiniError("Video start must be before the end of the source video")
            complete = seconds is None or bool(available and seconds >= available - start)
            if not start and complete:
                # Native downloads parallelise fragments; FFmpeg remains for actual ranges
                downloader.params.pop("download_ranges", None)
                downloader.params.pop("external_downloader_args", None)
                if progress:
                    progress(None, f"Downloading {noun} · whole clip, up to 8 concurrent fragments")
            if progress and downloader.params.get("download_ranges"):
                watcher = Thread(target=watch, name="timey-download")
                watcher.start()
            info = downloader.process_ie_result(info, download=True)
    except DownloadError as exc:
        raise MiniError(f"YouTube download failed: {exc}") from exc
    finally:
        stopped.set()
        if watcher:
            watcher.join()
    if failures:
        raise failures[0]
    paths = [
        path
        for path in directory.glob("source.*")
        if path.suffix in {".mp4", ".webm", ".mkv", ".m4a", ".mp3", ".opus", ".ogg", ".wav", ".aac"}
    ]
    if not info or len(paths) != 1:
        raise MiniError("No completed video was downloaded; try a local video file")
    title = str(info.get("title") or "Timer")
    if cache:
        try:
            media_cache.save(cache, key, paths[0], title, start, seconds, complete)
        except OSError:
            if progress:
                progress(None, "Cache unavailable · using the completed download for this render")
    if progress:
        progress(
            1,
            f"{'Music' if audio else 'Background'} ready · {info.get('title') or paths[0].name}",
        )
    return paths[0], title


def suggest_style(title: str) -> str:
    """Suggest a game theme while leaving the final choice to the person"""
    # ponytail: title matching only, extend aliases if game titles need broader recognition
    title = title.casefold().replace("-", " ").replace("_", " ")
    return next((style for style in STYLES if style.replace("-", " ") in title), "minimal")


def require_ffmpeg() -> None:
    """Check native video tools before downloading or rendering"""
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise MiniError(f"Timey needs {tool} on PATH; install FFmpeg and run again")


def probe(source: Path) -> tuple[int, int, bool]:
    """Read video dimensions and audio presence without decoding the movie"""
    return _inspect(source)[:3]


def _inspect(source: Path) -> tuple[int, int, bool, float]:
    """Read the stream timeline as well as its displayed dimensions"""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(source.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MiniError(
            "The video could not be inspected within 30 seconds; try another file"
        ) from exc
    if result.returncode:
        raise MiniError(f"Cannot read this video: {result.stderr[-1500:]}")
    metadata = json.loads(result.stdout)
    streams = metadata.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not video or not video.get("width") or not video.get("height"):
        raise MiniError("The source does not contain a usable video stream")
    width, height = video["width"], video["height"]
    aspect = video.get("sample_aspect_ratio", "1:1")
    if aspect and aspect != "N/A":
        numerator, denominator = map(int, aspect.split(":"))
        if numerator and denominator:
            width = round(width * numerator / denominator)
    for item in video.get("side_data_list", []):
        if abs(item.get("rotation", 0)) % 180 == 90:
            width, height = height, width
    try:
        length = float(video.get("duration", metadata.get("format", {}).get("duration", 0)))
    except TypeError, ValueError:
        length = 0
    return (
        width,
        height,
        any(item.get("codec_type") == "audio" for item in streams),
        length if math.isfinite(length) and length > 0 else 0,
    )


# == Overlay artwork ==

PIXELS = (
    "01110/10001/10011/10101/11001/10001/01110",
    "00100/01100/00100/00100/00100/00100/01110",
    "01110/11011/00011/00110/01100/11000/11111",
    "11110/00011/00011/01110/00011/00011/11110",
    "00011/00111/01111/11011/11111/00011/00011",
    "11111/11000/11000/11110/00011/11011/01110",
    "01110/11000/11000/11110/11011/11011/01110",
    "11111/00011/00110/00110/01100/01100/01100",
    "01110/11011/11011/01110/11011/11011/01110",
    "01110/11011/11011/01111/00011/00011/01110",
)


def _font(kind: str, size: int, custom: str = ""):
    names = {
        "serif": (
            "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
            "georgiab.ttf",
            "DejaVuSerif-Bold.ttf",
        ),
        "mono": (
            "/System/Library/Fonts/Menlo.ttc",
            "consolab.ttf",
            "DejaVuSansMono-Bold.ttf",
        ),
        "sans": (
            "/System/Library/Fonts/Avenir Next.ttc",
            "calibrib.ttf",
            "DejaVuSans-Bold.ttf",
        ),
    }
    for candidate in (custom,) if custom else names[kind]:
        try:
            return ImageFont.truetype(str(Path(candidate).expanduser()), size)
        except OSError:
            if custom:
                raise MiniError(
                    "Cannot read the custom font; choose a valid TTF, OTF or TTC file"
                ) from None
    return ImageFont.load_default(size=size)


def placement(timer: Timer, width: int, height: int) -> tuple[int, int, float]:
    """Keep the HUD within a safe margin on landscape and portrait backgrounds"""
    margin = max(1, round(min(width, height) * 0.025))
    scale = min(
        min(width / (1000 if height > width else 1920), height / 1080) * timer.size,
        (width - margin * 2) / 540,
        (height - margin * 2) / 234,
    )
    panel_w, panel_h = round(540 * scale), round(234 * scale)
    x = margin if timer.position.endswith("left") else width - panel_w - margin
    y = height - panel_h - margin if timer.position.startswith("bottom") else margin
    if timer.position in {"centre", "bottom-centre"}:
        x = (width - panel_w) // 2
    if timer.position == "centre":
        y = (height - panel_h) // 2
    return x, y, scale


def _pixels(ink, digits: str, centre: int, top: int, pixel: int, colour: str, shadow: str) -> None:
    """Draw crisp bitmap numbers with one shadow pass before the foreground"""
    widths = [1 if char == ":" else 5 for char in digits]
    left = centre - (sum(widths) + 2 * (len(digits) - 1)) * pixel // 2
    cells = []
    for char in digits:
        rows = "0/1/0/0/1/0/0" if char == ":" else PIXELS[int(char)]
        for row, bits in enumerate(rows.split("/")):
            for column, bit in enumerate(bits):
                if bit == "1":
                    cells.append((left + column * pixel, top + row * pixel))
        left += (3 if char == ":" else 7) * pixel
    for a, b in cells:
        ink.rectangle((a + 4, b + 4, a + pixel + 3, b + pixel + 3), fill=shadow)
    for a, b in cells:
        ink.rectangle((a, b, a + pixel - 1, b + pixel - 1), fill=colour)


def _shapes(draw, artwork: dict) -> None:
    """Draw only validated vector primitives on the transparent panel"""
    for shape in artwork["shapes"]:
        points = [(round(x * 2), round(y * 2)) for x, y in shape["points"]]
        colour = shape["colour"]
        if shape["kind"] == "line":
            draw.line(points, fill=colour, width=shape["width"] * 2)
        elif shape["kind"] == "polygon":
            draw.polygon(points, fill=colour)
        elif shape["kind"] == "round":
            draw.rounded_rectangle(points, radius=shape["radius"] * 2, fill=colour)
        elif shape["kind"] == "ellipse":
            draw.ellipse(points, fill=colour)
        else:
            draw.rectangle(points, fill=colour)


def _temple_digits(height: int = 124) -> dict:
    """Slice the bundled numeral atlas once, preserving the colon's vertical position"""
    with Image.open((ASSETS / "timey/art") / "digits.png") as source:
        atlas = source.convert("RGBA")
    mask = atlas.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
    columns = mask.getprojection()[0]
    starts = [i for i, value in enumerate(columns) if value and (i == 0 or not columns[i - 1])]
    ends = [
        i + 1
        for i, value in enumerate(columns)
        if value and (i + 1 == len(columns) or not columns[i + 1])
    ]
    if len(starts) != 11:
        raise MiniError("The Temple Run numeral artwork is damaged; reinstall Timey")
    _, top, _, bottom = mask.getbbox()
    glyphs = {}
    for char, left, right in zip("0123456789:", starts, ends):
        glyph = atlas.crop((left - 3, top - 3, right + 3, bottom + 3))
        glyphs[char] = glyph.resize(
            (max(1, round(glyph.width / glyph.height * height * 1.35)), height),
            Image.Resampling.LANCZOS,
        )
    return glyphs


def frames(timer: Timer, width: int, height: int, *, preview: bool = False) -> Iterator[bytes]:
    """Stream small transparent PNGs at one frame per second with constant memory"""
    if Image is None:
        raise MiniError("Use uv run --extra timey mini timey to enable timer artwork")
    accent, base, kind = STYLES.get(timer.style, STYLES["minimal"])[1:]
    artwork = timer.artwork
    temple = timer.style == "temple-run" and not artwork
    labelled = bool(timer.label.strip())
    if artwork:
        kind = "mono" if artwork["font"] == "pixel" else artwork["font"]
    font = timer.font or (
        str((ASSETS / "timey/fonts") / f"{FONTS[timer.style]}.ttf")
        if not artwork and timer.style in FONTS
        else ""
    )
    accent = "#" + (timer.accent or accent).lstrip("#")
    base = "#" + base
    _, _, scale = placement(timer, width, height)
    panel_size = (max(1, round(540 * scale)), max(1, round(234 * scale)))
    digit_size = 124 if labelled else 170 if timer.seconds >= 3600 else 176
    digit_top = 212 if labelled else 356 - digit_size
    glyphs = (
        _temple_digits(max(1, round(digit_size * scale / 2))) if temple and not timer.font else None
    )
    texture = None
    plate = Image.new("RGBA", (1080, 468))
    draw = ImageDraw.Draw(plate)

    def rect(box, colour):
        draw.rectangle(tuple(round(value * 2) for value in box), fill=colour)

    def poly(points, colour):
        draw.polygon([(round(a * 2), round(b * 2)) for a, b in points], fill=colour)

    if not artwork and timer.style not in {"glass", "temple-run"}:
        rect((5, 7, 535, 231), (0, 0, 0, 110))
    if artwork:
        _shapes(draw, artwork)
        (left, top), (right, bottom) = artwork["bar"]["points"]
        rect((left, top, right, bottom), artwork["bar"]["background"])
    elif temple:
        with Image.open((ASSETS / "timey/art") / "plate.png") as stone:
            texture = stone.convert("RGBA").resize(panel_size, Image.Resampling.LANCZOS)
        draw.rounded_rectangle((210, 384, 870, 397), radius=5, fill="#10170B")
        draw.line((214, 398, 866, 398), fill="#9B9C70", width=1)
    elif timer.style == "minecraft":
        for inset, colour in ((0, "#111310"), (4, "#7A8074"), (9, "#3B4038")):
            rect((inset, inset, 530 - inset, 224 - inset), colour)
        rect((9, 9, 521, 14), "#BBC4B0")
        rect((9, 14, 14, 215), "#BBC4B0")
        rect((14, 210, 521, 215), "#20241E")
        rect((516, 14, 521, 210), "#20241E")
        # Familiar inventory slots, selected item and XP strip give the timer a real HUD rhythm
        for left in range(31, 498, 52):
            rect((left, 187, left + 48, 218), "#131612")
            rect((left + 2, 189, left + 46, 216), "#5C6256")
            rect((left + 4, 191, left + 44, 214), "#282D25")
        for inset, colour in ((0, "white"), (2, "#939B8D")):
            draw.rectangle(
                (
                    (239 + inset) * 2,
                    (185 + inset) * 2,
                    (291 - inset) * 2,
                    (220 - inset) * 2,
                ),
                outline=colour,
                width=3,
            )
        for left in (47, 99, 203, 307, 411):
            rect((left, 199, left + 4, 209), "#9F7A46")
            rect((left - 4, 195, left + 10, 199), "#5CE5CB")
            rect((left + 10, 199, left + 14, 202), "#2D9E89")
        heart = ("01100110", "11111111", "11111111", "01111110", "00111100", "00011000")
        for left in range(37, 178, 30):
            for row, bits in enumerate(heart):
                for column, bit in enumerate(bits):
                    if bit == "1":
                        a, b = left + column * 2, 22 + row * 2
                        rect((a, b, a + 2, b + 2), "#D54540")
            rect((left + 2, 24, left + 4, 26), "#F7A6A1")
        rect((258, 193, 272, 196), "#C6B89D")
        rect((258, 210, 272, 213), "#C6B89D")
        poly(
            [(260, 196), (270, 196), (267, 203), (270, 210), (260, 210), (263, 203)],
            "#E8D777",
        )
        rect((34, 174, 496, 179), "#151D11")
        for left in range(37, 495, 23):
            rect((left, 175, left + 17, 178), "#384C2C")
    elif timer.style == "subway-surfers":
        draw.rounded_rectangle((0, 0, 1060, 448), radius=44, fill="white")
        draw.rounded_rectangle((12, 12, 1048, 436), radius=34, fill=base)
        poly([(0, 15), (24, 0), (88, 0), (64, 24), (0, 24)], accent)
        poly([(442, 224), (466, 200), (530, 200), (506, 224)], accent)
        rect((34, 184, 496, 199), "#0B2849")
        for left in (27, 466):
            draw.ellipse(
                (left * 2, 53, (left + 31) * 2, 115),
                fill=accent,
                outline="#FF9C25",
                width=5,
            )
            draw.ellipse(((left + 6) * 2, 65, (left + 25) * 2, 103), outline="#FFF0A0", width=3)
        for left in range(84, 420, 58):
            poly(
                [(left, 207), (left + 21, 207), (left + 12, 219), (left - 9, 219)],
                "#257EB8",
            )
    elif timer.style == "neon":
        rect((0, 0, 530, 224), "#7561BF")
        rect((3, 3, 527, 221), base)
        rect((0, 0, 120, 4), accent)
        rect((526, 104, 530, 224), accent)
        rect((34, 184, 496, 194), "#302A46")
    elif timer.style == "glass":
        draw.rounded_rectangle((0, 0, 1060, 448), radius=56, fill=(18, 27, 40, 132))
        draw.rounded_rectangle((1, 1, 1059, 447), radius=56, outline=(235, 245, 255, 100), width=2)
        draw.rounded_rectangle((8, 8, 1052, 440), radius=50, outline=(235, 245, 255, 28), width=2)
        rect((34, 184, 496, 187), (215, 234, 255, 40))
    else:
        draw.rounded_rectangle((0, 0, 1060, 448), radius=24, fill=(22, 27, 32, 232))
        rect((0, 18, 4, 206), accent)
        rect((34, 184, 496, 187), "#4A5157")
    label_spec = artwork["text"]["label"] if artwork else None
    timer_spec = artwork["text"]["timer"] if artwork else None
    caption_spec = artwork["text"]["caption"] if artwork else None
    label_font = _font(kind, label_spec["size"] * 2 if artwork else 24 if temple else 36, font)
    caption_font = _font(kind, caption_spec["size"] * 2 if artwork else 30 if temple else 26, font)
    # Keep custom labels inside the panel even when the chosen font has wide glyphs
    label = timer.label.upper() if timer.style in FONTS and not artwork else timer.label
    centre = label_spec["point"][0] if artwork else 270 if temple else 265
    while len(label) > 1 and draw.textlength(label, font=label_font) > (
        760 if temple else min(centre, 540 - centre) * 4 - 32
    ):
        label = label[:-2] + "…"
    draw.text(
        tuple(round(n * 2) for n in label_spec["point"])
        if artwork
        else (540, 182)
        if temple
        else (530, 98),
        label,
        font=label_font,
        fill=(accent if timer.accent else label_spec["colour"])
        if artwork
        else "#D9D6B2"
        if temple
        else accent,
        anchor="mt",
        stroke_width=label_spec["stroke"] * 2 if artwork else 0,
        stroke_fill=label_spec["outline"] if artwork else base,
    )
    centre = timer_spec["point"][0] if artwork else 270 if temple else 265
    if glyphs:
        advance = max(glyph.width for glyph in glyphs.values()) + round(18 * scale / 2)
        colon = glyphs[":"].width + round(12 * scale / 2)
    else:
        digit_font = _font(
            kind,
            timer_spec["size"] * 2
            if artwork
            else digit_size + 18
            if temple
            else (216 if timer.seconds < 3600 else 166)
            if not labelled
            else 148
            if timer.seconds < 3600
            else 116,
            font,
        )
        widest = "88:88:88" if timer.seconds >= 3600 else "88:88"
        while digit_font.size > 2 and max(digit_font.getlength(char) for char in "0123456789") * (
            len(widest) - widest.count(":")
        ) + digit_font.getlength(":") * widest.count(":") > (
            740 if temple else min(centre, 540 - centre) * 4 - 40
        ):
            digit_font = digit_font.font_variant(size=digit_font.size - 2)
        advance = max(digit_font.getlength(char) for char in "0123456789")
        colon = digit_font.getlength(":")

    def lettering(ink, digits, point, **options):
        # Fixed numeral cells keep the countdown steady even with proportional display fonts
        left = point[0] - sum(colon if char == ":" else advance for char in digits) / 2
        for char in digits:
            step = colon if char == ":" else advance
            ink.text(
                (left + step / 2, point[1]),
                char,
                font=digit_font,
                anchor="mt",
                **options,
            )
            left += step

    states = (
        [(timer.seconds, "Time remaining")]
        if preview
        else chain(
            repeat((timer.seconds, "Get ready"), timer.start_gap),
            ((remaining, "Time remaining") for remaining in range(timer.seconds, 0, -1)),
            repeat((0, "Time's up"), timer.end_gap),
        )
    )
    previous, encoded = None, b""
    for remaining, caption in states:
        if (remaining, caption) != previous:
            canvas = plate.copy()
            ink = ImageDraw.Draw(canvas)
            digits = clock(remaining, hours=timer.seconds >= 3600)
            if (
                not glyphs
                and (timer.style == "minecraft" or artwork and artwork["font"] == "pixel")
                and not timer.font
            ):
                size = (
                    timer_spec["size"] * 2
                    if artwork
                    else (196 if len(digits) <= 5 else 140)
                    if not labelled
                    else 126
                    if len(digits) <= 5
                    else 91
                )
                cells = sum(1 if char == ":" else 5 for char in digits) + 2 * (len(digits) - 1)
                pixel = max(
                    1,
                    min(size // 7, round((min(centre, 540 - centre) * 4 - 32) / cells)),
                )
                _pixels(
                    ink,
                    digits,
                    round(centre * 2),
                    round(timer_spec["point"][1] * 2) if artwork else 124 if not labelled else 160,
                    pixel,
                    timer_spec["colour"] if artwork else "white",
                    timer_spec["outline"] if artwork else "#111310",
                )
            elif not glyphs:
                point = (
                    tuple(round(n * 2) for n in timer_spec["point"])
                    if artwork
                    else (540, digit_top)
                    if temple
                    else (530, 120)
                    if not labelled
                    else (530, 160)
                )
                if timer.style == "subway-surfers" and not artwork:
                    lettering(
                        ink,
                        digits,
                        (point[0] + 5, point[1] + 7),
                        fill="#167AC5",
                        stroke_width=8,
                        stroke_fill="#061F3A",
                    )
                elif temple:
                    lettering(
                        ink,
                        digits,
                        (point[0] + 2, point[1] + 5),
                        fill="#6C431A",
                        stroke_width=3,
                        stroke_fill="#0F0C07",
                    )
                lettering(
                    ink,
                    digits,
                    point,
                    fill=timer_spec["colour"] if artwork else "#FFF2CE" if temple else "white",
                    stroke_width=timer_spec["stroke"] * 2
                    if artwork
                    else 3
                    if timer.style == "subway-surfers"
                    else 1,
                    stroke_fill=timer_spec["outline"] if artwork else base,
                )
            if caption != "Time remaining":
                if temple:
                    ink.rounded_rectangle(
                        (210, 376, 870, 408),
                        radius=5,
                        fill="#11170E",
                        outline="#737A52",
                        width=2,
                    )
                ink.text(
                    tuple(round(n * 2) for n in caption_spec["point"])
                    if artwork
                    else (540, 392)
                    if temple
                    else (530, 302 if labelled else 84),
                    caption.upper() if temple else caption,
                    font=caption_font,
                    fill=caption_spec["colour"] if artwork else "#E3C985" if temple else accent,
                    anchor="mm" if temple else "mt",
                    stroke_width=caption_spec["stroke"] * 2 if artwork else 1 if temple else 0,
                    stroke_fill=caption_spec["outline"] if artwork else base,
                )
            length = round(454 * remaining / timer.seconds)
            if artwork:
                (left, top), (right, bottom) = artwork["bar"]["points"]
                segments = artwork["bar"]["segments"]
                fraction = remaining / timer.seconds
                for index in range(segments):
                    start = left + (right - left) * index / segments
                    end = min(
                        left + (right - left) * fraction,
                        left + (right - left) * (index + 1) / segments - (2 if segments > 1 else 0),
                    )
                    if end > start:
                        ink.rectangle(
                            (
                                round(start * 2),
                                round(top * 2),
                                round(end * 2),
                                round(bottom * 2),
                            ),
                            fill=accent if timer.accent else artwork["bar"]["colour"],
                        )
            elif timer.style == "minecraft":
                for left in range(37, 37 + length, 23):
                    ink.rectangle(
                        (left * 2, 350, min(left + 17, 37 + length) * 2, 356),
                        fill=accent,
                    )
            elif temple:
                if remaining and caption == "Time remaining":
                    end = 213 + round(654 * remaining / timer.seconds)
                    ink.rounded_rectangle((213, 386, end, 395), radius=3, fill=accent)
                    ink.line((216, 387, max(216, end), 387), fill="#D4F49A")
            elif length:
                ink.rectangle(
                    (
                        76,
                        372,
                        (38 + length) * 2,
                        374 if timer.style in {"minimal", "glass"} else 388,
                    ),
                    fill=accent,
                )
            canvas = canvas.resize(
                panel_size,
                Image.Resampling.NEAREST
                if timer.style == "minecraft" or artwork and artwork["font"] == "pixel"
                else Image.Resampling.LANCZOS,
            )
            if glyphs:
                left = (
                    canvas.width - sum(colon if char == ":" else advance for char in digits)
                ) // 2
                for char in digits:
                    step = colon if char == ":" else advance
                    glyph = glyphs[char]
                    canvas.alpha_composite(
                        glyph, (left + (step - glyph.width) // 2, round(digit_top * scale / 2))
                    )
                    left += step
            if texture is not None:
                canvas = Image.alpha_composite(texture, canvas)
            with BytesIO() as buffer:
                canvas.save(buffer, format="PNG", compress_level=1)
                encoded = buffer.getvalue()
            previous = remaining, caption
        yield encoded


def _encode(
    argv: list[str],
    work: Path,
    seconds: float,
    title: str,
    progress: Progress | None,
    images: Iterator[bytes] | None = None,
) -> None:
    """Run native encoding with bounded logs, real progress and cancellation cleanup"""
    stopped, failures = Event(), []
    with (work / "error.log").open("w+b") as errors:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if images else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=errors,
        )

        def feed() -> None:
            try:
                for image in images:
                    if stopped.is_set():
                        break
                    process.stdin.write(image)
            except BrokenPipeError:
                pass
            except Exception as exc:
                failures.append(exc)
            finally:
                try:
                    process.stdin.close()
                except OSError as exc:
                    # Windows reports EINVAL when cancelled FFmpeg closes its input pipe
                    if exc.errno != EPIPE and not (stopped.is_set() and exc.errno == EINVAL):
                        failures.append(exc)

        writer = Thread(target=feed, name="timey-overlay") if images else None
        if writer:
            writer.start()
        try:
            state = {}
            if progress:
                progress(0, f"{title} · starting FFmpeg")
            for line in process.stdout:
                key, _, value = line.decode("utf-8", errors="replace").strip().partition("=")
                state[key] = value
                if key == "progress" and progress:
                    try:
                        elapsed = max(0, float(state.get("out_time_us", 0)) / 1_000_000)
                    except ValueError:
                        continue
                    detail = f"{clock(round(elapsed))} / {clock(math.ceil(seconds))} · frame {state.get('frame', '?')} · {state.get('fps', '?')} fps · {state.get('speed', '?')} speed"
                    progress(min(1, elapsed / seconds), f"{title} · {detail}")
            status = process.wait()
            if writer:
                writer.join()
            if failures:
                raise failures[0]
            if status:
                errors.seek(0, 2)
                errors.seek(max(0, errors.tell() - 2500))
                raise MiniError(
                    f"FFmpeg could not render this video: {errors.read().decode('utf-8', errors='replace')}"
                )
            if progress:
                progress(1, f"{title} · complete")
        finally:
            stopped.set()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if writer:
                writer.join()
            process.stdout.close()


def _loop(
    source: Path,
    work: Path,
    length: float,
    blend: float,
    width: int,
    height: int,
    fps: int,
    audio: bool,
    progress: Progress | None,
    start: int = 0,
) -> Path:
    """Prepare one cyclic clip, blending its tail into its head without growing with timer length"""
    # Quantise both the cycle and overlap to output frames to avoid repeated-frame seams
    length = math.floor(length * fps + 0.001) / fps
    blend = math.floor(min(blend, length / 4) * fps) / fps
    if blend < 1 / fps and not start:
        return source
    target = work / "loop.mp4"
    video = f"scale={width}:{height},setsar=1,fps={fps},settb=AVTB"
    filters = (
        f"[0:v:0]{video},trim=start={blend}:end={length},setpts=PTS-STARTPTS[body];"
        f"[1:v:0]{video},trim=duration={blend},setpts=PTS-STARTPTS[head];"
        f"[body][head]xfade=transition=fade:duration={blend}:offset={length - 2 * blend},"
        f"trim=duration={length - blend},format=yuv420p[v]"
    )
    if audio:
        filters += (
            f";[0:a:0]aresample=48000,atrim=start={blend}:end={length},asetpts=PTS-STARTPTS,"
            f"apad,atrim=duration={length - blend}[sound];"
            f"[1:a:0]aresample=48000,atrim=duration={blend},asetpts=PTS-STARTPTS,"
            f"apad,atrim=duration={blend}[intro];"
            f"[sound][intro]acrossfade=d={blend}:c1=tri:c2=tri[a]"
        )
    if blend < 1 / fps:
        filters = f"[0:v:0]{video},trim=duration={length},setpts=PTS-STARTPTS,format=yuv420p[v]"
        if audio:
            filters += f";[0:a:0]aresample=48000,atrim=duration={length},asetpts=PTS-STARTPTS[a]"
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(start),
        "-i",
        str(source),
    ]
    if blend >= 1 / fps:
        argv += ["-ss", str(start), "-t", str(blend), "-i", str(source)]
    argv += [
        "-filter_complex",
        filters,
        "-map",
        "[v]",
        "-t",
        str(length - blend),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "16",
    ]
    argv += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"] if audio else ["-an"]
    argv += ["-progress", "pipe:1", "-nostats", str(target)]
    _encode(
        argv,
        work,
        length - blend,
        f"Smoothing the loop · {blend:g}s crossfade",
        progress,
    )
    return target


def _surface(first: bytes, timer: Timer, work: Path) -> tuple[Path, Path]:
    """Make a rounded blur mask and an edge-only highlight from the panel silhouette"""
    with Image.open(BytesIO(first)) as panel:
        alpha = panel.getchannel("A")
        temple = timer.style == "temple-run" and not timer.artwork
        if temple:
            red, green, _, _ = panel.split()
            gems = ImageChops.subtract(green, red).point(lambda value: min(255, value * 4))
            gems = ImageChops.multiply(gems, alpha)
            # Only the gems catch light; the live progress strip must not leave a ghost
            ImageDraw.Draw(gems).rectangle(
                (panel.width * 0.1, panel.height * 0.2, panel.width * 0.9, panel.height),
                fill=0,
            )
    mask = alpha.point(lambda value: 255 if value >= (32 if timer.style == "glass" else 128) else 0)
    mask_path, edge_path = work / "mask.png", work / "edge.png"
    mask.save(mask_path)
    inset = max(1, round(mask.height / 100))
    padded = Image.new("L", (mask.width + inset * 2, mask.height + inset * 2))
    padded.paste(mask, (inset, inset))
    eroded = padded.filter(ImageFilter.MinFilter(inset * 2 + 1)).crop(
        (inset, inset, mask.width + inset, mask.height + inset)
    )
    edge = ImageChops.subtract(mask, eroded)
    if temple:
        edge = ImageChops.lighter(edge, gems)
    # Custom artwork can contain holes; keep any animated light outside the text area
    ink = ImageDraw.Draw(edge)
    ink.rectangle(
        (mask.width * 0.1, mask.height * 0.2, mask.width * 0.9, mask.height * 0.8),
        fill=0,
    )
    accent = (
        "#E1E6B9"
        if temple
        else "#" + (timer.accent or STYLES.get(timer.style, STYLES["minimal"])[1]).lstrip("#")
    )
    rim = Image.new("RGBA", mask.size, accent)
    rim.putalpha(edge)
    rim.save(edge_path)
    return mask_path, edge_path


def render(
    source: Path,
    output: Path,
    timer: Timer,
    *,
    preview: bool = False,
    sample: bool = False,
    height: int = 1080,
    fps: int = 30,
    mute: bool = False,
    force: bool = False,
    progress: Progress | None = None,
    music: Path | None = None,
    music_volume: float = 1.0,
    mix_audio: bool = False,
    start: int = 0,
) -> Path:
    """Publish a completed timer or a bounded six-second sample with the actual clock"""
    require_ffmpeg()
    if type(start) is not int or not 0 <= start <= 2**31 - 1:
        raise MiniError("Video start must be a non-negative timestamp")
    if sample and preview:
        raise MiniError("Choose a still preview or a motion sample")
    if sample:
        timer = replace(timer, start_gap=min(timer.start_gap, 1))
    length = min(timer.total, 6) if sample else timer.total
    source, output = source.expanduser().resolve(), output.expanduser().absolute()
    if output.is_symlink() or source == output.resolve():
        raise MiniError("Output must not be a symlink or overwrite the source video")
    if output.suffix.lower() != (".png" if preview else ".mp4"):
        raise MiniError("Use .png for a preview or .mp4 for a rendered timer")
    if height not in {480, 720, 1080, 1440, 2160} or fps not in {24, 30, 60}:
        raise MiniError("Choose 480/720/1080/1440/2160p and 24/30/60 fps")
    if not math.isfinite(music_volume) or not 0 <= music_volume <= 2:
        raise MiniError("Music volume must be between 0 and 2")
    ensure_outputs([output], force=force)
    if progress:
        progress(None, "Grokking the video · inspecting dimensions and audio")
    width, source_height, audio, source_length = _inspect(source)
    if start and (not source_length or start >= source_length):
        raise MiniError("Video start must be before the end of a source with a known duration")
    source_length = max(0, source_length - start)
    if music and not preview:
        music = music.expanduser().resolve()
        if not music.is_file() or music == output.resolve():
            raise MiniError(
                "Music must be an existing file and must not be overwritten by the output"
            )
        try:
            inspection = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    str(music),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MiniError(
                "The music could not be inspected within 30 seconds; try another file"
            ) from exc
        if inspection.returncode or not inspection.stdout.strip():
            raise MiniError("The music source does not contain a usable audio stream")
    factor = min(1, height / source_height)
    width, canvas_height = (
        max(2, int(width * factor) // 2 * 2),
        max(2, int(source_height * factor) // 2 * 2),
    )
    x, y, scale = placement(timer, width, canvas_height)
    if progress:
        progress(
            None,
            f"Crafting the timer · {timer.style}, {width} × {canvas_height}, {fps} fps",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".timey-", dir=output.parent) as scratch:
        work = Path(scratch)
        target = work / ("preview.png" if preview else "timer.mp4")
        if not preview and (timer.loop_blend or start) and source_length and source_length < length:
            original = source
            source = _loop(
                source,
                work,
                source_length,
                timer.loop_blend,
                width,
                canvas_height,
                fps,
                audio and not mute and (not music or mix_audio),
                progress,
                start,
            )
            if source != original:
                start = 0
        elif not preview and timer.loop_blend and not source_length and progress:
            progress(None, "Loop duration unavailable · repeating without a crossfade")
        images = frames(timer, width, canvas_height, preview=preview)
        first = next(images)
        argv = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-stream_loop",
            "-1",
            "-ss",
            str(start),
            "-i",
            str(source),
            "-thread_queue_size",
            "8",
            "-f",
            "image2pipe",
            "-framerate",
            "1",
            "-vcodec",
            "png",
            "-i",
            "pipe:0",
        ]
        filters = f"[0:v:0]scale={width}:{canvas_height},setsar=1,fps={fps}[bg]"
        panel = "1:v:0"
        if timer.motion and not preview:
            half = round(fps * 0.08)
            weights = " ".join(str(n) for n in chain(range(1, half + 2), range(half, 0, -1)))
            # A short eased dissolve changes only the pixels that differ between seconds
            filters += (
                f";[1:v:0]fps={fps},format=gbrap,premultiply=inplace=1,"
                f"tmix=frames={half * 2 + 1}:weights='{weights}',unpremultiply=inplace=1[timer]"
            )
            panel = "timer"
        index = 2
        if music and not preview:
            argv += ["-stream_loop", "-1", "-i", str(music)]
            index += 1
            fade = min(2, length / 2)
            filters += f";[2:a:0]volume={music_volume},afade=t=in:st=0:d={fade},afade=t=out:st={length - fade}:d={fade}[music]"
            if mix_audio and audio and not mute:
                filters += ";[0:a:0][music]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[mix]"
        if timer.style == "glass" or timer.motion and not preview:
            mask, edge = _surface(first, timer, work)
            panel_w, panel_h = round(540 * scale), round(234 * scale)
            if timer.style == "glass":
                argv += ["-loop", "1", "-framerate", str(fps), "-i", str(mask)]
                filters += (
                    f";[bg]split[scene][behind];[behind]crop={panel_w}:{panel_h}:{x}:{y}:exact=1,"
                    f"gblur=sigma={max(1, 12 * scale):g},format=yuv420p[blur];"
                    f"[blur][{index}:v:0]alphamerge[frost];"
                    f"[scene][frost]overlay={x}:{y}:eof_action=repeat[bg]"
                )
                index += 1
            if timer.motion and not preview:
                argv += ["-loop", "1", "-framerate", str(fps), "-i", str(edge)]
                light = (
                    "0.36*exp(-pow((X/W-(mod(T,12)-1)/1.4)/0.14,2))"
                    "*between(mod(T,12),0.8,2.8)"
                    f"+0.16*exp(-pow((T-{timer.start_gap})/0.35,2))"
                    f"+0.16*exp(-pow((T-{timer.start_gap + timer.seconds})/0.35,2))"
                )
                filters += (
                    f";[{index}:v:0]format=yuva420p,geq=lum='lum(X,Y)':cb='cb(X,Y)':"
                    f"cr='cr(X,Y)':a='if(gt(alpha(X,Y),0),alpha(X,Y)*({light}),0)'[shine];"
                    f"[bg][{panel}]overlay={x}:{y}:eof_action=repeat[panel];"
                    f"[panel][shine]overlay={x}:{y}:eof_action=repeat[v]"
                )
            else:
                filters += f";[bg][{panel}]overlay={x}:{y}:eof_action=repeat[v]"
        else:
            filters += f";[bg][{panel}]overlay={x}:{y}:eof_action=repeat[v]"
        argv += ["-filter_complex", filters, "-map", "[v]"]
        if preview:
            argv += ["-frames:v", "1", "-an"]
        else:
            argv += [
                "-t",
                str(length),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
            ]
            if music:
                argv += [
                    "-map",
                    "[mix]" if mix_audio and audio and not mute else "[music]",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "160k",
                ]
            else:
                argv += (
                    ["-an"]
                    if mute or not audio
                    else ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k", "-af", "apad"]
                )
        argv += ["-progress", "pipe:1", "-nostats", str(target)]
        try:
            _encode(
                argv,
                work,
                length,
                "Drawing your preview" if preview else "Rendering the timer",
                progress,
                chain((first,), islice(images, length - 1) if sample else images),
            )
            if progress:
                progress(None, "Finishing the video · saving the completed export")
        finally:
            images.close()
        ensure_outputs([output], force=force)
        target.replace(output)
    if progress:
        progress(
            1,
            "Preview ready"
            if preview
            else "Motion preview ready"
            if sample
            else f"Timer ready · {output.stat().st_size / 1048576:.1f} MiB saved",
        )
    return output


def reference(source: Path, output: Path, *, start: int = 0, size: int = 960) -> None:
    """Give the style designer one small background frame without a full preview render"""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-y",
                "-ss",
                str(start),
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                f"scale={size}:{size}:force_original_aspect_ratio=decrease",
                "-q:v",
                "2",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MiniError("The background reference could not be drawn within 30 seconds") from exc
    if result.returncode:
        raise MiniError(f"Cannot make the background reference: {result.stderr[-1000:]}")
