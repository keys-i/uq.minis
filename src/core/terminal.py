"""Shared Typer applications, Rich output and terminal input"""

import os
import random
import time
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, FloatPrompt, InvalidResponse, Prompt
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from typer import rich_utils

from uq_minis.core.art import Habitat, Preview, _habitats

COLOURS = {
    "accent": "#cf6024",
    "success": "#269277",
    "warning": "#a77516",
    "error": "#ce4656",
    "ink": "#20262d",
    "peach": "#e8a37e",
    "mint": "#9bbfbc",
    "surface": "#262c34",
    "text": "#f1eee9",
}
THEME = Theme(
    {
        **COLOURS,
        "heading": "bold",
        "key": "bold",
        "muted": "dim",
        "prompt": "bold",
        "prompt.default": COLOURS["accent"],
        "prompt.choices": "dim",
        "prompt.invalid": COLOURS["error"],
        "progress.description": "bold",
        "progress.percentage": COLOURS["accent"],
        "bar.complete": COLOURS["peach"],
        "bar.finished": COLOURS["mint"],
        "bar.pulse": COLOURS["peach"],
    }
)
CONSOLE = Console(theme=THEME, highlight=False)
ERROR = Console(stderr=True, theme=THEME, highlight=False)


_HABITAT = ContextVar("mini_habitat", default=None)
_RECENT = ContextVar("mini_answers", default=())


def _look() -> Habitat:
    return _HABITAT.get() or _habitats()["raccoon"]


@contextmanager
def habitat(name: str):
    """Apply a mini's look and restore it after completion, errors or cancellation"""
    look = _habitats()[name]
    token = _HABITAT.set(look)
    answers = _RECENT.set(())
    option = rich_utils.STYLE_OPTION
    command = rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN
    rich_utils.STYLE_OPTION = f"bold {COLOURS['ink']} on {look.primary}"
    rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = rich_utils.STYLE_OPTION
    try:
        with (
            CONSOLE.use_theme(Theme(look.styles())),
            ERROR.use_theme(Theme(look.styles())),
        ):
            yield
    finally:
        rich_utils.STYLE_OPTION = option
        rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = command
        _HABITAT.reset(token)
        _RECENT.reset(answers)


# Typer creates its own help console, so share the colour values with it
rich_utils.STYLE_OPTION = f"bold {COLOURS['ink']} on {COLOURS['peach']}"
rich_utils.STYLE_SWITCH = f"bold {COLOURS['success']}"
rich_utils.STYLE_USAGE = COLOURS["accent"]
rich_utils.STYLE_OPTIONS_PANEL_BORDER = COLOURS["accent"]
rich_utils.STYLE_COMMANDS_PANEL_BORDER = COLOURS["accent"]
rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = rich_utils.STYLE_OPTION
rich_utils.STYLE_ERRORS_PANEL_BORDER = COLOURS["error"]


def intro(title: str, message: str) -> None:
    """Put the task first and leave artwork to the active prompt"""
    _RECENT.set(())
    CONSOLE.print()
    CONSOLE.print(Text(title, style="heading"))
    CONSOLE.print(Text(message))
    CONSOLE.print()


def table(*headers: str, title: str | None = None) -> Table:
    """Use airy, compact tables with the same emphasis across minis"""
    view = Table(
        *headers,
        title=title,
        title_justify="left",
        title_style="heading",
        header_style="heading",
        border_style="muted",
        box=box.SIMPLE,
        padding=(0, 1),
    )
    if view.columns:
        view.columns[0].style = "key"
    return view


