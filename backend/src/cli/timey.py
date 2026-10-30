"""Timey's guided terminal wizard and direct rendering options

The guided wizard and direct flags build the same Timer configuration
Media selection, rendering, publication drafts and uploads remain separate
steps so changing a preview cannot accidentally publish a video
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any
from urllib.parse import quote_plus

import typer
from rich.panel import Panel
from rich.text import Text

from uq_minis.core import (
    CONSOLE,
    STATE,
    MiniError,
    Preview,
    activity,
    application,
    ask,
    confirm,
    intro,
    number,
    problem,
    table,
)
from uq_minis.core.art import RESIDENTS
from uq_minis.core.common import atomic_json, ensure_outputs, unique
from uq_minis.core.paths import CACHE
lazy from uq_minis.minis.timey import (
    FONTS,
    POSITIONS,
    STYLES,
    Timer,
    catalogue,
    clock,
    design,
    download,
    duration,
    frame,
    overlay,
    picture,
    read_style,
    reference,
    render,
    require_ffmpeg,
    search,
    specimen,
    suggest,
    suggest_style,
    thumbnail,
    youtube_url,
)
lazy from uq_minis.minis.timey import (
    designer as choose_designer,
)
lazy from uq_minis.minis.timey import (
    font as resolve_font,
)
lazy from uq_minis.minis.timey import (
    fonts as find_fonts,
)
lazy from uq_minis.minis.timey.youtube import metadata as generate_metadata
lazy from uq_minis.minis.timey.youtube import prepare as prepare_upload
lazy from uq_minis.minis.timey.youtube import read_details, upload, validate

app = application(theme=RESIDENTS["timey"])


def _media(message: str, default: str = "", *, optional: bool = False, height: int = 0) -> str:
    """Search on request and fill the canonical link only after a result is chosen"""
    while True:
        value = ask(
            message, default=default, paths=True, required=not optional, lookup=suggest
        ).strip()
        if not value or value.lower().startswith(("https://", "http://")):
            return value
        if len(value) <= 240 and (
            Path(value).expanduser().exists()
            or Path(value).suffix.lower()
            in {".mp4", ".mov", ".webm", ".mkv", ".wav", ".mp3", ".m4a"}
        ):
            return value
        if value.startswith(("/", "./", "../", "~")):
            CONSOLE.print(
                "This local path does not exist; choose a file or enter search words",
                style="error",
            )
            default = value
            continue
        try:
            with activity("Searching YouTube") as update:
                results = search(value)
                previews: dict[str, Preview] = {}
                for index, result in enumerate(results):
                    previews[result["url"]] = thumbnail(result, height=height)
                    update((index + 1) / len(results), "Reading thumbnails")
        except MiniError as exc:
            problem(exc)
            default = value
            continue
        if not results:
            CONSOLE.print("No videos found; try different search words", style="muted")
            default = value
            continue
        choices = {item["url"]: f"{item['title']} · {item['length']}" for item in results}
        choices["back"] = "Search again or enter a link"
        selected = ask("Choose a video", choices=choices, previews=previews)
        if selected != "back":
            return selected
        default = value


class _Studio:
    """Keep the current overlay and its choice previews together"""

    def __init__(self, timer: Timer):
        self.timer = timer

    def samples(self, field: str, values: Iterable[str]) -> dict[str, Preview]:
        """Prepare images once so browsing never renders or downloads anything"""
        timer = replace(self.timer, x=None, y=None) if field == "position" else self.timer
        return {
            value: overlay(replace(timer, **{field: value}), value or "Theme default")
            for value in values
        }

    def choose(
        self, field: str, message: str, choices: dict[str, Any], *, free: bool = False
    ) -> str:
        """Preview listed choices and review a typed colour before applying it"""
        previews = self.samples(field, choices)
        while True:
            value = ask(
                message,
                choices=() if free else choices,
                suggestions=choices if free else (),
                default=getattr(self.timer, field),
                previews=previews,
                search=True,
            )
            try:
                candidate = replace(
                    self.timer,
                    **{field: value},
                    **({"x": None, "y": None} if field == "position" else {}),
                )
                if value in previews or confirm(
                    "Use this colour?", default=True, preview=overlay(candidate, value)
                ):
                    self.timer = candidate
                    return value
            except MiniError as exc:
                problem(exc)

    def font(self, default: str) -> str:
        """Turn mood words and misspellings into named choices before downloading"""
        from uq_minis.assets import ROOT

        fonts = {name: str(ROOT / "timey/fonts" / f"{name}.ttf") for name in FONTS.values()}
        previews = {
            name: overlay(replace(self.timer, font=path), name) for name, path in fonts.items()
        }
        try:
            with activity("Opening the Google Fonts catalogue"):
                available = catalogue(STATE / "timey/fonts")
        except MiniError as exc:
            problem(exc)
            CONSOLE.print(
                "Using the small offline font shelf; specimen links still work",
                style="muted",
            )
            available = None
        families = find_fonts(families=available)
        previews.update({
            name: previews[name.casefold().replace(" ", "")]
            for name in families
            if name.casefold().replace(" ", "") in fonts
        })

        async def sample(value: str) -> Preview | None:
            if value not in families:
                return None
            path = await specimen(
                f"https://fonts.google.com/specimen/{quote_plus(value)}", STATE / "timey/fonts"
            )
            return overlay(replace(self.timer, font=path), value)

        while True:
            value = ask(
                "Font mood or name, Google Fonts link or file (blank for theme default)",
                default=default,
                suggestions=families,
                ignore_case=True,
                paths=True,
                previews=previews,
                previewer=sample,
            ).strip()
            if not value:
                self.timer = replace(self.timer, font="")
                return ""
            try:
                source = value
                if not Path(value).expanduser().is_file() and (
                    value.startswith(("/", "./", "../", "~"))
                    or Path(value).suffix.lower() in {".ttf", ".otf", ".ttc"}
                ):
                    raise MiniError(
                        "This font file does not exist; choose a file or enter a family name"
                    )
                if (
                    not value.lower().startswith(("http://", "https://"))
                    and not Path(value).expanduser().is_file()
                ):
                    matches = find_fonts(value, available)
                    family = next(
                        (name for name in matches if name.casefold() == value.casefold()),
                        None,
                    )
                    if family is None:
                        if not matches:
                            CONSOLE.print(
                                "No close match on the font shelf yet; browse these or change your words",
                                style="muted",
                            )
                        choices = dict(matches or families)
                        choices.update({
                            "theme": "Use the theme font",
                            "back": "Change your search words",
                        })
                        family = ask(
                            "Choose a font",
                            choices=choices,
                            previews=previews,
                            previewer=sample,
                            ignore_case=True,
                        )
                        if family == "back":
                            default = value
                            continue
                        if family == "theme":
                            self.timer = replace(self.timer, font="")
                            return ""
                    value = family
                    key = value.casefold().replace(" ", "")
                    if key in fonts:
                        self.timer = replace(self.timer, font=fonts[key])
                        return fonts[key]
                    source = f"https://fonts.google.com/specimen/{quote_plus(value)}"
                with activity("Preparing your font sample") as update:
                    path = resolve_font(source, STATE / "timey/fonts", progress=update)
                candidate = replace(self.timer, font=path)
                if confirm("Use this font?", default=True, preview=overlay(candidate, value)):
                    self.timer = candidate
                    return path
            except (MiniError, OSError) as exc:
                problem(exc)


def _styles() -> list[str]:
    """Suggest presets and saved styles while leaving custom briefs available"""
    return [
        "auto",
        *STYLES,
        "custom",
        *(path.stem for path in sorted((STATE / "timey/styles").glob("*.json"))),
    ]


def _saved_style(value: str) -> Path | None:
    """Treat normal prose as a brief rather than probing it as a long filename"""
    if len(value) > 240 or "\n" in value:
        return None
    for path in (Path(value).expanduser(), (STATE / "timey/styles") / f"{value}.json"):
        if path.is_file():
            return path
    return None


def _metadata(context: dict[str, Any], directory: Path, designer: str) -> dict[str, Any]:
    """Use a signed-in agent when available, otherwise a factual timer-settings draft"""
    agent = (
        choose_designer(designer)
        if designer != "auto" or any(shutil.which(name) for name in ("codex", "claude"))
        else None
    )
    with activity("Writing your YouTube metadata") as progress:
        return generate_metadata(context, directory, agent=agent, progress=progress)


def _upload_details(
    path: Path,
    title: str,
    *,
    context: dict[str, Any] | None = None,
    metadata: bool | None = None,
    first_frame: bool | None = None,
    designer: str = "auto",
    sample: Preview | None = None,
) -> None:
    """Ask the YouTube questions and save an editable upload draft"""
    ensure_outputs([path], force=False)
    CONSOLE.print("YouTube details", style="heading")
    snippet: dict[str, Any] = {"title": title, "description": "", "tags": ["timer", "countdown"]}
    if metadata is None:
        metadata = confirm("Generate a searchable title, description and tags?", default=True)
    if metadata:
        context = dict(context or {"video_title": title})
        context["instructions"] = ask(
            "Video purpose or audience (blank to keep it general)",
            default=context.get("instructions", ""),
        )
        snippet = _metadata(context, path.parent, designer)
        CONSOLE.print(
            Panel(
                Text(snippet["description"]),
                title="Generated description",
                border_style="accent",
                padding=(1, 2),
            )
        )
    title = snippet["title"]
    title = ask("Video title", default=title[:100])
    description = ask("Description (or @path/to/description.txt)", default=snippet["description"])
    if description.startswith("@"):
        description = Path(description[1:]).expanduser().read_text(encoding="utf-8")
    tags = ask("Tags, separated by commas", default=",".join(snippet["tags"]))
    visibility = ask("Visibility", choices=["private", "unlisted", "public"], default="private")
    kids = confirm("Is this video made for kids?", default=False)
    synthetic = confirm("Does it contain realistic altered or synthetic content?", default=False)
    choice = (
        "first-frame"
        if first_frame
        else "youtube"
        if first_frame is False
        else ask(
            "Thumbnail",
            choices={
                "first-frame": "Use the opening frame",
                "custom": "Choose a PNG or JPEG",
                "youtube": "Let YouTube choose",
            },
            default="first-frame",
            previews={"first-frame": sample} if sample else None,
        )
    )
    thumbnail = (
        "first-frame"
        if choice == "first-frame"
        else ask("Custom thumbnail PNG/JPEG", paths=True)
        if choice == "custom"
        else ""
    )
    while choice == "custom":
        try:
            image = Path(thumbnail).expanduser()
            if confirm("Use this thumbnail?", default=True, preview=picture(image, image.name)):
                break
        except MiniError as exc:
            problem(exc)
        thumbnail = ask("Custom thumbnail PNG/JPEG", paths=True, required=True)
    data: dict[str, Any] = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [tag.strip() for tag in tags.split(",") if tag.strip()],
            "categoryId": "20",
        },
        "status": {
            "privacyStatus": visibility,
            "selfDeclaredMadeForKids": kids,
            "containsSyntheticMedia": synthetic,
            "license": "youtube",
            "embeddable": True,
        },
        "notifySubscribers": False,
    }
    if thumbnail:
        data["thumbnail"] = (
            thumbnail
            if thumbnail == "first-frame"
            else str(Path(thumbnail).expanduser().absolute())
        )
    if context:
        data["context"] = context
    if confirm(
        "Set category, language, licence, embedding, notifications or a schedule?",
        default=False,
    ):
        categories = {
            "gaming": "20",
            "education": "27",
            "entertainment": "24",
            "music": "10",
            "people & blogs": "22",
        }
        category = ask("Video category", choices=[*categories, "other"], default="gaming")
        data["snippet"]["categoryId"] = (
            categories[category] if category in categories else ask("YouTube category ID")
        )
        language = ask("Video language (e.g. en-AU, blank to skip)", default="")
        if language:
            data["snippet"]["defaultLanguage"] = language
        data["status"]["license"] = ask(
            "Licence", choices=["youtube", "creativeCommon"], default="youtube"
        )
        data["status"]["embeddable"] = confirm("Allow embedding?", default=True)
        data["notifySubscribers"] = confirm("Notify subscribers?", default=False)
        schedule = ask("Publish at (ISO date with timezone, blank to skip)", default="")
        if schedule:
            data["status"].update(privacyStatus="private", publishAt=schedule)
    validate(data)
    atomic_json(path, data)
    CONSOLE.print(f"Saved editable upload details: {path}", markup=False)
    CONSOLE.print(
        "YouTube Studio handles copyright checks, age restriction, monetisation, cards and end screens",
        style="dim",
    )


def _send(
    video: Path,
    details: Path,
    secrets: Path,
    token: Path,
    *,
    yes: bool,
    interactive: bool,
    force: bool = False,
) -> None:
    """Review the draft and upload only after confirmation"""
    data = prepare_upload(video, details, force=force)
    body = validate(data)
    view = table("YouTube", "Details")
    view.add_row("Video", Text(str(video)))
    view.add_row("Title", Text(body["snippet"]["title"]))
    view.add_row("Description", Text(body["snippet"]["description"]))
    view.add_row("Tags", Text(", ".join(body["snippet"].get("tags", []))))
    view.add_row("Thumbnail", Text(data.get("thumbnail", "YouTube automatically chooses")))
    view.add_row("Visibility", body["status"]["privacyStatus"])
    view.add_row("Made for kids", str(body["status"]["selfDeclaredMadeForKids"]))
    view.add_row("Altered content", str(body["status"]["containsSyntheticMedia"]))
    if body["status"].get("publishAt"):
        view.add_row("Scheduled", body["status"]["publishAt"])
    CONSOLE.print(view)
    if not yes and (
        not interactive
        or not confirm("Upload this video to your YouTube channel now?", default=False)
    ):
        CONSOLE.print("Upload skipped; your video and upload details are saved")
        return

    with activity("Connecting to YouTube · checking sign-in") as progress:
        url = upload(
            video,
            details,
            secrets,
            token,
            progress=progress,
        )
        progress(1, "Upload complete · your YouTube link is ready")
    CONSOLE.print(f"Uploaded: {url}", markup=False, style="success")
    receipt = json.loads(video.with_suffix(".uploaded.json").read_text(encoding="utf-8"))
    if (
        receipt.get("status", {}).get("privacyStatus") == "private"
        and body["status"]["privacyStatus"] != "private"
    ):
        CONSOLE.print(
            "YouTube kept this upload private; check YouTube Studio and your API project's audit status",
            style="warning",
        )


@app.command()
def run(
    source: Annotated[str | None, typer.Argument(help="YouTube link or local video path.")] = None,
    length: Annotated[
        str | None, typer.Option(help="Countdown: 10m, MM:SS, HH:MM:SS or seconds.")
    ] = None,
    video_start: Annotated[
        str | None,
        typer.Option(help="Start the background footage at this timestamp: 1:20, 2m or seconds."),
    ] = None,
    style: Annotated[
        str | None,
        typer.Option(help="Preset, saved style name, JSON file or a custom design brief."),
    ] = None,
    start_gap: Annotated[
        str | None,
        typer.Option(help="Get-ready time before the countdown (default 5s)."),
    ] = None,
    end_gap: Annotated[
        str | None,
        typer.Option(help="Time's-up hold after the countdown (default 5s)."),
    ] = None,
    position: Annotated[
        str, typer.Option(help="top-right/left, bottom-right/left/centre or centre.")
    ] = "centre",
    size: Annotated[
        float, typer.Option(help="Overlay size multiplier: 0.5–3 (default 2.4).")
    ] = 2.4,
    x: Annotated[
        float | None, typer.Option(help="Custom horizontal placement, 0–1; use with --y")
    ] = None,
    y: Annotated[
        float | None, typer.Option(help="Custom vertical placement, 0–1; use with --x")
    ] = None,
    overlay_width: Annotated[
        float | None, typer.Option(help="Overlay width as a fraction of the video, 0.05–1")
    ] = None,
    overlay_height: Annotated[
        float | None, typer.Option(help="Overlay height as a fraction of the video, 0.05–1")
    ] = None,
    motion: Annotated[
        bool,
        typer.Option(
            "--motion/--no-motion",
            help="Smooth digit changes and subtle animated edges.",
        ),
    ] = True,
    loop_blend: Annotated[
        float,
        typer.Option(
            help="Crossfade at short-video loop seams: 0–2 seconds; 0 keeps the original cut."
        ),
    ] = 0.6,
    label: Annotated[
        str,
        typer.Option(help="Optional short text above the timer (blank by default)."),
    ] = "",
    accent: Annotated[
        str, typer.Option(help="Override the theme's accent with a hex colour.")
    ] = "",
    font: Annotated[str, typer.Option(help="TTF/OTF/TTC file or a Google Fonts link.")] = "",
    instructions: Annotated[
        str,
        typer.Option(help="Ask a coding agent to create or refine the overlay style."),
    ] = "",
    designer: Annotated[
        str, typer.Option(help="Custom-style designer: auto, codex or claude.")
    ] = "auto",
    music: Annotated[
        str,
        typer.Option(help="Use audio from a YouTube link or a local audio/video file."),
    ] = "",
    music_volume: Annotated[
        float,
        typer.Option(help="Added music volume: 0–2, where 1 is the original volume."),
    ] = 1.0,
    mix_audio: Annotated[
        bool, typer.Option(help="Mix added music with the video's original audio.")
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Destination MP4, or PNG with --preview."),
    ] = None,
    height: Annotated[
        int | None,
        typer.Option(
            help="Maximum preview/export height in pixels; 0 keeps original quality (default)."
        ),
    ] = None,
    fps: Annotated[int, typer.Option(help="Output frame rate: 24, 30 or 60.")] = 30,
    mute: Annotated[
        bool,
        typer.Option(help="Mute the original video audio; added music still plays."),
    ] = False,
    customise: Annotated[
        bool,
        typer.Option(
            "--customise",
            "--customize",
            help="Ask about position, colour, label, font and audio.",
        ),
    ] = False,
    preview: Annotated[bool, typer.Option(help="Save only a styled PNG preview.")] = False,
    cache: Annotated[
        bool,
        typer.Option(
            "--cache/--no-cache",
            help="Reuse YouTube clips in the bounded out/.cache/timey/media cache.",
        ),
    ] = True,
    metadata: Annotated[
        bool | None,
        typer.Option(
            "--metadata/--no-metadata",
            help="Generate editable YouTube title, description and tags.",
        ),
    ] = None,
    metadata_instructions: Annotated[
        str,
        typer.Option(help="Purpose, audience or wording for generated YouTube metadata."),
    ] = "",
    first_frame: Annotated[
        bool | None,
        typer.Option(
            "--first-frame/--no-first-frame",
            help="Use the finished video's first frame as its YouTube thumbnail.",
        ),
    ] = None,
    upload: Annotated[
        bool | None,
        typer.Option("--upload/--no-upload", help="Offer a YouTube upload after rendering."),
    ] = None,
    upload_only: Annotated[
        bool, typer.Option(help="Upload an existing MP4 without rendering again.")
    ] = False,
    details: Annotated[
        Path | None, typer.Option(help="Editable YouTube upload-details JSON.")
    ] = None,
    client_secrets: Annotated[
        Path, typer.Option(help="Desktop OAuth client JSON for YouTube sign-in.")
    ] = (STATE / "timey/client_secret.json"),
    token: Annotated[Path, typer.Option(help="Private saved YouTube OAuth token.")] = STATE
    / "timey/youtube.json",
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Confirm a requested upload without a final prompt."),
    ] = False,
    force: Annotated[
        bool, typer.Option(help="Replace an existing rendered video or preview.")
    ] = False,
    no_input: Annotated[
        bool, typer.Option("--no-input", help="Use options without asking questions.")
    ] = False,
) -> None:
    """Timey: turn a video into a beautiful countdown, with an optional YouTube upload"""
    interactive = sys.stdin.isatty() and not no_input
    if interactive:
        intro("Timey", "Turn a video into a countdown")
    if height is None:
        height = (
            int(
                number(
                    "Preview and export quality",
                    stops={
                        **{
                            float(value): f"{value}p"
                            for value in (240, 360, 480, 720, 1080, 1440, 2160, 4320)
                        },
                        0: "Original",
                    },
                    default=0,
                    parse=lambda value: float(value.removesuffix("p")),
                )
            )
            if interactive and source is None and not upload_only
            else 0
        )
    if height != 0 and height < 240 or fps not in {24, 30, 60}:
        raise typer.BadParameter(
            "Choose a height of at least 240p (0 keeps the source) and 24/30/60 fps"
        )
    if source is None:
        if not interactive:
            raise typer.BadParameter("Pass a YouTube link or local video path")
        source = _media("YouTube link, local video or search words", height=height)
    if len(metadata_instructions) > 4000:
        raise typer.BadParameter("Metadata instructions must be at most 4000 characters")
    if upload_only:
        if preview or upload is False:
            raise typer.BadParameter(
                "--upload-only cannot be combined with --preview or --no-upload"
            )
        video = Path(source).expanduser()
        details = details or video.with_suffix(".youtube.json")
        context = {"video_title": video.stem, "instructions": metadata_instructions}
        if not details.exists() and interactive:
            _upload_details(
                details,
                video.stem,
                context=context,
                metadata=metadata,
                first_frame=first_frame,
                designer=designer,
                sample=frame(video) if video.is_file() else None,
            )
        else:
            data = read_details(details)
            if metadata:
                if isinstance(data.get("context"), dict):
                    context = dict(data["context"])
                context["video_title"] = data["snippet"]["title"]
                if metadata_instructions:
                    context["instructions"] = metadata_instructions
                data["snippet"].update(_metadata(context, details.parent, designer))
                data["context"] = context
            if first_frame is not None:
                if first_frame:
                    data["thumbnail"] = "first-frame"
                else:
                    data.pop("thumbnail", None)
            if metadata or first_frame is not None:
                atomic_json(details, data)
        if not interactive and not yes:
            raise typer.BadParameter("Use --yes to confirm an unattended upload")
        _send(
            video,
            details,
            client_secrets,
            token,
            yes=yes,
            interactive=interactive,
            force=force,
        )
        return
    if preview and upload:
        raise typer.BadParameter("A PNG preview cannot be uploaded as a video")
    if preview and (metadata or first_frame):
        raise typer.BadParameter("Metadata and first-frame thumbnails need a rendered MP4")
    if designer not in {"auto", "codex", "claude"}:
        raise typer.BadParameter("Choose auto, codex or claude as the style designer")
    if not math.isfinite(music_volume) or not 0 <= music_volume <= 2:
        raise typer.BadParameter("Music volume must be between 0 and 2")
    if length is None and not interactive:
        raise typer.BadParameter("Pass --length, such as --length 10m, for an unattended render")
    if interactive:
        CONSOLE.rule("Timing", style="accent", align="left")
        length = length or str(
            int(
                number(
                    "How long should the timer run? (10m, 25:00, 1h)",
                    default=600,
                    minimum=1,
                    maximum=86400,
                    step=60,
                    unit="s",
                    parse=duration,
                )
            )
        )
        if video_start is None:
            video_start = ask("Start background video at (timestamp, e.g. 1:20)", default="0s")
        start_gap = start_gap or str(
            int(
                number(
                    "Gap before it starts",
                    default=5,
                    minimum=0,
                    maximum=3600,
                    unit="s",
                    parse=duration,
                )
            )
        )
        end_gap = end_gap or str(
            int(
                number(
                    "Gap after it finishes",
                    default=5,
                    minimum=0,
                    maximum=3600,
                    unit="s",
                    parse=duration,
                )
            )
        )
        studio = _Studio(
            Timer(
                seconds=duration(length),
                start_gap=duration(start_gap),
                end_gap=duration(end_gap),
                style=style if style is not None and style in STYLES else "minimal",
                position=position,
                x=x,
                y=y,
                width=overlay_width,
                height=overlay_height,
                accent=accent,
                size=size,
                label=label,
            )
        )
        if style is None:
            CONSOLE.rule("Your look", style="accent", align="left")
            styles = {"auto": "Suggest a theme from the video title"}
            styles.update({name: f"{name} · {values[0]}" for name, values in STYLES.items()})
            styles.update({name: name for name in _styles() if name not in styles})
            style = ask(
                "Timer style (name, file or describe your own)",
                default="auto",
                suggestions=styles,
                previews=studio.samples("style", STYLES),
                paths=True,
            )
        if style in STYLES:
            studio.timer = replace(studio.timer, style=style)
        if style == "custom" and not instructions:
            instructions = ask("Describe how the overlay should look")
        if instructions or style not in {"auto", *STYLES} and not _saved_style(style):
            designer = ask("Style designer", choices=["auto", "codex", "claude"], default=designer)
        if customise or confirm(
            "Customise the overlay placement, text, colour or audio?", default=False
        ):
            position = studio.choose("position", "Position", {name: name for name in POSITIONS})
            x = y = None
            size = (
                number("Timer size", default=size * 100, minimum=50, maximum=300, step=10, unit="%")
                / 100
            )
            motion = confirm("Smooth digit changes and subtle animated edges?", default=motion)
            loop_blend = number(
                "Blend between video repeats",
                default=loop_blend,
                minimum=0,
                maximum=2,
                step=0.1,
                unit="s",
            )
            label = ask("Timer label (blank for none)", default=label)
            studio.timer = replace(studio.timer, size=size, label=label)
            accent = studio.choose(
                "accent",
                "Accent hex colour (blank for theme default)",
                {
                    "": "Theme default",
                    "#8FDA53": "Leaf green",
                    "#6FE9EF": "Ice blue",
                    "#FFD34D": "Golden yellow",
                    "#E8A37E": "Peach",
                    "#C2ADD4": "Lilac",
                },
                free=True,
            )
            font = studio.font(font)
            music = _media(
                "Music link, file or search words (blank to keep original)",
                music,
                optional=True,
                height=height,
            )
            if music:
                music_volume = (
                    number(
                        "Music loudness",
                        default=music_volume * 100,
                        minimum=0,
                        maximum=200,
                        step=5,
                        control="dial",
                        unit="%",
                    )
                    / 100
                )
                mix_audio = confirm(
                    "Keep the original video audio alongside the music?",
                    default=mix_audio,
                )
            mute = confirm("Mute the background video?", default=mute)
        if not preview and upload is None:
            upload = confirm(
                "Would you like to upload the finished timer to YouTube as well?",
                default=False,
            )
    artwork, brief = None, instructions
    if style is not None and style not in {"auto", *STYLES}:
        saved = _saved_style(style)
        if saved:
            artwork = read_style(saved)
        elif style.lower().endswith(".json"):
            raise MiniError(f"Style file does not exist: {style}")
        elif style != "custom":
            brief = f"{style}\n{instructions}".strip()
    elif instructions and style in STYLES:
        brief = f"{style} game-inspired overlay\n{instructions}"
    if style == "custom" and not brief:
        raise typer.BadParameter("Use --instructions to describe your custom overlay")
    if len(brief) > 4000:
        raise typer.BadParameter("Describe the custom style in at most 4000 characters")
    if brief:
        designer = choose_designer(designer)
    if not math.isfinite(music_volume) or not 0 <= music_volume <= 2:
        raise typer.BadParameter("Music volume must be between 0 and 2")
    assert length is not None
    timer = Timer(
        duration(length),
        duration(start_gap or "5s"),
        duration(end_gap or "5s"),
        style if style is not None and style in STYLES else "minimal",
        position,
        label,
        accent,
        "",
        artwork,
        size,
        motion,
        loop_blend,
        x,
        y,
        overlay_width,
        overlay_height,
    )
    start = duration(video_start or "0s")
    if start > 2**31 - 1:
        raise typer.BadParameter("Video start timestamp is too large")
    local_start = start if not source.lstrip().lower().startswith(("http://", "https://")) else 0
    save_prompt = output is None and interactive
    if output is None:
        default = "out/timey/timey.png" if preview else "out/timey/timey.mp4"
        output = Path(ask("Save to", default=default, paths=True) if interactive else default)
    output = output.expanduser().absolute()
    if output.is_symlink():
        raise MiniError("Output must not be a symlink")
    if output.suffix.lower() != (".png" if preview else ".mp4"):
        raise MiniError("Use .png for a preview or .mp4 for a rendered timer")
    if save_prompt and not force:
        output = unique(output)
    ensure_outputs([output], force=force)
    if upload or metadata or first_frame:
        if upload and not interactive and (not details or not yes):
            raise typer.BadParameter("An unattended upload requires --details and --yes")
        details = details or output.with_suffix(".youtube.json")
        details = details.expanduser().absolute()
        if details.is_symlink() or details in {
            output,
            output.with_suffix(".thumbnail.jpg"),
        }:
            raise MiniError(
                "Upload details must have their own file path, separate from the video and thumbnail"
            )
        if details.exists():
            read_details(details)
        elif upload and not interactive:
            raise MiniError(
                f"Upload details do not exist: {details}; create a draft with the wizard first"
            )
        if output.with_suffix(".uploaded.json").exists():
            raise MiniError("This output already has an upload receipt; choose a new output path")
    require_ffmpeg()
    with TemporaryDirectory(
        prefix=".timey-", dir=output.parent if output.parent.exists() else Path.cwd()
    ) as scratch:
        with activity("Preparing your background") as progress:
            video, title = download(
                source,
                Path(scratch),
                seconds=1 if preview else timer.total,
                height=height,
                progress=progress,
                start=start,
                cache=(CACHE / "timey/media") if cache else None,
            )
        if brief:
            background = Path(scratch) / "background.png"
            reference(video, background, start=local_start)
            with activity("Crafting your overlay · preparing the design brief") as progress:
                artwork, saved_style = design(
                    brief,
                    (STATE / "timey/styles"),
                    agent=designer,
                    background=background,
                    context=title,
                    base=artwork,
                    progress=progress,
                )
            CONSOLE.print(f"Reusable style: {saved_style}", markup=False)
            timer = replace(timer, style=artwork["name"], artwork=artwork)
        elif artwork:
            timer = replace(timer, style=artwork["name"])
        if style in {None, "auto"} and not artwork:
            timer = replace(timer, style=suggest_style(title))
        if font:
            with activity("Finding your font") as progress:
                timer = replace(
                    timer,
                    font=resolve_font(font, (STATE / "timey/fonts"), progress=progress),
                )
                progress(1, "Font ready · applied to your overlay")
        notice = ""
        while True:
            location = (
                f"{timer.x:.0%} across, {timer.y:.0%} down"
                if timer.x is not None and timer.y is not None
                else timer.position
            )
            summary = {
                "Background": title,
                "Countdown": clock(timer.seconds),
                "Before / after": f"{timer.start_gap}s before · {timer.end_gap}s after",
                "Full video": clock(timer.total),
                "Look": f"{timer.style.replace('-', ' ').title()} · {location} · {timer.size * 100:g}% size",
                "Quality": f"Up to {height}p"
                if height
                else "Keep the background’s original quality",
                "Sound": f"Added music at {music_volume * 100:g}%"
                + (" with the background audio" if mix_audio and not mute else "")
                if music
                else "Silent"
                if mute
                else "Keep the background audio",
                "Save to": str(output),
                **({"Check this change": notice} if notice else {}),
            }
            if not interactive or preview:
                view = table("Timer", "Your video", title="Here’s what we’re making")
                for name, value in summary.items():
                    view.add_row(name, Text(value))
                CONSOLE.print(view)
                break
            sample = (
                frame(video, timer, start=local_start, height=height)
                if video.is_file()
                else overlay(timer, "Your timer")
            )
            action = ask(
                "Review your timer",
                choices={
                    "make": "Finish and create timer",
                    "edit": "Adjust timing and layout",
                    "preview": "Watch a short preview",
                },
                default="make",
                details=summary,
                preview=sample,
            )
            if action == "make":
                break
            if action == "preview":
                preview_path = Path(scratch) / ("preview.mp4" if timer.motion else "preview.png")
                with activity("Preparing your short preview") as progress:
                    render(
                        video,
                        preview_path,
                        timer,
                        preview=not timer.motion,
                        sample=timer.motion,
                        mute=True,
                        height=height,
                        fps=fps,
                        progress=progress,
                        start=local_start,
                    )
                typer.launch(str(preview_path))
                continue
            try:
                studio = _Studio(timer)
                seconds = int(
                    number(
                        "Countdown length",
                        default=timer.seconds,
                        minimum=1,
                        maximum=86400,
                        step=60,
                        unit="s",
                        parse=duration,
                    )
                )
                opening = int(
                    number(
                        "Gap before it starts",
                        default=timer.start_gap,
                        minimum=0,
                        maximum=3600,
                        unit="s",
                        parse=duration,
                    )
                )
                ending = int(
                    number(
                        "Gap after it finishes",
                        default=timer.end_gap,
                        minimum=0,
                        maximum=3600,
                        unit="s",
                        parse=duration,
                    )
                )
                position = studio.choose("position", "Position", {name: name for name in POSITIONS})
                size = (
                    number(
                        "Timer size",
                        default=timer.size * 100,
                        minimum=50,
                        maximum=300,
                        step=10,
                        unit="%",
                    )
                    / 100
                )
                timer = replace(
                    timer,
                    seconds=seconds,
                    start_gap=opening,
                    end_gap=ending,
                    position=position,
                    x=None,
                    y=None,
                    size=size,
                )
                notice = ""
            except MiniError as exc:
                notice = str(exc)
        context = {
            "video_title": title[:500],
            "style": timer.style,
            "label": timer.label,
            "countdown_seconds": timer.seconds,
            "start_gap": timer.start_gap,
            "end_gap": timer.end_gap,
            "total_seconds": timer.total,
            "source_start": start,
            "audio": "added soundtrack mixed with original audio"
            if music and mix_audio and not mute
            else "added soundtrack"
            if music
            else "muted"
            if mute
            else "original audio when present",
            "instructions": metadata_instructions,
        }
        if source.lstrip().lower().startswith(("http://", "https://")):
            context["source_url"] = youtube_url(source)
        if upload:
            assert details is not None
        if upload and details is not None and not details.exists():
            _upload_details(
                details,
                f"{clock(timer.seconds)} {timer.style} timer",
                context=context,
                metadata=metadata,
                first_frame=first_frame,
                designer=designer,
                sample=frame(video, timer, start=local_start, height=height)
                if video.is_file()
                else None,
            )
        elif details is not None and (metadata or first_frame is not None):
            data: dict[str, Any] = (
                read_details(details)
                if details.exists()
                else {
                    "snippet": {
                        "title": f"{clock(timer.seconds)} {timer.style} timer",
                        "description": "",
                        "tags": ["timer", "countdown"],
                        "categoryId": "20",
                    },
                    "status": {
                        "privacyStatus": "private",
                        "selfDeclaredMadeForKids": False,
                        "containsSyntheticMedia": False,
                    },
                    "notifySubscribers": False,
                }
            )
            if metadata:
                data["snippet"].update(_metadata(context, details.parent, designer))
            data["context"] = context
            if first_frame:
                data["thumbnail"] = "first-frame"
            elif first_frame is False:
                data.pop("thumbnail", None)
            validate(data)
            atomic_json(details, data)
        if preview:
            with activity("Drawing your preview") as progress:
                render(
                    video,
                    output,
                    timer,
                    preview=True,
                    height=height,
                    fps=fps,
                    force=force,
                    progress=progress,
                    start=local_start,
                )
        else:
            soundtrack = None
            if music:
                music_directory = Path(scratch) / "music"
                music_directory.mkdir()
                with activity("Preparing your soundtrack") as progress:
                    soundtrack, _ = download(
                        music,
                        music_directory,
                        seconds=timer.total,
                        audio=True,
                        progress=progress,
                        cache=(CACHE / "timey/media") if cache else None,
                    )
            with activity("Rendering the timer · starting the video export") as progress:
                render(
                    video,
                    output,
                    timer,
                    height=height,
                    fps=fps,
                    mute=mute,
                    force=force,
                    progress=progress,
                    music=soundtrack,
                    music_volume=music_volume,
                    mix_audio=mix_audio,
                    start=local_start,
                )
    CONSOLE.print(f"Saved: {output}", markup=False, style="success")
    if details and not upload and (metadata or first_frame):
        data = prepare_upload(output, details, force=force)
        CONSOLE.print(f"YouTube draft: {details}", markup=False)
        if data.get("thumbnail"):
            CONSOLE.print(f"Thumbnail: {data['thumbnail']}", markup=False)
    if upload:
        assert details is not None
        _send(
            output,
            details,
            client_secrets,
            token,
            yes=yes,
            interactive=interactive,
            force=force,
        )
