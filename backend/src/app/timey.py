"""Browser countdowns using the same renderer, design and publication tools as the CLI

The browser shares timer configuration, cached media and FFmpeg rendering
with the CLI. Input requests own their cancellation and temporary outputs;
preview and draft preparation do not publish a video to YouTube
"""

import hashlib
import json
import math
import re
import shutil
from collections.abc import AsyncIterable
from dataclasses import replace
from io import BytesIO
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore, Event
from time import time
from typing import Any, cast
from urllib.parse import parse_qs, quote_plus, urlsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from uq_minis.app.collab import router as collaboration
from uq_minis.app.core import Workspace, cancellation, page, value, workspace
from uq_minis.core import cache as files
from uq_minis.core.common import MiniError, atomic_json
from uq_minis.core.paths import CACHE, STATE

router = APIRouter()
router.include_router(collaboration)
RENDER = BoundedSemaphore(1)
PREVIEW = BoundedSemaphore(1)
MEDIA = BoundedSemaphore(1)
PUBLISH = BoundedSemaphore(1)
UPLOAD_LIMIT = 512 * 1024**2


def _youtube(source: str) -> bool:
    """Recognise the canonical remote source before requiring its provider session"""
    from uq_minis.minis import timey

    try:
        timey.youtube_url(source)
        return True
    except MiniError:
        return False


def _google() -> Path:
    """Require the private Google session shared by Timey's YouTube operations"""
    from uq_minis.minis.timey import connect

    return connect.require()


def _source(form: FormData, context: Workspace, field: str = "source") -> str:
    """Resolve only uploads registered by this browser workspace"""
    source = value(form, field)
    if source.startswith("upload:"):
        path = context.download(source.removeprefix("upload:"))
        if path is None or not path.is_file():
            raise MiniError("This uploaded media is no longer cached; choose it again")
        return str(path)
    return source