@contextmanager
def activity(title: str, *, show: bool = True):
    """Show real progress, unknown-duration stages and useful redirected logs"""
    with Progress(
        SpinnerColumn("dots", style="accent"),
        TextColumn("{task.description}", markup=False),
        BarColumn(bar_width=20),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=CONSOLE,
        disable=not show or not CONSOLE.is_terminal,
        refresh_per_second=8,
    ) as progress:
        task = progress.add_task(title, total=None)
        previous = ["", -1]

        def update(done: float | None, stage: str) -> None:
            fraction = max(0, min(1, done)) if done is not None else None
            total, completed = (100, fraction * 100) if fraction is not None else (None, 0)
            if progress.tasks[task].total != total:
                started = progress.tasks[task].start_time
                progress.reset(task, total=total, completed=0, description=stage)
                # Rich treats None as "keep the total" during reset
                progress.tasks[task].total = total
                progress.tasks[task].start_time = started
            progress.update(task, description=stage, completed=completed)
            if show and not CONSOLE.is_terminal:
                name = stage.partition(" · ")[0]
                bucket = int(fraction * 10) if fraction is not None else -1
                if name != previous[0] or bucket != previous[1]:
                    CONSOLE.print(
                        (f"{fraction:.0%} · " if fraction is not None else "") + stage,
                        markup=False,
                    )
                    previous[:] = [name, bucket]

        update(None, title)
        yield update


def application(*, theme: str = "raccoon", add_completion: bool = False, **options) -> typer.Typer:
    """Create a command app with the shared presentation and exception settings"""
    app = typer.Typer(
        add_completion=add_completion,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
        **options,
    )
    app.habitat = theme
    return app


