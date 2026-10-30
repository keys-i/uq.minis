"""Shared Typer applications, Rich output and terminal input

Mini commands share prompt validation, recoverable drafts, navigation and
resource cleanup through this module. Input helpers preserve typed entry
alongside visual controls and respect terminal size and motion preferences
"""

import asyncio
import calendar
import os
import random
import sys
import time
import webbrowser
from collections.abc import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Generator,
    Iterator,
    Mapping,
    Sequence,
)
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from datetime import time as Time
from functools import partial
from math import atan2, cos, isfinite, pi
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TextIO
from urllib.parse import urlsplit

import typer
from rich import box
from rich.cells import cell_len, get_character_cell_size, set_cell_size
from rich.console import Console, Group, RenderableType
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, FloatPrompt, InvalidResponse, Prompt, PromptBase
from rich.table import Table
from rich.text import Text, TextType
from rich.theme import Theme
from typer import rich_utils
from typer._click.exceptions import ClickException

from uq_minis.core.art import COLOURS as COLOURS
from uq_minis.core.art import FPS, Habitat, Preview, blend, habitats
from uq_minis.core.common import MiniError

if TYPE_CHECKING:
    from prompt_toolkit.completion import Completer, Completion


THEME = Theme({
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
})
CONSOLE = Console(theme=THEME, highlight=False)
ERROR = Console(stderr=True, theme=THEME, highlight=False)


_HABITAT: ContextVar[Habitat | None] = ContextVar("mini_habitat", default=None)
_MENU = ContextVar("mini_menu", default=False)
_PREVIEW: ContextVar[Preview | None] = ContextVar("mini_preview", default=None)
_DRAFT: ContextVar[dict[str, str | float] | None] = ContextVar("mini_draft", default=None)
_RESTORE = ContextVar("mini_restore", default=False)
still = False
_POKES: dict[str, int] = {}


def _width(columns: int) -> int:
    """Keep input and loading columns in the same place"""
    return min(96, round(columns * 0.55))


class Back(Exception):
    """Leave an unfinished interactive workflow and return to the mini picker"""


def _key(key: str) -> str:
    """Use the host OS's labels for terminal keyboard chords"""
    return key.replace("Ctrl+", "⌃").replace("Alt+", "⌥") if sys.platform == "darwin" else key


def _marquee(text: str, width: int, elapsed: float) -> str:
    """Glide back and forth through long captions without splitting wide characters"""
    span = cell_len(text) - width
    if span <= 0:
        return text
    travel = span / 4
    phase = elapsed % (2 * travel + 1.6)
    position = (phase - 0.8) * 4 if phase < travel + 1.6 else (2 * travel + 1.6 - phase) * 4
    offset = min(span, max(0, int(position)))
    start = 0
    while offset > 0:
        offset -= get_character_cell_size(text[start])
        start += 1
    return set_cell_size(text[start:], width)


def _look() -> Habitat:
    return _HABITAT.get() or habitats()["numbat"]


@contextmanager
def habitat(name: str, *, menu: bool = True) -> Generator[None]:
    """Apply a mini's shared theme, navigation and recoverable draft

    The named habitat comes from the bundled species catalogue
    Enable ``menu`` to let Escape return to the mini picker
    Restore the previous theme, preview and draft when the context exits,
    including after an error or cancellation
    """
    look = habitats()[name]
    token = _HABITAT.set(look)
    navigation = _MENU.set(menu)
    preview = _PREVIEW.set(None)
    draft = _DRAFT.set({})
    restore = _RESTORE.set(False)
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
        _MENU.reset(navigation)
        _PREVIEW.reset(preview)
        _DRAFT.reset(draft)
        _RESTORE.reset(restore)


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
    _PREVIEW.set(None)
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
        row_styles=[
            f"{colour} on {blend(COLOURS['surface'], colour, 0.22)}"
            for colour in (_look().primary, _look().secondary)
        ],
    )
    if view.columns:
        view.columns[0].style = "key"
    return view


@contextmanager
def activity(title: str, *, show: bool = True) -> Generator[Callable[[float | None, str], None]]:
    """Keep task progress beside the current scene or selected preview

    Yield an update callback accepting a completion fraction from 0 to 1
    and a readable stage description; ``None`` means the duration is unknown
    Redirected output uses ordinary log lines and ``show=False`` suppresses
    presentation while retaining the same callback contract
    """
    look, preview = _look(), _PREVIEW.get()
    moving = not still and os.getenv("MINI_MOTION", "1") != "0" and not CONSOLE.no_color

    class Loading(Progress):
        """Keep the current scene beside a compact, wrapping task and progress bar"""

        def get_renderable(self) -> RenderableType:
            right = Group(
                Text(
                    self.tasks[0].description if self.tasks else title,
                    style=f"bold {look.secondary}",
                ),
                super().get_renderable(),
            )
            if CONSOLE.width < 80 or CONSOLE.height < 24:
                return right
            width = _width(CONSOLE.width)
            size = (max(40, width - 4), max(16, min(64, CONSOLE.height - 6)))
            if preview:
                left = (
                    Text(preview.description)
                    if CONSOLE.no_color
                    else preview.fit(size, elapsed=time.monotonic() if moving else None)
                )
            else:
                countries = look.countries(size[0] - 2)
                size = (
                    size[0],
                    max(
                        1,
                        min(
                            28,
                            round(size[0] * 7 / 20),
                            CONSOLE.height - len(countries.split("\n")) - 5,
                        ),
                    ),
                )
                frame = int(time.monotonic() * FPS) % (FPS * 3) if moving else 0
                left = look.picture(frame, "breathe" if moving else "idle", size=size).copy()
                left.append(
                    f"  {look.name} ↗\n", style=f"bold underline {look.primary} link {look.source}"
                )
                left.append("  ")
                for index, line in enumerate(countries.split("\n")):
                    if index:
                        left.append("\n  ")
                    left.append(line)
            layout = Table.grid(expand=True)
            layout.add_column(width=width)
            layout.add_column(width=2)
            layout.add_column(ratio=1)
            layout.add_row(left, "", right)
            return layout

    with Loading(
        SpinnerColumn("dots", style="accent"),
        BarColumn(bar_width=20),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=CONSOLE,
        disable=not show or not CONSOLE.is_terminal,
        refresh_per_second=8,
        transient=True,
    ) as progress:
        task = progress.add_task(title, total=None)
        previous: list[str | int] = ["", -1]

        def update(done: float | None, stage: str) -> None:
            fraction = max(0, min(1, done)) if done is not None else None
            total, completed = (100, fraction * 100) if fraction is not None else (None, 0)
            if progress.tasks[task].total != total:
                started = progress.tasks[task].start_time
                # Rich treats None as "keep the total" during reset
                if total is None:
                    progress.tasks[task].total = None
                progress.reset(task, total=total, completed=round(completed), description=stage)
                progress.tasks[task].start_time = started
            progress.update(task, description=stage, completed=completed)
            if show and not CONSOLE.is_terminal:
                name = stage.partition(" · ")[0]
                bucket = int(fraction * 10) if fraction is not None else -1
                if name != previous[0] or bucket != previous[1]:
                    CONSOLE.print(
                        (f"{fraction:.0%} · " if fraction is not None else "") + stage,
                        markup=False,
                        style="accent",
                    )
                    previous[:] = [name, bucket]

        update(None, title)
        yield update


def application(
    *, theme: str = "numbat", add_completion: bool = False, **options: Any
) -> typer.Typer:
    """Create a command app with the shared presentation and exception settings"""
    app = typer.Typer(
        add_completion=add_completion,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
        **options,
    )
    setattr(app, "habitat", theme)
    return app


def problem(error: Exception) -> None:
    """Keep expected failures readable and consistent across terminal workflows"""
    message = error.format_message() if isinstance(error, ClickException) else str(error)
    ERROR.print(Text("› " + message, style="error"))