def _show(request: Request, **results: object) -> dict[str, object]:
    fields: list[dict[str, Any]] = [
        {"name": "source", "label": "YouTube link or local video path"},
        {"name": "length", "label": "Countdown length", "value": "10m"},
        {
            "name": "style",
            "label": "Look",
            "type": "select",
            "options": [
                (name, name.replace("-", " ").title())
                for name in (
                    "auto",
                    "minimal",
                    "minecraft",
                    "temple-run",
                    "subway-surfers",
                    "neon",
                    "glass",
                )
            ],
        },
        {
            "name": "action",
            "label": "Create",
            "type": "select",
            "options": [
                ("preview", "Still preview"),
                ("sample", "Short motion preview"),
                ("render", "Finished timer video"),
                ("search", "Find background videos"),
                ("upload", "Upload a reviewed MP4"),
            ],
        },
        {"name": "query", "label": "Search YouTube", "when": {"action": ["search"]}},
        {"name": "start", "label": "Background start timestamp", "value": "0"},
        {"name": "start_gap", "label": "Get-ready time", "value": "5s"},
        {"name": "end_gap", "label": "Finishing hold", "value": "5s"},
        {"name": "label", "label": "Countdown label · optional", "maxLength": 32},
        {
            "name": "position",
            "label": "Timer position",
            "type": "select",
            "value": "centre",
            "options": [
                (name, name.replace("-", " ").title())
                for name in (
                    "centre",
                    "top-left",
                    "top-right",
                    "bottom-left",
                    "bottom-right",
                    "bottom-centre",
                )
            ],
            "group": "Make it yours",
        },
        {
            "name": "size",
            "label": "Timer size",
            "type": "range",
            "value": 2.4,
            "min": 0.5,
            "max": 3,
            "step": 0.1,
            "group": "Make it yours",
        },
        {
            "name": "accent",
            "label": "Accent colour",
            "type": "color",
            "value": "#8fda53",
            "group": "Make it yours",
        },
        {
            "name": "use_accent",
            "label": "Use my accent colour",
            "type": "checkbox",
            "group": "Make it yours",
        },
        {
            "name": "font",
            "label": "Font file or Google Fonts link",
            "group": "Make it yours",
        },
        {
            "name": "motion",
            "label": "Digit changes",
            "type": "select",
            "options": [("on", "Smooth movement"), ("off", "Still digits")],
            "group": "Make it yours",
        },
        {
            "name": "loop_blend",
            "label": "Smooth video repeats · seconds",
            "type": "range",
            "min": 0,
            "max": 2,
            "step": 0.1,
            "value": 0.6,
            "group": "Make it yours",
        },
        {
            "name": "custom_style",
            "label": "Saved style name or JSON path",
            "group": "Design an overlay",
        },
        {
            "name": "instructions",
            "label": "Describe your custom overlay",
            "type": "textarea",
            "maxLength": 4000,
            "group": "Design an overlay",
        },
        {
            "name": "designer",
            "label": "Signed-in designer",
            "type": "select",
            "options": [(name, name.title()) for name in ("auto", "codex", "claude")],
            "group": "Design an overlay",
        },
        {
            "name": "music",
            "label": "Music link or local audio/video path",
            "group": "Sound",
        },
        {
            "name": "music_volume",
            "label": "Music volume",
            "type": "range",
            "min": 0,
            "max": 2,
            "step": 0.05,
            "value": 1,
            "group": "Sound",
        },
        {
            "name": "mix_audio",
            "label": "Keep original audio alongside the music",
            "type": "checkbox",
            "group": "Sound",
        },
        {
            "name": "mute",
            "label": "Mute the background",
            "type": "checkbox",
            "group": "Sound",
        },
        {
            "name": "height",
            "label": "Maximum height · 0 keeps original quality",
            "type": "number",
            "value": 0,
            "min": 0,
            "group": "Export settings",
        },
        {
            "name": "fps",
            "label": "Frames per second",
            "type": "select",
            "value": 30,
            "options": [(n, str(n)) for n in (24, 30, 60)],
            "group": "Export settings",
        },
        {
            "name": "no_cache",
            "label": "Download fresh media for this run",
            "type": "checkbox",
            "group": "Export settings",
        },
        {
            "name": "metadata",
            "label": "Prepare editable video title, description and tags",
            "type": "checkbox",
            "group": "Publication draft",
        },
        {
            "name": "metadata_instructions",
            "label": "Writing notes",
            "type": "textarea",
            "maxLength": 4000,
            "group": "Publication draft",
        },
        {
            "name": "details",
            "label": "Reviewed YouTube details JSON path",
            "when": {"action": ["upload"]},
        },
        {
            "name": "confirm",
            "label": "I reviewed this MP4 and its publication details and authorise this upload",
            "type": "checkbox",
            "when": {"action": ["upload"]},
        },
    ]
    for field in fields:
        if field["name"] != "action" and "when" not in field:
            field["when"] = {
                "action": [
                    "preview",
                    "sample",
                    "render",
                    *(["upload"] if field["name"] == "source" else []),
                ]
            }
    return page(
        request,
        "timey",
        fields=fields,
        submit="Make my timer",
        note="Try a preview first. Full videos use the same settings as the preview. Uploading is a separate action after reviewing the video and its editable publication draft",
        **results,
    )


@router.get("/api/minis/timey")
def home(request: Request) -> dict[str, object]:
    """Offer the renderer without requiring the terminal wizard"""
    return _show(request)