class _Input:
    """Keep keyboard input and presentation shared across prompt types"""

    completer = None

    def get_input(self, console, question, password, stream=None):
        """Use the active terminal session or Rich's ordinary input fallback"""
        from prompt_toolkit import prompt
        from prompt_toolkit.application import get_app, get_app_session
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.input import DummyInput, PipeInput
        from prompt_toolkit.layout import ConditionalContainer, HSplit, VSplit, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.mouse_events import MouseEventType
        from prompt_toolkit.output import ColorDepth
        from prompt_toolkit.styles import Style

        input = get_app_session().input
        if (
            stream is not None
            or isinstance(input, DummyInput)
            or os.getenv("TERM") == "dumb"
            or not console.is_terminal
            and not isinstance(input, PipeInput)
        ):
            if not getattr(self, "described", False):
                if preview := getattr(self, "preview", None):
                    console.print(Text(preview.description))
                for key, preview in getattr(self, "previews", {}).items():
                    console.print(Text(f"{key} · {preview.description}"))
                self.described = True
            return super().get_input(console, question, password, stream=stream)
        look = _look()
        moving = os.getenv("MINI_MOTION", "1") != "0" and not console.no_color
        started = time.monotonic()
        action = "idle"
        acted = started - 2
        deadline = started + random.uniform(2, 5)
        state = "idle"
        hover = ""

        def roomy():
            size = get_app_session().output.get_size()
            return (
                min(console.width, size.columns) >= 72
                and size.rows >= 16
                and console.encoding.lower().startswith("utf")
                and not console.no_color
            )

        def portrait():
            nonlocal action, acted, deadline, state, hover
            now = time.monotonic()
            buffer = get_app().current_buffer
            chosen = buffer.complete_state and buffer.complete_state.current_completion
            previews = getattr(self, "previews", {})
            key = chosen.text if chosen else buffer.text or getattr(self, "preview_default", "")
            preview = getattr(self, "preview", None) or previews.get(key)
            pose = "idle"
            if moving:
                focus = "look" if chosen else "listen" if buffer.text else "idle"
                if focus != state:
                    state = focus
                    hover = ""
                    if focus != "idle":
                        action, acted = focus, now
                if focus == "idle" and now - acted >= 1:
                    if getattr(self, "reaction", False) and now - started < 1:
                        action, acted = "peek", started
                    if now >= deadline:
                        action = random.choice(look.idle.split())
                        acted, deadline = now, now + random.uniform(4, 9)
                if now - acted < 1:
                    pose = action
                elif focus != "idle":
                    pose = focus
            frame = min(7, int(max(0, now - acted) * 8)) if moving else 0
            fragments = []
            for segment in (preview.picture if preview else look.picture(frame, pose)).render(
                console
            ):
                colour = segment.style.color if segment.style else None
                background = segment.style.bgcolor if segment.style else None
                fragments.append(
                    (
                        " ".join(
                            colour
                            for colour in (
                                f"fg:{colour.get_truecolor().hex}" if colour else "",
                                f"bg:{background.get_truecolor().hex}" if background else "",
                            )
                            if colour
                        ),
                        segment.text,
                    )
                )
            return fragments

        def touch(event):
            nonlocal action, acted, deadline, state, hover
            if event.event_type in {MouseEventType.MOUSE_MOVE, MouseEventType.MOUSE_UP}:
                x, y = event.position.x, event.position.y
                if 5 <= x <= 25 and 1 <= y <= 10:
                    buffer = get_app().current_buffer
                    chosen = buffer.complete_state and buffer.complete_state.current_completion
                    if getattr(self, "preview", None) or getattr(self, "previews", {}).get(
                        chosen.text if chosen else buffer.text
                    ):
                        return
                    region = "ears" if y < 3 else "pet" if x < 17 and y < 8 else "object"
                    hover = {
                        "ears": "ears · click to tickle",
                        "pet": "body · click to pet",
                        "object": f"{look.object} · click to play",
                    }[region]
                    if event.event_type == MouseEventType.MOUSE_MOVE:
                        get_app().invalidate()
                        return
                    if not moving:
                        return
                    state = "look" if chosen else "listen" if buffer.text else "idle"
                    action = region
                    acted = time.monotonic()
                    deadline = acted + random.uniform(4, 9)
                    get_app().invalidate()
                elif hover:
                    hover = ""
                    get_app().invalidate()

        def footer():
            buffer = get_app().current_buffer
            chosen = buffer.complete_state and buffer.complete_state.current_completion
            action = "enter to choose" if chosen else "enter"
            if self.completer and not (chosen or buffer.text):
                action = "↑↓ move · tab fill"
            if hover:
                action = hover
            return [("class:chosen" if chosen else "class:hint", f"  {action} ")]

        def ready():
            app = get_app()
            app.erase_when_done = True
            original = app.layout.container
            portrait_control = FormattedTextControl(portrait)
            portrait_control.mouse_handler = touch
            recent = "\n".join(_RECENT.get())
            panel = HSplit(
                [
                    Window(
                        FormattedTextControl(recent),
                        height=len(_RECENT.get()),
                        style="class:history",
                        wrap_lines=False,
                    ),
                    original,
                    Window(FormattedTextControl(footer), height=1),
                ],
                padding=1,
            )
            app.layout.container = ConditionalContainer(
                HSplit(
                    [
                        VSplit(
                            [
                                Window(
                                    portrait_control,
                                    width=28,
                                    height=12,
                                ),
                                panel,
                            ],
                            padding=2,
                            height=12,
                        )
                    ]
                ),
                filter=Condition(roomy),
                alternative_content=original,
            )
            if self.completer and (self.choices or getattr(self, "previews", None)):
                app.current_buffer.start_completion(select_first=False)

        answer = prompt(
            [("class:question", question.plain)],
            completer=self.completer,
            complete_while_typing=True,
            is_password=password,
            reserve_space_for_menu=6 if self.completer else 0,
            mouse_support=True,
            pre_run=ready,
            refresh_interval=0.125 if moving and roomy() else 0,
            color_depth=ColorDepth.DEPTH_1_BIT if console.no_color else None,
            style=Style.from_dict(
                {
                    "question": "bold",
                    "completion-menu.completion": f"bg:{COLOURS['surface']} {COLOURS['text']}",
                    "completion-menu.completion.current": f"bold noreverse bg:{look.primary} {COLOURS['ink']}",
                    "scrollbar.background": f"bg:{COLOURS['surface']}",
                    "scrollbar.button": f"bg:{look.secondary}",
                    "chosen": f"bold noreverse bg:{look.primary} {COLOURS['ink']}",
                    "hint": "",
                    "history": "italic",
                }
                if not console.no_color
                else {
                    "completion-menu.completion.current": "reverse",
                }
            ),
        )
        console.print(question + Text("•" * len(answer) if password else answer))
        preview = getattr(self, "preview", None) or getattr(self, "previews", {}).get(answer)
        if preview:
            console.print(Text(preview.description))
        return answer

    def process_response(self, value):
        """Keep validated recent answers beside the next question"""
        answer = super().process_response(value)
        if getattr(self, "required", False) and not answer:
            raise InvalidResponse("Add a value to continue")
        if not self.password:
            _RECENT.set((*_RECENT.get()[-2:], f"✓ {self.prompt.plain}: {answer}"))
        self.reaction = False
        return answer

    def on_validate_error(self, value, error):
        """React once while keeping Rich's validation message visible"""
        self.reaction = True
        super().on_validate_error(value, error)