def recover(error: Exception, arguments: Sequence[str]) -> list[str]:
    """Reopen editable answers only after an explicit choice, without repeating actions"""
    import shlex

    problem(error)
    CONSOLE.print(
        "Your answers are kept for review · nothing retries automatically",
        style="muted",
    )
    choice = ask(
        "What next?",
        choices={
            "edit": "Review saved answers and rerun",
            "menu": "Back to the mini menu",
        },
        default="menu",
        show_choices=False,
    )
    if choice == "menu":
        raise Back
    if arguments:
        while True:
            value = ask("Command arguments", default=shlex.join(arguments))
            try:
                arguments = shlex.split(value)
                break
            except ValueError as exc:
                problem(exc)
    if "--submit" in arguments and not confirm(
        "Submit again? Check for any partial submissions first", default=False
    ):
        raise Back
    _RESTORE.set(True)
    return [argument for argument in arguments if argument != "--yes"]


class _Input[T: (str, bool, float)](PromptBase[T]):
    """Keep keyboard input and presentation shared across prompt types"""

    completer: Completer | None = None
    labels: Mapping[str, str] = {}
    previews: Mapping[str, Preview] = {}
    previewer: Callable[[str], Awaitable[Preview | None]] | None = None
    preview: Preview | None = None
    preview_default = ""
    radio = False
    paths = False
    details: Mapping[str, str] = {}
    actions: Mapping[str, tuple[str, Callable[[str], None]]] = {}
    minimum: float | None = None
    maximum: float | None = None
    step = 1.0
    initial = 0.0
    control = "slider"
    calendar_default = date.min
    unit = ""
    stops: Mapping[float, str] = {}
    parse: Callable[[str], float] = float
    required = False
    described = False
    reaction = False

    # Rich's classmethod fallback also works through a stateful instance override
    def get_input(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, console: Console, prompt: TextType, password: bool, stream: TextIO | None = None
    ) -> str:
        """Use the active terminal session or Rich's ordinary input fallback"""
        question = Text.from_markup(prompt) if isinstance(prompt, str) else prompt
        from prompt_toolkit import prompt as read_input
        from prompt_toolkit.application import get_app, get_app_session
        from prompt_toolkit.data_structures import Point
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.formatted_text import StyleAndTextTuples
        from prompt_toolkit.input import DummyInput, PipeInput
        from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
        from prompt_toolkit.layout import (
            ConditionalContainer,
            FloatContainer,
            HSplit,
            VSplit,
            Window,
        )
        from prompt_toolkit.layout.containers import VerticalAlign
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.layout.menus import CompletionsMenuControl
        from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
        from prompt_toolkit.output import ColorDepth
        from prompt_toolkit.styles import Style

        input = get_app_session().input
        plain = (
            stream is not None
            or isinstance(input, DummyInput)
            or os.getenv("TERM") == "dumb"
            or not console.is_terminal
            and not isinstance(input, PipeInput)
        )

        def roomy() -> bool:
            size = get_app_session().output.get_size()
            return (
                min(console.width, size.columns) >= 80
                and size.rows >= 24
                and console.encoding.lower().startswith("utf")
            )

        loaded: dict[str, Preview | None] = {}
        loading = ""
        failure = ""

        def selection() -> str:
            buffer = get_app().current_buffer
            chosen = buffer.complete_state and buffer.complete_state.current_completion
            return chosen.text if chosen else buffer.text or self.preview_default

        def sample() -> Preview | None:
            key = selection()
            return self.preview or self.previews.get(key) or loaded.get(key) or _PREVIEW.get()

        def split() -> int:
            size = get_app_session().output.get_size()
            return _width(min(console.width, size.columns))

        def content_width() -> int:
            columns = min(console.width, get_app_session().output.get_size().columns)
            return max(1, columns - (split() + 2 if roomy() else 0))

        def sculpture() -> tuple[int, int]:
            size = get_app_session().output.get_size()
            if sample():
                return max(40, split() - 4), max(16, min(64, size.rows - 6))
            columns = max(40, split() - 4)
            rows = max(1, min(28, max(16, round(columns * 7 / 20)), size.rows - footprint() - 2))
            return columns, rows

        def footprint() -> int:
            if sample():
                return 6
            return len(look.countries(max(38, split() - 6)).split("\n")) + 3

        look = _look()
        if (
            console.is_terminal
            and console.width >= 44
            and console.encoding.lower().startswith("utf")
            and (plain or not roomy())
        ):
            console.print(look.picture(), end="")
            console.print(Text(look.name + " ↗", style=f"bold underline link {look.source}"))
            console.print(Text(f"{look.status} · {look.country}\n{look.place}\n"))
        if plain:
            if not getattr(self, "described", False):
                if self.control == "clock":
                    minutes = int(self.initial)
                    console.print(
                        f"Default time: {minutes // 60:02}:{minutes % 60:02}", markup=False
                    )
                for label, detail in self.details.items():
                    console.print(Text(f"{label}: {detail}"))
                if self.choices:
                    for key, label in self.labels.items():
                        console.print(Text(f"{key} · {label}"))
                if preview := getattr(self, "preview", None):
                    console.print(Text(preview.description))
                for key, preview in getattr(self, "previews", {}).items():
                    console.print(Text(f"{key} · {preview.description}"))
                self.described = True
            return super().get_input(console, prompt, password, stream=stream)
        status = {
            "vulnerable": ("#9ee59a", "#77d7e3"),
            "endangered": ("#ffae77", "#f4d66b"),
            "critically endangered": ("#ff879a", "#ffc18a"),
            "extinct": ("#c6adff", "#8dbefa"),
        }[look.status.partition(" · ")[0]]
        allowed = os.getenv("MINI_MOTION", "1") != "0" and not console.no_color
        moving = allowed and not still
        started = time.monotonic()
        reacting = getattr(self, "reaction", False)
        action = "peek" if reacting else "idle"
        acted = started if reacting else started - 2
        deadline = started + random.uniform(2, 5)
        state = "idle"
        drawn = (0, "idle")
        last = ("", None)
        hover = ""
        helping = False
        hot = ""
        pressed = ""
        bubble = 0.0
        blurb = ""
        menu = _MENU.get()
        bindings = KeyBindings()
        shown: dict[str, tuple[str, float]] = {}
        touches: dict[str, list[str]] = {}
        review_scroll = 0
        review_lines = max(1, len(self.details))
        clock_part = 0
        calendar_part = 0
        changed_at = started - 1
        sweeps: dict[str, tuple[float, float, float, float]] = {}
        radio, selected_default = self.radio, self.preview_default
        stops = tuple(self.stops)

        def caption(value: str, width: int = 40, slot: str = "picture") -> str:
            now = time.monotonic()
            if slot not in shown or shown[slot][0] != value:
                shown[slot] = (value, now)
            if not moving and cell_len(value) > width:
                return set_cell_size(value, width - 1) + "…"
            return _marquee(value, width, now - shown[slot][1])

        def sweep(slot: str, target: float, cycle: float = 0) -> float:
            """Ease visual markers while keeping the editable value immediate"""
            now = time.monotonic()
            origin, previous, destination, began = sweeps.get(slot, (target, target, target, now))
            progress = min(1, (now - began) / 0.22) if moving else 1
            current = origin + (previous - origin) * (1 - (1 - progress) ** 3)
            if target != destination:
                distance = target - current
                if cycle:
                    distance = (distance + cycle / 2) % cycle - cycle / 2
                sweeps[slot] = (current, current + distance, target, now)
                return current if moving else target
            sweeps[slot] = (origin, previous, destination, began)
            return current

        class Choices(CompletionsMenuControl):
            """Scroll the selected completion while keeping native input and pointer behaviour"""

            def create_content(self, width: int, height: int):
                """Use the actual menu width after terminal layout and resizing"""
                content = super().create_content(width, height)
                original = content.get_line
                state = get_app().current_buffer.complete_state

                def line(index: int) -> StyleAndTextTuples:
                    if radio and state:
                        choice = state.completions[index]
                        selected = index == state.complete_index or (
                            state.complete_index is None and choice.text == selected_default
                        )
                        style = (
                            "class:completion-menu.completion.current"
                            if selected
                            else f"class:row{index % 2}"
                        )
                        text = (
                            caption(choice.display_text, max(1, width - 3), "choice")
                            if selected
                            else set_cell_size(choice.display_text, max(1, width - 3))
                        )
                        return [
                            (style + f" fg:{look.primary}", "> " if selected else "  "),
                            (style, set_cell_size(text, max(1, width - 3)) + " "),
                        ]
                    if state and index == state.complete_index:
                        choice = state.completions[index]
                        text = caption(choice.display_text, max(1, width - 2), "choice")
                        style = f"class:completion-menu.completion.current {choice.style} {choice.selected_style}"
                        return [
                            (style + f" fg:{look.primary}", ">"),
                            (style, set_cell_size(text, max(1, width - 2)) + " "),
                        ]
                    return [
                        (item[0] + f" class:row{index % 2}", item[1], item[2])
                        if len(item) == 3
                        else (item[0] + f" class:row{index % 2}", item[1])
                        for item in original(index)
                    ]

                content.get_line = line
                return content

            def mouse_handler(self, mouse_event: MouseEvent):
                """Browse on hover without confirming the highlighted choice"""
                event = mouse_event
                buffer = get_app().current_buffer
                state = buffer.complete_state
                index = event.position.y
                if event.event_type == MouseEventType.MOUSE_MOVE:
                    if (
                        state
                        and 0 <= index < len(state.completions)
                        and index != state.complete_index
                    ):
                        buffer.go_to_completion(index)
                        get_app().invalidate()
                    return None
                return super().mouse_handler(event)

        def command(name: str) -> None:
            nonlocal helping, moving, hot, pressed, failure
            global still
            hot = pressed = ""
            if name == "menu" and menu:
                get_app().exit(exception=Back())
                return
            if name == "species":
                failure = ""
                try:
                    url = urlsplit(look.source)
                    if url.scheme != "https" or not url.hostname or url.username or url.password:
                        failure = "Animal page unavailable"
                    else:
                        if not webbrowser.open(look.source):
                            failure = "Browser unavailable · try again later"
                except ValueError:
                    failure = "Animal page unavailable"
                except OSError:
                    failure = "Browser unavailable · try again later"
            elif name == "keys":
                helping = not helping
            elif name == "motion" and allowed:
                still = not still
                moving = not still
                get_app().refresh_interval = 1 / FPS if moving or bubble else 0
            get_app().invalidate()

        @bindings.add("escape", "h")
        @bindings.add(
            "?",
            filter=Condition(lambda: not get_app().current_buffer.text and not password),
        )
        def shortcuts(event: KeyPressEvent) -> None:
            command("keys")

        @bindings.add("escape", filter=Condition(lambda: menu or helping))
        @bindings.add("escape", "left", filter=Condition(lambda: menu))
        def back(event: KeyPressEvent) -> None:
            command("keys" if helping else "menu")

        @bindings.add("escape", "m")
        def motion(event: KeyPressEvent) -> None:
            command("motion")

        @bindings.add("escape", "a")
        def species(event: KeyPressEvent) -> None:
            command("species")

        @bindings.add("c-space")
        def complete(event: KeyPressEvent) -> None:
            event.current_buffer.start_completion(select_first=False)

        def directory() -> Completion | None:
            state = get_app().current_buffer.complete_state
            if not self.paths or not state:
                return None
            choice = state.current_completion or (
                state.completions[0] if len(state.completions) == 1 else None
            )
            return choice if choice and choice.text.endswith(os.sep) else None

        @bindings.add("tab", filter=Condition(lambda: directory() is not None), eager=True)
        def descend(event: KeyPressEvent) -> None:
            if choice := directory():
                event.current_buffer.apply_completion(choice)
                event.current_buffer.start_completion(select_first=False)

        def value() -> float:
            try:
                number = self.parse(get_app().current_buffer.text)
                return number if isfinite(number) else self.initial
            except ValueError, MiniError:
                return self.initial

        def adjust(number: float, *, relative: bool = False) -> None:
            nonlocal changed_at
            assert self.minimum is not None and self.maximum is not None
            if relative:
                if stops:
                    at = min(range(len(stops)), key=lambda index: abs(stops[index] - value()))
                    number = stops[max(0, min(len(stops) - 1, at + int(number)))]
                else:
                    number = value() + self.step * number
                    if self.control == "clock":
                        number %= 1440
            buffer = get_app().current_buffer
            number = max(self.minimum, min(self.maximum, round(number, 8)))
            buffer.text = (
                f"{int(number) // 60:02}:{int(number) % 60:02}"
                if self.control == "clock"
                else f"{number:g}"
            )
            buffer.cursor_position = len(buffer.text)
            changed_at = time.monotonic()
            get_app().invalidate()

        @bindings.add("left", filter=Condition(lambda: self.minimum is not None), eager=True)
        @bindings.add("right", filter=Condition(lambda: self.minimum is not None), eager=True)
        @bindings.add("up", filter=Condition(lambda: self.control == "clock"), eager=True)
        @bindings.add("down", filter=Condition(lambda: self.control == "clock"), eager=True)
        def nudge(event: KeyPressEvent) -> None:
            step = 60 if self.control == "clock" and clock_part == 0 else 1
            adjust(-step if event.key_sequence[0].key in {"left", "down"} else step, relative=True)

        @bindings.add(
            "tab", filter=Condition(lambda: self.control in {"clock", "calendar"}), eager=True
        )
        @bindings.add(
            "s-tab", filter=Condition(lambda: self.control in {"clock", "calendar"}), eager=True
        )
        def unit(event: KeyPressEvent) -> None:
            nonlocal clock_part, calendar_part, changed_at
            if self.control == "clock":
                clock_part = 1 - clock_part
            else:
                calendar_part = (
                    calendar_part + (-1 if event.key_sequence[0].key == "s-tab" else 1)
                ) % 3
            changed_at = time.monotonic()
            get_app().invalidate()

        def selected_day() -> date:
            try:
                return date.fromisoformat(get_app().current_buffer.text)
            except ValueError:
                return self.calendar_default

        def turn_day(days: int = 0, months: int = 0, *, target: date | None = None) -> None:
            nonlocal changed_at
            chosen = target or selected_day()
            try:
                if months:
                    index = max(
                        0, min(9999 * 12 - 1, (chosen.year - 1) * 12 + chosen.month - 1 + months)
                    )
                    year, month = index // 12 + 1, index % 12 + 1
                    chosen = chosen.replace(
                        year=year,
                        month=month,
                        day=min(chosen.day, calendar.monthrange(year, month)[1]),
                    )
                chosen += timedelta(days=days)
            except OverflowError:
                return
            get_app().current_buffer.text = chosen.isoformat()
            get_app().current_buffer.cursor_position = len(get_app().current_buffer.text)
            changed_at = time.monotonic()
            get_app().invalidate()

        @bindings.add("left", filter=Condition(lambda: self.control == "calendar"), eager=True)
        @bindings.add("right", filter=Condition(lambda: self.control == "calendar"), eager=True)
        @bindings.add("up", filter=Condition(lambda: self.control == "calendar"), eager=True)
        @bindings.add("down", filter=Condition(lambda: self.control == "calendar"), eager=True)
        def calendar_key(event: KeyPressEvent) -> None:
            key = event.key_sequence[0].key
            delta = -1 if key in {"left", "up"} else 1
            if calendar_part:
                turn_day(months=delta * (1 if calendar_part == 1 else 12))
            else:
                turn_day(days={"left": -1, "right": 1, "up": -7, "down": 7}[key])

        def calendar_click(
            event: MouseEvent, *, days: int = 0, months: int = 0, target: date | None = None
        ) -> None:
            if event.event_type == MouseEventType.MOUSE_UP and event.button == MouseButton.LEFT:
                turn_day(days, months, target=target)
            elif event.event_type in {MouseEventType.SCROLL_UP, MouseEventType.SCROLL_DOWN}:
                turn_day(months=-1 if event.event_type == MouseEventType.SCROLL_UP else 1)

        def clock_click(
            event: MouseEvent, part: int, delta: int = 0, *, face: bool = False
        ) -> None:
            nonlocal clock_part
            if delta and footer_height() >= 6 and event.position.y != 2:
                return
            if event.button == MouseButton.LEFT and (
                event.event_type == MouseEventType.MOUSE_UP
                or face
                and event.event_type == MouseEventType.MOUSE_MOVE
            ):
                clock_part = part
                dx, dy = (event.position.x - (7 + part * 18)) / 5, (event.position.y - 2) / 2
                if face and dx * dx + dy * dy >= 0.25:
                    amount = round(atan2(dx, -dy) % (2 * pi) / (2 * pi) * (24 if part == 0 else 60))
                    current = int(value())
                    adjust(
                        (amount % 24) * 60 + current % 60
                        if part == 0
                        else current // 60 * 60 + amount % 60
                    )
                else:
                    adjust(delta, relative=True)
            elif event.event_type in {MouseEventType.SCROLL_UP, MouseEventType.SCROLL_DOWN}:
                clock_part = part
                step = 60 if part == 0 else 1
                adjust(
                    step if event.event_type == MouseEventType.SCROLL_UP else -step, relative=True
                )
            get_app().invalidate()

        def scroll(mouse_event: MouseEvent | int) -> None:
            nonlocal review_scroll
            event = mouse_event
            delta = (
                event
                if isinstance(event, int)
                else -3
                if event.event_type == MouseEventType.SCROLL_UP
                else 3
                if event.event_type == MouseEventType.SCROLL_DOWN
                else 0
            )
            review_scroll = max(0, min(review_lines - 1, review_scroll + delta))
            get_app().invalidate()

        @bindings.add("escape", "up", filter=Condition(lambda: bool(self.details)))
        @bindings.add("escape", "down", filter=Condition(lambda: bool(self.details)))
        @bindings.add("pageup", filter=Condition(lambda: bool(self.details)))
        @bindings.add("pagedown", filter=Condition(lambda: bool(self.details)))
        def page(event: KeyPressEvent) -> None:
            scroll(-3 if event.key_sequence[-1].key in {"up", "pageup"} else 3)

        @bindings.add("left", filter=Condition(lambda: "left" in self.actions), eager=True)
        @bindings.add("right", filter=Condition(lambda: "right" in self.actions), eager=True)
        def linked(event: KeyPressEvent) -> None:
            nonlocal failure
            try:
                self.actions[event.key_sequence[0].key][1](selection())
                failure = ""
            except (MiniError, OSError) as exc:
                failure = str(exc)
            get_app().invalidate()

        def meter(event: MouseEvent, delta: float = 0) -> None:
            if event.event_type in {MouseEventType.SCROLL_UP, MouseEventType.SCROLL_DOWN}:
                adjust(1 if event.event_type == MouseEventType.SCROLL_UP else -1, relative=True)
            elif event.button == MouseButton.LEFT and (
                event.event_type == MouseEventType.MOUSE_UP
                or event.event_type == MouseEventType.MOUSE_MOVE
                and self.control == "slider"
            ):
                if self.control == "dial":
                    if delta:
                        adjust(delta, relative=True)
                    return
                assert self.minimum is not None and self.maximum is not None
                fraction = max(0, min(1, (event.position.x - 2) / (span() - 1)))
                if stops:
                    adjust(stops[round(fraction * (len(stops) - 1))])
                    return
                number = self.minimum + (self.maximum - self.minimum) * fraction
                adjust(self.minimum + round((number - self.minimum) / self.step) * self.step)

        def span() -> int:
            label = self.stops.get(value(), f"{value():g}{self.unit}")
            return max(8, min(24, content_width() - cell_len(label) - 4))

        def button(name: str, event: MouseEvent) -> None:
            nonlocal hot, pressed
            if event.event_type == MouseEventType.MOUSE_MOVE:
                hot = name
            elif event.event_type == MouseEventType.MOUSE_DOWN:
                pressed = name
            elif event.event_type == MouseEventType.MOUSE_UP:
                command(name)
                return
            get_app().invalidate()

        def shortcuts_text() -> StyleAndTextTuples:
            return [
                ("class:question", "  Keyboard shortcuts\n\n"),
                (
                    "",
                    f"  ↑↓     browse choices\n  Tab    fill a choice\n  {_key('Ctrl+Space')}  suggestions\n",
                ),
                (
                    "",
                    f"  {_key('Ctrl+U')}  clear line\n  {_key('Ctrl+W')}  delete word\n  {_key('Ctrl+L')}  redraw\n",
                ),
                ("", f"  Esc / {_key('Alt+←')}  menu\n" if menu else ""),
                ("", f"  {_key('Alt+M')}   pause motion\n" if allowed else ""),
                ("", f"  {_key('Alt+A')}   animal page\n"),
                ("", f"  {_key('Ctrl+C')}  cancel\n\n  ? / {_key('Alt+H')}  shortcuts"),
            ]

        def portrait():
            nonlocal action, acted, deadline, state, hover, last, hot, pressed, drawn, bubble
            if helping:
                return shortcuts_text()
            now = time.monotonic()
            if bubble and now >= bubble:
                bubble = 0
                get_app().refresh_interval = 1 / FPS if moving else 0
            buffer = get_app().current_buffer
            chosen = buffer.complete_state and buffer.complete_state.current_completion
            preview = sample()
            pose = "idle"
            frame = 0
            # Paint the menu before parsing the animal's larger movement file
            if moving and not preview and get_app().renderer.last_rendered_screen is not None:
                focus = "look" if chosen else "listen" if buffer.text else "idle"
                changed = (buffer.text, chosen.text if chosen else None)
                if focus != state or changed != last:
                    state = focus
                    last = changed
                    hover = ""
                    bubble = 0
                    hot = pressed = ""
                    action, acted = focus if focus != "idle" else "blink", now
                    deadline = now + random.uniform(3, 6)
                if now >= deadline:
                    action = random.choice([pose for pose in look.idle.split() if pose != action])
                    acted = now
                    deadline = now + look.seconds(action) + random.uniform(3, 7)
                if action != "idle" and now - acted < look.seconds(action):
                    pose = action
                    frame = int(max(0, now - acted) * FPS)
                elif focus != "idle":
                    pose = focus
                    frame = FPS - 1
                else:
                    pose, frame = "breathe", int(now * FPS) % (FPS * 3)
            drawn = (frame, pose)
            fragments: StyleAndTextTuples = []
            picture = (
                look.picture(frame, pose, size=sculpture())
                if not preview
                else Text(preview.description)
                if console.no_color
                else preview.fit(sculpture(), elapsed=now if moving else None)
            )
            if preview:
                lines = picture.split("\n", allow_blank=True)
                picture = Text()
                for index, line in enumerate(lines):
                    if index:
                        picture.append("\n")
                    picture.append(
                        caption(line.plain, sculpture()[0])
                        if line.cell_len > sculpture()[0]
                        else line
                    )
            for segment in picture.render(console):
                colour = segment.style.color if segment.style else None
                background = segment.style.bgcolor if segment.style else None
                fragments.append((
                    " ".join(
                        colour
                        for colour in (
                            f"fg:{colour.get_truecolor().hex}" if colour else "",
                            f"bg:{background.get_truecolor().hex}" if background else "",
                        )
                        if colour
                    ),
                    segment.text,
                ))
            if not preview:
                phase = (1 - cos(now * pi / 4)) / 2 if moving else 0
                colour = blend(look.primary, look.secondary, phase)
                fragments.append((
                    f"class:animal underline fg:{colour}"
                    + (
                        f" bg:{blend(COLOURS['surface'], colour, 0.18)}" if hot == "species" else ""
                    ),
                    f"  {look.name} ↗\n",
                ))
                if now < bubble:
                    lines = Text(blurb).wrap(console, sculpture()[0] - 2)[:2]
                    fragments.append((
                        "class:bubble",
                        "  ╭ " + "\n  │ ".join(line.plain for line in lines) + "\n  ╰─\n",
                    ))
                else:
                    metadata = Text()
                    for index, line in enumerate(look.countries(999).split("\n")):
                        if index:
                            metadata.append("\n  ")
                        boundary = line.plain.rfind("  ") + 2 if "  " in line.plain else 0
                        fixed, label = line[:boundary], line[boundary:]
                        available = max(1, sculpture()[0] - 2 - fixed.cell_len)
                        visible = _marquee(label.plain, available, now if moving else 0).rstrip()
                        start = label.plain.find(visible)
                        label = label[max(0, start) : max(0, start) + len(visible)]
                        if index in (0, 2):
                            label.stylize(
                                blend(*status, phase)
                                if index == 0
                                else blend(look.leaf, look.water, phase)
                            )
                        metadata.append(fixed)
                        metadata.append(label)
                    fragments.append(("", "  "))
                    for segment in metadata.render(console):
                        fg = segment.style.color if segment.style else None
                        bg = segment.style.bgcolor if segment.style else None
                        fragments.append((
                            "class:country"
                            + (f" fg:{fg.get_truecolor().hex}" if fg else "")
                            + (f" bg:{bg.get_truecolor().hex}" if bg else ""),
                            segment.text,
                        ))
                    fragments.append(("", "\n"))
            return fragments

        def touch(mouse_event: MouseEvent) -> None:
            event = mouse_event
            nonlocal action, acted, deadline, state, hover, bubble, blurb, hot
            if helping:
                return
            if event.event_type in {MouseEventType.MOUSE_MOVE, MouseEventType.MOUSE_UP}:
                x, y = event.position.x, event.position.y
                if not sample() and y == sculpture()[1] and 2 <= x < cell_len(look.name) + 4:
                    hot = "species"
                    if (
                        event.event_type == MouseEventType.MOUSE_UP
                        and event.button == MouseButton.LEFT
                    ):
                        command("species")
                    get_app().invalidate()
                    return
                if hot == "species":
                    hot = ""
                    get_app().invalidate()
                if region := look.region(*drawn, x, y, size=sculpture()):
                    buffer = get_app().current_buffer
                    chosen = buffer.complete_state and buffer.complete_state.current_completion
                    if sample():
                        return
                    previous = hover
                    hover = {
                        "ears": look.head,
                        "pet": look.body,
                        "object": f"{look.object} · click to explore",
                    }[region]
                    if event.event_type == MouseEventType.MOUSE_MOVE:
                        if (
                            moving
                            and previous != hover
                            and (
                                action == "idle" or time.monotonic() - acted >= look.seconds(action)
                            )
                        ):
                            action, acted = (
                                "peek" if x < (sculpture()[0] + 2) / 2 else "look",
                                time.monotonic(),
                            )
                            deadline = acted + random.uniform(4, 7)
                        get_app().invalidate()
                        return
                    state = "look" if chosen else "listen" if buffer.text else "idle"
                    poses = getattr(
                        look,
                        {
                            "ears": "head_moves",
                            "pet": "body_moves",
                            "object": "object_moves",
                        }[region],
                    ).split()
                    previous = touches.setdefault(region, [])
                    unused = [pose for pose in poses if pose not in previous]
                    if not unused:
                        previous.clear()
                        unused = poses
                    action = random.choice(unused)
                    previous.append(action)
                    acted = time.monotonic()
                    if region != "object":
                        _POKES[look.animal] = min(4, _POKES.get(look.animal, 0) + 1)
                        if _POKES[look.animal] > 3:
                            lines = look.quip.split("|")
                            blurb = random.choice(
                                [line for line in lines if line != blurb] or lines
                            )
                            bubble = acted + 4.5
                            get_app().refresh_interval = 1 / FPS
                    deadline = acted + random.uniform(4, 9)
                    get_app().invalidate()
                elif hover:
                    hover = ""
                    get_app().invalidate()

        def footer() -> StyleAndTextTuples:
            parts: StyleAndTextTuples
            if self.control == "calendar":
                chosen = selected_day()
                hint = f"{('day', 'month', 'year')[calendar_part]} · Tab unit · arrows · Enter"
                pulse = max(0, 1 - (time.monotonic() - changed_at) / 0.3) if moving else 0
                focus = f"bold bg:{blend(COLOURS['surface'], look.primary, 0.18 + 0.15 * pulse)} {COLOURS['text']}"
                if footer_height() < 9:
                    return [
                        ("class:chosen", " < ", partial(calendar_click, days=-1)),
                        ("class:chosen", chosen.strftime("%d %b %Y")),
                        ("class:chosen", " > ", partial(calendar_click, days=1)),
                        ("class:hint", f"\n  {hint}"),
                    ]
                parts = [
                    ("class:button", " < ", partial(calendar_click, months=-1)),
                    (focus if calendar_part else "class:chosen", f" {chosen:%B %Y} "),
                    ("class:button", " > ", partial(calendar_click, months=1)),
                    ("class:button", " today ", partial(calendar_click, target=date.today())),
                    ("class:hint", "\n Mo  Tu  We  Th  Fr  Sa  Su\n"),
                ]
                for week, days in enumerate(calendar.monthcalendar(chosen.year, chosen.month)):
                    for day in days:
                        style = focus if day == chosen.day else f"class:row{week % 2}"
                        parts.append((
                            style,
                            f" {day:2} " if day else "    ",
                            partial(calendar_click, target=chosen.replace(day=day))
                            if day
                            else calendar_click,
                        ))
                    parts.append(("", "\n"))
                parts.append(("class:hint", hint))
                return parts
            if self.minimum is not None and self.maximum is not None:
                number = value()
                if self.control == "clock":
                    parts = []
                    if footer_height() >= 6:
                        ring = (
                            (5, 0),
                            (8, 0),
                            (9, 1),
                            (10, 2),
                            (9, 3),
                            (8, 4),
                            (5, 4),
                            (2, 4),
                            (1, 3),
                            (0, 2),
                            (1, 1),
                            (2, 0),
                        )
                        for row in range(5):
                            for part, (amount, maximum, unit) in enumerate((
                                (int(number) // 60, 24, "h"),
                                (int(number) % 60, 60, "m"),
                            )):
                                if part:
                                    parts.append(("class:hint", " : " if row == 2 else "   "))
                                step = 60 if part == 0 else 1
                                parts.append((
                                    "class:button" if row == 2 else "",
                                    "− " if row == 2 else "  ",
                                    partial(clock_click, part=part, delta=-step),
                                ))
                                text = list(
                                    (
                                        "  ╭─────╮  ",
                                        " ╱       ╲ ",
                                        f"│  {amount:02} {unit}   │",
                                        " ╲       ╱ ",
                                        "  ╰─────╯  ",
                                    )[row]
                                )
                                position = sweep(f"clock{part}", amount / maximum * 12, 12)
                                x, y = ring[round(position) % 12]
                                if row == y:
                                    text[x] = "●"
                                parts.append((
                                    "class:chosen" if part == clock_part else "class:hint",
                                    "".join(text),
                                    partial(clock_click, part=part, face=True),
                                ))
                                parts.append((
                                    "class:button" if row == 2 else "",
                                    " +" if row == 2 else "  ",
                                    partial(clock_click, part=part, delta=step),
                                ))
                            parts.append(("", "\n"))
                        parts.append(("class:hint", "Tab unit · arrows · drag · Enter"))
                        return parts
                    for part, (amount, maximum) in enumerate((
                        (int(number) // 60, 24),
                        (int(number) % 60, 60),
                    )):
                        if part:
                            parts.append(("class:hint", " : "))
                        step = 60 if part == 0 else 1
                        style = (
                            "class:completion-menu.completion.current"
                            if part == clock_part
                            else "class:row1"
                        )
                        dial = "◯◔◑◕"[min(3, int(amount / maximum * 4))]
                        parts.extend([
                            ("class:button", " − ", partial(clock_click, part=part, delta=-step)),
                            (style, f" {dial} {amount:02} ", partial(clock_click, part=part)),
                            ("class:button", " + ", partial(clock_click, part=part, delta=step)),
                        ])
                    parts.append(("class:hint", "\n  Tab unit · ← → · Enter"))
                    return parts
                fraction = max(0, min(1, (number - self.minimum) / (self.maximum - self.minimum)))
                if stops:
                    fraction = min(
                        range(len(stops)), key=lambda index: abs(stops[index] - number)
                    ) / (len(stops) - 1)
                width = span()
                at = round(sweep("slider", fraction) * (width - 1))
                dial = "◯◔◑◕●"[round(fraction * 4)]
                bar = "━" * at + "●" + "─" * (width - at - 1)
                label = self.stops.get(number, f"{number:g}{self.unit}")
                parts = (
                    [
                        ("class:chosen", "  − ", lambda event: meter(event, -1)),
                        ("class:chosen", f" {dial}  {number:g}{self.unit} ", meter),
                        ("class:chosen", " + ", lambda event: meter(event, 1)),
                    ]
                    if self.control == "dial"
                    else [("class:chosen", f"  {bar}  {label}", meter)]
                )
                parts.append(("class:hint", "\n  ← → adjust · Enter to keep"))
                return parts
            buffer = get_app().current_buffer
            chosen = buffer.complete_state and buffer.complete_state.current_completion
            action = "enter to choose" if chosen else "enter"
            if self.completer and not (chosen or buffer.text):
                action = "↑↓ move · tab fill"
            if hover:
                action = hover
            elif chosen:
                assert buffer.complete_state is not None
                assert buffer.complete_state.complete_index is not None
                count = len(buffer.complete_state.completions)
                action += f" · {buffer.complete_state.complete_index + 1}/{count}"
            fragments: StyleAndTextTuples = [
                (
                    "class:chosen" if chosen else "class:hint",
                    f"  {action}",
                )
            ]
            if loading:
                fragments.append(("class:hint", f"\n  ◌ Preparing {loading}…"))
            elif failure:
                fragments.append((f"fg:{COLOURS['error']}", f"\n  {failure}"))
            elif self.details:
                fragments.append(("class:hint", f"\n  {_key('Alt+↑↓')} or scroll to review"))
            elif self.actions:
                fragments.append((
                    "class:hint",
                    "\n  "
                    + " · ".join(
                        f"{'←' if key == 'left' else '→'} {label}"
                        for key, (label, _) in self.actions.items()
                    ),
                ))
            elif roomy() and not helping and not sample() and not (loading or failure):
                fragments.append(("class:hint", "\n  hover · click to explore"))
            return fragments

        def footer_height() -> int:
            if self.control not in {"calendar", "clock"}:
                return 2
            height = sculpture()[1] + 6 if roomy() else get_app_session().output.get_size().rows
            return min(
                9 if self.control == "calendar" else 6,
                max(2, height - 2 - (3 if roomy() else 1)),
            )

        def nav():
            fragments: StyleAndTextTuples = []
            buttons = {"menu": ("← menu", "esc")} if menu else {}
            buttons["keys"] = ("keys", "?")
            if allowed:
                buttons["motion"] = ("play" if not moving else "pause", _key("Alt+M"))
            width = content_width()
            chords = sum(cell_len(label + key) + 3 for label, key in buttons.values())
            chords += (len(buttons) - 1) * 2
            for index, (name, (label, key)) in enumerate(buttons.items()):
                if index:
                    fragments.append(("", "  "))
                style = (
                    "class:pressed"
                    if pressed == name
                    else "class:hot"
                    if hot == name
                    else "class:button"
                )
                click = partial(button, name)
                text = f" {label} {key} " if chords <= width else f" {label} "
                fragments.append((style, text, click))
            return fragments

        def ready():
            app = get_app()
            app.erase_when_done = True
            if provider := self.previewer:
                changed = asyncio.Event()
                buffer = app.current_buffer
                pending: asyncio.Future[Preview | None] | None = None
                wanted: str | None = None

                def request(_: object = None) -> None:
                    nonlocal wanted, failure
                    key = selection()
                    if key == wanted:
                        return
                    wanted, failure = key, ""
                    changed.set()
                    if pending and selection() != loading:
                        pending.cancel()

                async def load() -> None:
                    nonlocal loading, failure, pending
                    buffer.on_text_changed += request
                    buffer.on_completions_changed += request
                    request()
                    try:
                        while True:
                            await changed.wait()
                            changed.clear()
                            await asyncio.sleep(0.15)
                            key = selection()
                            failure = ""
                            if key not in self.labels or key in self.previews or key in loaded:
                                continue
                            loading = key
                            app.invalidate()
                            try:
                                pending = asyncio.ensure_future(provider(key))
                                result = await pending
                            except asyncio.CancelledError:
                                task = asyncio.current_task()
                                if task is None or task.cancelling():
                                    raise
                                continue
                            except (MiniError, OSError) as exc:
                                result = None
                                if selection() == key:
                                    failure = f"Sample unavailable: {exc} · choose another or retry"
                            else:
                                if len(loaded) == 8:
                                    loaded.pop(next(iter(loaded)))
                                loaded[key] = result
                            finally:
                                pending = None
                                loading = ""
                                app.invalidate()
                    finally:
                        buffer.on_text_changed -= request
                        buffer.on_completions_changed -= request

                app.create_background_task(load())
            original = app.layout.container
            # The native input otherwise expands to the full portrait height
            assert isinstance(original, (HSplit, Window))

            def input_height() -> int:
                return max(
                    2,
                    min(
                        max(
                            4 if self.radio else 6 if self.completer else 2,
                            2
                            + min(
                                6,
                                len(state.completions)
                                if (state := get_app().current_buffer.complete_state)
                                else 0,
                            ),
                        ),
                        get_app_session().output.get_size().rows - (6 if self.details else 3),
                    ),
                )

            original.height = input_height
            for window in app.layout.find_all_windows():
                if isinstance(window.content, CompletionsMenuControl):
                    window.content = Choices()
            for container in app.layout.walk():
                if isinstance(container, FloatContainer):
                    for floating in container.floats:
                        if floating.ycursor:
                            floating.xcursor = False
                            floating.left = floating.right = 0
            portrait_control = FormattedTextControl(portrait)
            portrait_control.mouse_handler = touch

            panel = HSplit(
                [
                    Window(FormattedTextControl(nav), height=1),
                    original,
                    Window(FormattedTextControl(footer), height=footer_height),
                ],
                padding=1,
                align=VerticalAlign.TOP,
            )
            review_windows: list[Window] = []
            if self.details:

                def facts() -> StyleAndTextTuples:
                    nonlocal review_lines
                    fragments: StyleAndTextTuples = []
                    for key, value in self.details.items():
                        text = Text(key + "  ", style="bold").append(value, style="not bold")
                        for line in text.wrap(console, content_width()):
                            fragments.extend(
                                (
                                    "class:chosen" if segment.style and segment.style.bold else "",
                                    segment.text,
                                )
                                for segment in line.render(console, end="")
                            )
                            fragments.append(("", "\n"))
                    review_lines = max(1, sum(part[1] == "\n" for part in fragments))
                    return fragments[:-1]

                review = FormattedTextControl(
                    facts,
                    get_cursor_position=lambda: Point(0, min(review_scroll, review_lines - 1)),
                )
                review.mouse_handler = scroll
                review_window = Window(
                    review,
                    height=lambda: max(
                        1,
                        min(
                            review.preferred_height(
                                content_width(),
                                14,
                                wrap_lines=True,
                                get_line_prefix=None,
                            )
                            or 1,
                            (
                                sculpture()[1] + footprint()
                                if roomy()
                                else get_app_session().output.get_size().rows
                            )
                            - input_height()
                            - (6 if roomy() else 3),
                        ),
                    ),
                    wrap_lines=True,
                )
                panel.children.insert(1, review_window)
                review_windows.append(review_window)
            app.layout.container = ConditionalContainer(
                HSplit([
                    VSplit(
                        [
                            Window(
                                portrait_control,
                                width=split,
                                height=lambda: sculpture()[1] + footprint(),
                            ),
                            panel,
                        ],
                        padding=2,
                        height=lambda: sculpture()[1] + footprint(),
                    )
                ]),
                filter=Condition(roomy),
                alternative_content=HSplit([
                    ConditionalContainer(
                        Window(FormattedTextControl(shortcuts_text), height=12),
                        filter=Condition(lambda: helping),
                    ),
                    Window(FormattedTextControl(nav), height=1),
                    *review_windows,
                    original,
                    Window(FormattedTextControl(footer), height=footer_height),
                ]),
            )
            if self.completer and (self.choices or getattr(self, "previews", None)):
                app.current_buffer.start_completion(select_first=False)

        rows = [
            blend(COLOURS["surface"], look.primary, 0.10),
            blend(COLOURS["surface"], look.secondary, 0.32),
        ]
        answer = read_input(
            [("class:question", question.plain)],
            completer=self.completer,
            complete_while_typing=True,
            is_password=password,
            # Let the shared layout size the picker instead of reserving six input rows
            reserve_space_for_menu=1 if self.completer else 0,
            mouse_support=True,
            key_bindings=bindings,
            pre_run=ready,
            refresh_interval=1 / FPS if moving else 0,
            color_depth=ColorDepth.DEPTH_1_BIT if console.no_color else None,
            style=Style.from_dict(
                {
                    "question": f"bold {look.secondary}",
                    "completion-menu.completion": f"bg:{COLOURS['surface']} {COLOURS['text']}",
                    "completion-menu.completion.current": f"bold noreverse bg:{blend(COLOURS['surface'], look.primary, 0.18)} {COLOURS['text']}",
                    "row0": f"bg:{rows[0]} {COLOURS['text']}",
                    "row1": f"bg:{rows[1]} {COLOURS['text']}",
                    "scrollbar.background": f"bg:{COLOURS['surface']}",
                    "scrollbar.button": f"bg:{look.secondary}",
                    "chosen": f"bold {look.primary}",
                    "hint": "",
                    "bubble": f"{look.secondary}",
                    "animal": f"bold {look.primary}",
                    "status": status[0],
                    "country": look.secondary,
                    "place": look.leaf,
                    "button": f"bg:{blend(COLOURS['surface'], look.secondary, 0.12)} {look.secondary}",
                    "hot": f"bold bg:{blend(COLOURS['surface'], look.secondary, 0.35)} {COLOURS['text']}",
                    "pressed": f"bold bg:{blend(COLOURS['surface'], look.secondary, 0.5)} {COLOURS['text']}",
                }
                if not console.no_color
                else {
                    "completion-menu.completion.current": "reverse",
                }
            ),
        )
        if loaded.get(answer) is not None:
            self.preview = loaded[answer]
        return answer

    def process_response(self, value: str) -> T:
        """Keep validated drafts available for recovery without logging every interaction"""
        answer = super().process_response(value)
        if isinstance(answer, float) and (
            not isfinite(answer)
            or self.minimum is not None
            and answer < self.minimum
            or self.maximum is not None
            and answer > self.maximum
        ):
            raise InvalidResponse(
                f"Choose a number from {self.minimum:g} to {self.maximum:g}"
                if self.minimum is not None and self.maximum is not None
                else "Choose a finite number"
            )
        if isinstance(answer, float) and self.stops and answer not in self.stops:
            raise InvalidResponse("Choose a marked value with the slider or type its label")
        if getattr(self, "required", False) and not answer:
            raise InvalidResponse("Add a value to continue")
        if not self.password:
            if preview := self.preview or self.previews.get(str(answer)):
                _PREVIEW.set(preview)
            if (draft := _DRAFT.get()) is not None and not isinstance(self, Confirm):
                draft[self.prompt.plain] = answer
        self.reaction = False
        return answer

    def on_validate_error(self, value: str, error: InvalidResponse) -> None:
        """React once while keeping Rich's validation message visible"""
        self.reaction = True
        super().on_validate_error(value, error)


class _Prompt(_Input[str], Prompt):  # pyright: ignore[reportIncompatibleMethodOverride]
    """Validate choices and required answers through Rich"""


class _Date(_Input[str], Prompt):  # pyright: ignore[reportIncompatibleMethodOverride]
    """Keep calendar entry valid without leaving the current field"""

    def process_response(self, value: str) -> str:
        """Accept ISO dates and reject impossible calendar days"""
        try:
            value = date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise InvalidResponse("Choose a day or type a date as YYYY-MM-DD") from exc
        return super().process_response(value)


class _Confirm(_Input[bool], Confirm):  # pyright: ignore[reportIncompatibleMethodOverride]
    """Keep yes/no validation with the shared input controls"""


class _Number(_Input[float], FloatPrompt):  # pyright: ignore[reportIncompatibleMethodOverride]
    """Keep number validation with the shared input controls"""

    def process_response(self, value: str) -> float:
        """Accept field-specific numeric notation before shared range validation"""
        try:
            parsed = float(self.parse(value))
        except MiniError as exc:
            raise InvalidResponse(str(exc)) from exc
        except (ValueError, OverflowError) as exc:
            raise InvalidResponse("Enter a valid number") from exc
        return super().process_response(f"{parsed:g}")


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
    preview: Preview | None = None,
    previews: Mapping[str, Preview] | None = None,
    previewer: Callable[[str], Awaitable[Preview | None]] | None = None,
    details: Mapping[str, str] | None = None,
    actions: Mapping[str, tuple[str, Callable[[str], None]]] | None = None,
    lookup: Callable[[str], Awaitable[Sequence[str]]] | None = None,
) -> str:
    """Read an answer through the shared, recoverable terminal interface

    Args:
        message: Question shown beside the active input
        choices: Accepted values, optionally mapped to human-readable labels
        suggestions: Completion hints that still permit an unlisted answer
        default: Initial answer, reused when an optional prompt is left empty
        paths: Browse nested files and directories with Tab completion
        required: Keep the prompt open until a non-empty answer is supplied
        ignore_case: Accept choice text without requiring matching letter case
        show_choices: Include accepted values in non-interactive prompt text
        search: Match choices anywhere within their text instead of only a prefix
        preview: Persistent sample shown beside this prompt
        previews: Preloaded samples keyed by accepted choice
        previewer: Cancellable async loader for the highlighted choice's sample
        details: Final-review facts shown beside the active input
        actions: Left/right key labels and callbacks receiving the highlighted value
        lookup: Async search predictions, debounced and cancelled on changed input

    Returns:
        The validated value, using ``default`` when an empty answer is allowed

    Raises:
        Back: Escape was pressed inside a mini with menu navigation enabled
        KeyboardInterrupt: The person cancelled the prompt
    """
    from prompt_toolkit.application import get_app
    from prompt_toolkit.completion import (
        CompleteEvent,
        Completer,
        Completion,
        ThreadedCompleter,
        WordCompleter,
        merge_completers,
    )
    from prompt_toolkit.document import Document

    if _RESTORE.get():
        saved = (_DRAFT.get() or {}).get(f"› {message}", default)
        if not choices or saved in choices:
            default = str(saved)
    question = _Prompt(
        f"[accent]›[/accent] {message}",
        console=CONSOLE,
        choices=list(choices) or None,
        show_choices=show_choices and not CONSOLE.is_terminal,
        case_sensitive=not ignore_case,
        show_default=bool(default),
    )
    completers: list[Completer] = []
    if choices or suggestions:
        values = choices or suggestions
        completers.append(
            WordCompleter(
                list(values),
                WORD=True,
                ignore_case=ignore_case,
                match_middle=search,
                display_dict=(
                    {
                        key: label if previews or previewer or details else f"{key}  {label}"
                        for key, label in values.items()
                    }
                    if isinstance(values, Mapping)
                    else None
                ),
            )
        )
    if paths:

        class Paths(Completer):
            """Browse one directory at a time without blocking the interaction loop"""

            def get_completions(
                self, document: Document, complete_event: CompleteEvent
            ) -> Iterator[Completion]:
                prefix = document.text_before_cursor
                for path in complete_path(prefix):
                    yield Completion(path, start_position=-len(prefix))

        completers.append(ThreadedCompleter(Paths()))
    if lookup:
        provider = lookup
        cache: dict[str, Sequence[str]] = {}

        class Lookup(Completer):
            """Debounce remote suggestions and release obsolete requests with the prompt"""

            def get_completions(
                self, document: Document, complete_event: CompleteEvent
            ) -> Iterator[Completion]:
                return iter(())

            async def get_completions_async(
                self, document: Document, complete_event: CompleteEvent
            ) -> AsyncGenerator[Completion]:
                buffer = get_app().current_buffer
                if document.cursor_position != len(document.text):
                    return
                await asyncio.sleep(0.25)
                if buffer.text != document.text:
                    # Native completion only retries appended text, so replacement needs a restart
                    asyncio.get_running_loop().call_soon(buffer.start_completion)
                    return
                query = document.text
                if query not in cache:
                    task = asyncio.ensure_future(provider(query))

                    def cancel(_: object) -> None:
                        if buffer.text != query:
                            task.cancel()

                    buffer.on_text_changed += cancel
                    try:
                        values = await task
                    except asyncio.CancelledError:
                        if buffer.text == query:
                            raise
                        asyncio.get_running_loop().call_soon(buffer.start_completion)
                        return
                    finally:
                        buffer.on_text_changed -= cancel
                    if len(cache) == 32:
                        cache.pop(next(iter(cache)))
                    cache[query] = tuple(values[:10])
                if buffer.text == query:
                    for value in cache[query]:
                        yield Completion(value, start_position=-len(query))

        completers.append(Lookup())
    question.completer = merge_completers(completers) if completers else None
    question.required = required
    question.paths = paths
    question.labels = (
        choices
        if isinstance(choices, Mapping)
        else suggestions
        if isinstance(suggestions, Mapping)
        else {}
    )
    question.previews = previews or {}
    question.preview = preview
    question.previewer = previewer
    question.details = details or {}
    question.actions = actions or {}
    question.preview_default = default
    question.radio = bool(choices) and len(choices) <= 10
    return question(default=default) if default or not (required or choices) else question()


def confirm(
    message: str,
    *,
    default: bool = False,
    preview: Preview | None = None,
    details: Mapping[str, str] | None = None,
) -> bool:
    """Ask a yes/no question with an explicit default and optional final review

    Native terminals share the same highlighted choices and preview panel as
    text inputs; plain terminals accept Rich's yes/no spellings
    Invalid answers stay in the prompt and confirmations are not restored
    automatically when retrying a failed workflow
    """
    question = _Confirm(f"[accent]›[/accent] {message}", console=CONSOLE)
    question.preview = preview
    question.details = details or {}
    question.radio = True
    question.preview_default = "y" if default else "n"
    from prompt_toolkit.completion import WordCompleter

    question.completer = WordCompleter(
        ["y", "n"], display_dict={"y": "Yes", "n": "No"}, ignore_case=True
    )
    return question(default=default)


def number(
    message: str,
    *,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float = 1,
    control: Literal["slider", "dial", "clock"] = "slider",
    unit: str = "",
    stops: Mapping[float, str] | None = None,
    parse: Callable[[str], float] = float,
) -> float:
    """Read a finite number using a slider, dial or typed value

    Supply both bounds to enable an interactive control; arrows and the wheel
    adjust it by ``step``, and sliders also support pointer dragging
    ``stops`` defines discrete values in display order and accepts their labels
    ``parse`` handles typed input such as durations; ``unit`` is display-only

    Returns:
        A validated number within the bounds, or an exact listed stop

    Raises:
        ValueError: Bounds, step or the default make the control invalid
        Back: The person returned to the mini picker
    """
    if _RESTORE.get():
        saved = (_DRAFT.get() or {}).get(f"› {message}", default)
        if isinstance(saved, float):
            default = saved
    if stops:
        if len(stops) < 2 or default not in stops or not all(map(isfinite, stops)):
            raise ValueError("A stepped slider needs two finite stops and a listed default")
        minimum, maximum = min(stops), max(stops)
    if minimum is not None or maximum is not None:
        if (
            minimum is None
            or maximum is None
            or not all(map(isfinite, (minimum, maximum, step, default)))
            or not minimum <= default <= maximum
            or minimum >= maximum
            or step <= 0
        ):
            raise ValueError(
                "Numeric controls need finite bounds, a positive step and a default inside them"
            )
    question = _Number(f"[accent]›[/accent] {message}", console=CONSOLE)
    question.minimum, question.maximum, question.step = minimum, maximum, step
    question.initial, question.control, question.unit = default, control, unit
    question.stops = stops or {}
    labels = {label.casefold(): value for value, label in question.stops.items()}
    question.parse = lambda value: (
        labels[value.strip().casefold()] if value.strip().casefold() in labels else parse(value)
    )
    question.show_default = not stops and control != "clock"
    return question(default=default)


def day(message: str, *, default: date | None = None) -> date:
    """Choose a calendar date or type a valid YYYY-MM-DD value

    Default to today unless a date is supplied or a saved draft is restored
    Arrows move across days, Tab selects the month or year, and Enter accepts
    the date; month changes clamp the day to the destination month's length
    Impossible dates stay editable and the returned date has no time zone
    """
    saved = (_DRAFT.get() or {}).get(f"› {message}") if _RESTORE.get() else None
    if isinstance(saved, str):
        default = date.fromisoformat(saved)
    question = _Date(f"[accent]›[/accent] {message}", console=CONSOLE)
    question.control = "calendar"
    question.calendar_default = default or date.today()
    return date.fromisoformat(question(default=question.calendar_default.isoformat()))


def clock(message: str, *, default: str = "18:00") -> Time:
    """Set a local time with paired hour/minute dials or a typed clock value

    Tab switches units; arrows, the wheel and dragging adjust the active dial
    Accept HH:MM, HH:MM:SS or a 12-hour value such as 6:30 PM
    Return a timezone-naive time at minute precision, discarding typed seconds
    Invalid input stays in the prompt; dial adjustments wrap across midnight
    """

    def parse(value: str) -> float:
        for pattern in ("%H:%M", "%H:%M:%S", "%I:%M %p"):
            try:
                result = datetime.strptime(value.strip(), pattern)
                return result.hour * 60 + result.minute
            except ValueError:
                pass
        raise MiniError("Choose hours and minutes or type a time as HH:MM, such as 18:30")

    minutes = int(
        number(
            message,
            default=parse(default),
            minimum=0,
            maximum=1439,
            control="clock",
            parse=parse,
        )
    )
    return Time(minutes // 60, minutes % 60)