def _timer(form: FormData, artwork: dict[str, Any] | None = None) -> Any:
    """Use one validated timer configuration for live previews and final renders"""
    from uq_minis.minis import timey

    style = value(form, "style", "minimal")
    custom = value(form, "custom_style")
    if artwork is None and custom:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", custom):
            raise MiniError("Choose a saved timer by name, rather than a file path")
        path = STATE / "timey/styles" / f"{custom}.json"
        if path.is_symlink():
            raise MiniError("This saved timer cannot be opened; create a new look")
        artwork = timey.read_style(path)
    return timey.Timer(
        seconds=timey.duration(value(form, "length", "10m")),
        start_gap=timey.duration(value(form, "start_gap", "5s")),
        end_gap=timey.duration(value(form, "end_gap", "5s")),
        style=artwork["name"] if artwork else "minimal" if style == "auto" else style,
        position=value(form, "position", "centre"),
        label=value(form, "label"),
        accent=value(form, "accent") if value(form, "use_accent") == "on" else "",
        size=float(value(form, "size", "2.4")),
        x=float(value(form, "x")) if value(form, "x") else None,
        y=float(value(form, "y")) if value(form, "y") else None,
        width=float(value(form, "overlay_width")) if value(form, "overlay_width") else None,
        height=float(value(form, "overlay_height")) if value(form, "overlay_height") else None,
        motion=value(form, "motion", "on") == "on",
        loop_blend=float(value(form, "loop_blend", "0.6")),
        artwork=artwork,
        font=timey.font(value(form, "font"), STATE / "timey/fonts") if value(form, "font") else "",
    )


def _process(request: Request, form: FormData, context: Workspace) -> dict[str, object]:
    from uq_minis.minis import timey
    from uq_minis.minis.timey import youtube

    action = value(form, "action", "preview")
    if action not in {"search", "preview", "sample", "render", "upload"}:
        raise MiniError("Choose a listed timer action")
    if action == "search":
        rows = timey.search(value(form, "query"), cookies=_google())
        return _show(
            request,
            rows=rows,
            columns=["title", "length", "url"],
            result=f"Found {len(rows)} background videos",
        )
    if action == "upload":
        if not request.app.state.identity.user(request):
            raise HTTPException(401, "Sign in with UQ before uploading")
        if value(form, "confirm") != "on":
            raise MiniError("Review the MP4 and its details, then explicitly authorise this upload")
        link = youtube.upload(
            Path(value(form, "source")),
            Path(value(form, "details")),
            STATE / "timey/client_secret.json",
            STATE / "timey/youtube.json",
        )
        return _show(request, result=f"Uploaded to {link}")
    if not RENDER.acquire(blocking=False):
        raise MiniError("Another timer is rendering; wait for it to finish")
    try:
        timey.require_ffmpeg()
        work = context.directory("timey")
        style = value(form, "style", "minimal")
        timer = _timer(FormData({**form, "font": _source(form, context, "font")}))
        artwork = timer.artwork
        height, fps = int(value(form, "height", "0")), int(value(form, "fps", "30"))
        if height != 0 and height < 240 or fps not in {24, 30, 60}:
            raise MiniError(
                "Choose a height of at least 240p (0 keeps the source) and 24/30/60 fps"
            )
        music_volume = float(value(form, "music_volume", "1"))
        if not 0 <= music_volume <= 2:
            raise MiniError("Music volume must be between 0 and 2")
        if action != "render" and (
            value(form, "metadata") == "on" or value(form, "first_frame") == "on"
        ):
            raise MiniError("Publication drafts and thumbnails need a finished timer video")
        start = timey.duration(value(form, "start", "0"))
        if start > 2**31 - 1:
            raise MiniError("The background start timestamp is too large")
        cache = None if value(form, "no_cache") == "on" else CACHE / "timey/media"
        length = (
            1
            if action == "preview"
            else min(timer.total, 10)
            if action == "sample"
            else timer.total
        )
        origin = _source(form, context)
        local = Path(origin).expanduser().is_file()
        if _youtube(origin):
            _google()
        source, title = timey.download(
            origin, work, seconds=length, height=height, start=start, cache=cache
        )
        downloads: list[dict[str, str]] = []
        designed: dict[str, str] | None = None
        if value(form, "instructions"):
            background = work / "background.png"
            timey.reference(source, background, start=start if local else 0)
            from uq_minis.minis.timey.style import discuss

            questions, artwork, saved = discuss(
                value(form, "instructions"),
                STATE / "timey/styles",
                name=value(form, "design_name"),
                background=background,
                context=title,
                base=artwork,
            )
            if questions:
                return _show(
                    request,
                    result="A little more detail will help shape your timer",
                    questions=questions,
                )
            if artwork is None or saved is None:
                raise MiniError("The designer didn't return a look; your brief is still here")
            timer = replace(timer, style=artwork["name"], artwork=artwork)
            downloads.append(context.publish(saved))
            designed = {"id": saved.stem, "name": artwork["name"]}
        elif style == "auto" and not artwork:
            timer = replace(timer, style=timey.suggest_style(title))
        music = None
        if value(form, "music") and action != "preview":
            music_source = _source(form, context, "music")
            if _youtube(music_source):
                _google()
            music, _ = timey.download(
                music_source,
                work / "music",
                seconds=length,
                height=height,
                cache=cache,
                audio=True,
            )
        output = timey.render(
            source,
            work / ("preview.png" if action == "preview" else "timer.mp4"),
            timer,
            preview=action == "preview",
            sample=action == "sample",
            height=height,
            fps=fps,
            mute=value(form, "mute") == "on",
            start=start if local else 0,
            music=music,
            music_volume=music_volume,
            mix_audio=value(form, "mix_audio") == "on",
        )
        result = context.publish(output)
        downloads.append(result)
        if value(form, "metadata") == "on" or value(form, "first_frame") == "on":
            draft_context = {
                "countdown_seconds": timer.seconds,
                "start_gap": timer.start_gap,
                "end_gap": timer.end_gap,
                "total_seconds": timer.total,
                "style": timer.style,
                "video_title": title,
                "instructions": value(form, "metadata_instructions"),
                "source_url": "" if local else timey.youtube_url(origin),
                "audio": "added music"
                if music
                else "silent"
                if value(form, "mute") == "on"
                else "original audio",
            }
            snippet = youtube.metadata(
                draft_context,
                work,
                agent=timey.designer(value(form, "designer", "auto"))
                if value(form, "metadata_instructions")
                else None,
            )
            details = output.with_suffix(".youtube.json")
            atomic_json(
                details,
                {
                    "snippet": snippet,
                    "status": {
                        "privacyStatus": "private",
                        "selfDeclaredMadeForKids": False,
                        "containsSyntheticMedia": False,
                    },
                    "context": draft_context,
                    "thumbnail": "first-frame",
                },
            )
            prepared = youtube.prepare(output, details)
            downloads.append(context.publish(details))
            if prepared.get("thumbnail"):
                downloads.append(context.publish(Path(prepared["thumbnail"])))
        return _show(
            request,
            result="Your timer is ready",
            downloads=downloads,
            image=result["url"] if action == "preview" else None,
            **({"design": designed} if designed else {}),
        )
    finally:
        RENDER.release()