class _Prompt(_Input, Prompt):
    """Validate choices and required answers through Rich"""


class _Confirm(_Input, Confirm):
    """Keep yes/no validation with the shared input controls"""


class _Number(_Input, FloatPrompt):
    """Keep number validation with the shared input controls"""


def complete_path(incomplete: str) -> list[str]:
    """Complete path prefixes and append a separator to directories"""
    # Typer's zsh backend uses native file completion when no values are returned
    if os.getenv("_MINI_COMPLETE") == "complete_zsh":
        return []
    directory, prefix = os.path.split(incomplete)
    try:
        return [
            os.path.join(directory, path.name) + (os.sep if path.is_dir() else "")
            for path in sorted(Path(directory or ".").expanduser().iterdir())
            if path.name.startswith(prefix)
            and (prefix.startswith(".") or not path.name.startswith("."))
        ]
    except OSError:
        return []


def ask(
    message: str,
    *,
    choices: Sequence[str] | Mapping[str, str] = (),
    suggestions: Sequence[str] | Mapping[str, str] = (),
    default: str = "",
    paths: bool = False,
    required: bool = False,
    ignore_case: bool = False,
    show_choices: bool = True,
    search: bool = False,
    previews: Mapping[str, Preview] | None = None,
) -> str:
    """Complete labelled choices, suggestions and paths with optional empty answers"""
    from prompt_toolkit.completion import PathCompleter, WordCompleter, merge_completers

    question = _Prompt(
        f"[accent]›[/accent] {message}",
        console=CONSOLE,
        choices=list(choices) or None,
        show_choices=show_choices and not CONSOLE.is_terminal,
        case_sensitive=not ignore_case,
        show_default=bool(default),
    )
    completers = []
    if choices or suggestions:
        values = choices or suggestions
        completers.append(
            WordCompleter(
                values,
                WORD=True,
                ignore_case=ignore_case,
                match_middle=search,
                display_dict=(
                    {key: label if previews else f"{key}  {label}" for key, label in values.items()}
                    if isinstance(values, Mapping)
                    else None
                ),
            )
        )
    if paths:
        completers.append(PathCompleter(expanduser=True))
    question.completer = merge_completers(completers) if completers else None
    question.required = required
    question.previews = previews or {}
    question.preview_default = default
    return question(default=default) if default or not (required or choices) else question()


def confirm(message: str, *, default: bool = False, preview: Preview | None = None) -> bool:
    """Ask for confirmation with the shared console and Rich validation"""
    question = _Confirm(f"[accent]›[/accent] {message}", console=CONSOLE)
    question.preview = preview
    return question(default=default)


def number(message: str, *, default: float) -> float:
    """Read a numeric answer with the shared console and Rich validation"""
    return _Number.ask(f"[accent]›[/accent] {message}", console=CONSOLE, default=default)