@router.post("/api/minis/timey")
async def submit(request: Request) -> dict[str, object]:
    """Limit expensive rendering to one browser request at a time"""
    async with request.form() as form:
        return await run_in_threadpool(_process, request, form, workspace(request))


def _saved_video(request: Request, source: str) -> Path:
    """Require verified access and an MP4 registered by this workspace"""
    if not request.app.state.identity.user(request):
        raise HTTPException(401, "Sign in with UQ to save your video; your draft is still here")
    key = source.removeprefix("/download/")
    path = workspace(request).download(key) if re.fullmatch(r"[a-f0-9]{32}", key) else None
    if path is None or not path.is_file() or path.is_symlink() or path.suffix.lower() != ".mp4":
        raise MiniError("This video is no longer available; return to your draft and make it again")
    return path


@router.post("/api/timey/save")
async def save(request: Request) -> dict[str, Any]:
    """Authorise a finished video's download without moving or rewriting the draft"""
    async with request.form() as form:
        video = _saved_video(request, value(form, "source"))
    return {
        "result": "Your download is ready",
        "downloads": [workspace(request).publish(video)],
    }


def _publish(request: Request, form: FormData) -> dict[str, Any]:
    """Publish only a reviewed registered video, with editable audience-facing details"""
    from uq_minis.minis.timey import youtube

    video = _saved_video(request, value(form, "source"))
    if value(form, "confirm") != "on":
        raise MiniError("Choose Upload to confirm where this video will be published")
    if value(form, "destination") != "youtube":
        raise HTTPException(503, "Keysi CDN is not connected yet; save a copy or choose YouTube")
    title, description = value(form, "title").strip(), value(form, "description")
    if not title or len(title) > 100 or len(description) > 4000:
        raise MiniError("Use a name under 100 characters and a description under 4,000 characters")
    details = workspace(request).directory("timey") / "video.youtube.json"
    atomic_json(
        details,
        {
            "snippet": {"title": title, "description": description, "categoryId": "27"},
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": False,
            },
            "thumbnail": "first-frame",
        },
    )
    youtube.prepare(video, details)
    link = youtube.upload(
        video, details, STATE / "timey/client_secret.json", STATE / "timey/youtube.json"
    )
    return {"result": f"Your video is on YouTube: {link}"}


@router.post("/api/timey/publish")
async def publish(request: Request) -> dict[str, Any]:
    """Keep publication behind verified access and the person's explicit destination choice"""
    async with request.form() as form:
        if not PUBLISH.acquire(blocking=False):
            raise HTTPException(
                409, "A video is already uploading; wait for it before trying again"
            )
        try:
            return await run_in_threadpool(_publish, request, form)
        finally:
            PUBLISH.release()


@router.get("/api/timey/search")
def search(query: str) -> dict[str, Any]:
    """Use the same bounded five-result YouTube search as the terminal"""
    from uq_minis.minis import timey

    return {"rows": timey.search(query, cookies=_google())}


@router.get("/api/timey/suggest")
async def suggestions(
    query: str = Query(default="", max_length=200),
) -> dict[str, list[str]]:
    """Offer quick predictions through the same bounded lookup as the CLI"""
    from uq_minis.minis import timey

    return {"suggestions": await timey.suggest(query)}


@router.get("/api/timey/fonts")
def fonts(query: str = Query(default="", max_length=200)) -> dict[str, Any]:
    """Search the CLI font shelf without downloading unselected font files"""
    from uq_minis.minis import timey

    notice = ""
    try:
        families = timey.catalogue(STATE / "timey/fonts")
    except MiniError:
        families = None
        notice = "Offline font shelf · try again for more fonts"
    matches = timey.fonts(query, families)
    names = list(matches)
    if query:
        names.sort(
            key=lambda name: (
                name.casefold() != query.casefold(),
                not name.casefold().startswith(query.casefold()),
                name,
            )
        )
    return {
        "rows": [
            {
                "name": name,
                "description": matches[name].removeprefix(f"{name} · ").removesuffix(" · bundled"),
                "source": f"https://fonts.google.com/specimen/{quote_plus(name)}",
            }
            for name in names[:12]
        ],
        "total": len(matches),
        "notice": notice,
    }


def _overlay(form: FormData, cancelled: Event | None = None) -> bytes:
    from uq_minis.minis.timey.video import Image, duration, frames, placement

    if not Image:
        raise MiniError("Enable Timey support to preview timer artwork")
    if not PREVIEW.acquire(blocking=False):
        raise HTTPException(429, "The preview is catching up; try again shortly")
    try:
        zero = duration(value(form, "length", "10m")) == 0
        if zero:
            form = FormData({**form, "length": "1s"})
        timer = replace(_timer(form), start_gap=0, end_gap=1 if zero else 0)
        width, height = (
            int(value(form, "width", "960")),
            int(value(form, "height", "540")),
        )
        if not 2 <= width <= 960 or not 2 <= height <= 540:
            raise MiniError("Preview dimensions must fit within 960 × 540")
        animated = value(form, "animated")
        if animated not in {"", "on"} or animated and value(form, "panel") != "on":
            raise MiniError("Choose a still or moving timer preview")
        if animated:
            rate = int(value(form, "fps", "30"))
            if rate not in {24, 30, 60}:
                raise MiniError("Choose 24, 30 or 60 fps")
            factor = min(1, 640 / width, 360 / height)
            width, height = (
                max(2, round(width * factor)),
                max(2, round(height * factor)),
            )
            stream = frames(
                replace(timer, width=None, height=None),
                width,
                height,
                fps=rate,
                offset=1 if zero else 0,
            )
            images: list[Image.Image] = []
            try:
                for frame in islice(stream, rate if timer.motion else 2):
                    if cancelled and cancelled.is_set():
                        raise MiniError("Timer preview cancelled")
                    with Image.open(BytesIO(frame)) as picture:
                        images.append(picture.convert("RGBA"))
                with BytesIO() as output:
                    images[0].save(
                        output,
                        format="WEBP",
                        save_all=True,
                        append_images=images[1:],
                        duration=round(1000 / rate) if timer.motion else 500,
                        loop=0,
                        quality=85,
                        method=2,
                    )
                    return output.getvalue()
            finally:
                stream.close()
                for image in images:
                    image.close()
        if value(form, "panel") == "on":
            stream = frames(
                replace(timer, width=None, height=None),
                width,
                height,
                preview=not zero,
                offset=1 if zero else 0,
            )
            try:
                return next(stream)
            finally:
                stream.close()
        with Image.new("RGBA", (width, height)) as picture:
            stream = frames(timer, width, height, preview=not zero, offset=1 if zero else 0)
            try:
                with Image.open(BytesIO(next(stream))) as panel:
                    x, y, _ = placement(timer, width, height)
                    picture.alpha_composite(panel.convert("RGBA"), (x, y))
            finally:
                stream.close()
            with BytesIO() as output:
                picture.save(output, format="PNG")
                return output.getvalue()
    finally:
        PREVIEW.release()


@router.post("/api/timey/preview")
async def overlay(request: Request) -> Response:
    """Render just the actual timer overlay without downloading or encoding footage"""
    async with request.form() as form:
        async with cancellation(request) as cancelled:
            resolved = FormData({**form, "font": _source(form, workspace(request), "font")})
            data = await run_in_threadpool(_overlay, resolved, cancelled)
    return Response(data, media_type="image/webp" if value(form, "animated") else "image/png")


def _clip(request: Request, form: FormData, cancelled: Event) -> dict[str, object]:
    from uq_minis.minis.timey import clip
    from uq_minis.minis.timey.video import PICTURES, duration, probe

    if not MEDIA.acquire(blocking=False):
        raise HTTPException(
            429,
            "Preparing a backdrop; your selection will follow",
            headers={"Retry-After": "2"},
        )
    try:
        source = _source(form, workspace(request))
        if _youtube(source):
            _google()
        source_title = ""
        if value(form, "source").startswith("upload:"):
            index = Path(source).parent / "info.json"
            if index.is_file() and not index.is_symlink() and index.stat().st_size <= 4096:
                original = json.loads(index.read_text())
                if isinstance(original, dict):
                    title = cast(dict[str, Any], original).get("title")
                    if isinstance(title, str):
                        source_title = title
        query = parse_qs(urlsplit(source).query)
        start = duration(value(form, "start") or query.get("t", query.get("start", ["0"]))[0])
        if not 0 <= start <= 2**31 - 1:
            raise MiniError("Video start must be a non-negative timestamp")
        complete = value(form, "complete")
        if complete not in {"", "on"}:
            raise MiniError("Choose a short sample or a complete video")
        audio = value(form, "audio")
        if audio not in {"", "on"}:
            raise MiniError("Choose video or music")
        path, title = clip.prepare(
            source,
            CACHE / "timey/media",
            start=0 if complete else start,
            complete=bool(complete),
            audio=bool(audio),
            height=int(value(form, "height", "540")),
            fps=int(value(form, "fps", "30")),
            cancelled=cancelled,
        )
        width, height, _ = (2, 2, True) if audio else probe(path)
        width, height = max(2, width), max(2, height)
        index = path.parent / "info.json"
        info: dict[str, Any] = json.loads(index.read_text()) if index.is_file() else {}
        duration = info.get("duration", 0)
        cached_complete = bool(complete) or info.get("complete") is True
        if type(duration) not in {int, float} or not math.isfinite(duration) or duration < 0:
            duration = 0
        if cached_complete and duration and start >= duration:
            raise MiniError("Video start must be before the end of the source video")
        return {
            **workspace(request).publish(path),
            "title": source_title or title,
            "width": width,
            "height": height,
            "duration": duration,
            "complete": cached_complete,
            "kind": "audio" if audio else "image" if path.suffix.lower() in PICTURES else "video",
        }
    finally:
        MEDIA.release()


@router.post("/api/timey/clip")
async def backdrop(request: Request) -> dict[str, object]:
    """Prepare cached media and cancel abandoned downloads or encodes"""
    async with request.form() as form:
        async with cancellation(request) as cancelled:
            return await run_in_threadpool(_clip, request, form, cancelled)


@router.post("/api/timey/source")
async def source(request: Request) -> dict[str, str]:
    """Stream local media into the shared cache and validate it before publication"""
    return await _upload(request, request.stream())


PARTS = BoundedSemaphore(1)


@router.post("/api/timey/parts/{key}")
async def parts(request: Request, key: str) -> dict[str, str]:
    """Assemble bounded ordered chunks to stay below Cloudflare's request limit"""
    if not re.fullmatch(r"[a-f0-9]{32}", key):
        raise MiniError("Invalid upload identifier")
    if not PARTS.acquire(blocking=False):
        raise HTTPException(429, "Another file is uploading; try again shortly")
    root = CACHE / "timey/parts"
    path = root / key
    try:
        if any(item.is_symlink() for item in (root, *root.parents)):
            raise MiniError("The upload directory must not be a symlink")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        for item in root.iterdir():
            if item.is_file() and not item.is_symlink() and item.stat().st_mtime < time() - 3600:
                item.unlink()
        offset = int(request.query_params.get("offset", "0"))
        if path.is_symlink() or offset != (path.stat().st_size if path.exists() else 0):
            raise MiniError("This upload was interrupted; choose the file again")
        if not path.exists() and len(list(root.iterdir())) >= 2:
            raise MiniError("Finish the current uploads before adding another file")
        length = int(request.headers.get("content-length", "0"))
        if not 0 < length <= 8 * 1024**2 or offset + length > UPLOAD_LIMIT:
            raise HTTPException(413, "Upload parts must be under 8 MiB and files under 512 MiB")
        received = 0
        with path.open("ab") as stream:
            async for chunk in request.stream():
                received += len(chunk)
                if received > length:
                    raise MiniError("The upload part was larger than expected")
                await run_in_threadpool(stream.write, chunk)
        path.chmod(0o600)
        if received != length:
            path.unlink(missing_ok=True)
            raise MiniError("This upload was interrupted; choose the file again")
    finally:
        PARTS.release()
    if request.query_params.get("final") != "on":
        return {"pending": "on"}

    async def chunks() -> AsyncIterable[bytes]:
        with path.open("rb") as stream:
            while chunk := await run_in_threadpool(stream.read, 1024**2):
                yield chunk

    try:
        return await _upload(request, chunks())
    finally:
        path.unlink(missing_ok=True)


async def _upload(request: Request, chunks: AsyncIterable[bytes]) -> dict[str, str]:
    """Validate a whole upload before publishing it to this workspace's cache"""
    from uq_minis.minis.timey.clip import animation, picture
    from uq_minis.minis.timey.video import PICTURES, inspect

    if int(request.headers.get("content-length", "0")) > UPLOAD_LIMIT:
        raise HTTPException(413, "Choose a file under 512 MiB")
    if not MEDIA.acquire(blocking=False):
        raise HTTPException(429, "Preparing another background; try again shortly")
    try:
        audio = request.query_params.get("audio", "")
        font = request.query_params.get("font", "")
        if font not in {"", "on"} or audio and font:
            raise MiniError("Choose one background, music or font file")
        if audio not in {"", "on"}:
            raise MiniError("Choose video or music")
        root = STATE / "timey/sources"
        if any(path.is_symlink() for path in (root, *root.parents)):
            raise MiniError("The media cache must not be a symlink")
        root.parent.mkdir(parents=True, exist_ok=True)
        name = Path(request.query_params.get("name", "video.mp4")).name[:120] or "video.mp4"
        suffix = Path(name).suffix.lower()
        limit = 8 * 1024**2 if font else UPLOAD_LIMIT
        is_picture = (
            not audio
            and not font
            and (suffix in PICTURES or request.headers.get("content-type", "").startswith("image/"))
        )
        filename = "upload" + (
            suffix
            if suffix
            in PICTURES
            | {
                ".mp4",
                ".mov",
                ".mkv",
                ".webm",
                ".m4v",
                ".avi",
                ".mp3",
                ".m4a",
                ".wav",
                ".flac",
                ".ogg",
                ".opus",
                ".aac",
                ".ttf",
                ".otf",
                ".ttc",
                ".woff",
                ".woff2",
            }
            else ".ttf"
            if font
            else ".m4a"
            if audio
            else ".mp4"
        )
        with TemporaryDirectory(prefix=".upload-", dir=root.parent) as directory:
            path = Path(directory) / filename
            digest, size = hashlib.sha256(), 0
            with path.open("wb") as stream:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(
                            413,
                            "Choose a font under 8 MiB" if font else "Choose a file under 512 MiB",
                        )
                    digest.update(chunk)
                    await run_in_threadpool(stream.write, chunk)
            if not size:
                raise MiniError("This file is empty; choose the original file and try again")
            original = path
            if font:
                from PIL import ImageFont

                try:
                    await run_in_threadpool(ImageFont.truetype, str(path), 16)
                except OSError as exc:
                    raise MiniError(
                        "This font could not be opened; try TTF, OTF, WOFF or WOFF2"
                    ) from exc
                duration = 0
            elif is_picture:
                moving = Path(directory) / "animation.mp4"
                async with cancellation(request) as cancelled:
                    animated = await run_in_threadpool(animation, path, moving, cancelled)
                if animated:
                    path, filename = moving, "upload.mp4"
                    _, _, _, duration = await run_in_threadpool(inspect, path)
                else:
                    image = Path(directory) / "background.png"
                    await run_in_threadpool(picture, path, image)
                    path, filename, duration = image, "upload.png", 0
            else:
                if audio:
                    _, _, _, duration = await run_in_threadpool(inspect, path, audio=True)
                else:
                    _, _, _, duration = await run_in_threadpool(inspect, path)
                if not duration:
                    raise MiniError("Choose a video with a finite length")
            identity = digest.hexdigest()[:16]
            key = f"{identity}-{hashlib.sha256(filename.encode()).hexdigest()[:16]}"
            # Original uploads are durable draft inputs, never automatic cache eviction
            with files.writing(root / key / filename) as destination:
                await run_in_threadpool(shutil.copyfile, path, destination)
                destination.chmod(0o600)
            if original != path:
                with files.writing(root / key / ("original" + original.suffix)) as destination:
                    await run_in_threadpool(shutil.copyfile, original, destination)
                    destination.chmod(0o600)
            atomic_json(
                root / key / "info.json",
                {"file": filename, "title": name, "duration": duration},
                private=True,
            )
        saved = workspace(request).publish(root / key / filename)
        return {"source": "upload:" + saved["url"].rsplit("/", 1)[-1], "title": name}
    finally:
        MEDIA.release()
