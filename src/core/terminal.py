"""Shared Typer applications, Rich output and terminal input"""

import os
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
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

COLOURS = {
    "accent": "#b4577e",
    "success": "#4d806e",
    "warning": "#9b6e28",
    "error": "#ba5860",
}
THEME = Theme(
    {
        **COLOURS,
        "heading": f"bold {COLOURS['accent']}",
        "muted": "dim",
        "prompt": "bold",
        "prompt.default": COLOURS["accent"],
        "prompt.choices": "dim",
        "prompt.invalid": COLOURS["error"],
        "progress.description": "bold",
        "progress.percentage": COLOURS["accent"],
        "bar.complete": COLOURS["accent"],
        "bar.finished": COLOURS["success"],
        "bar.pulse": COLOURS["accent"],
    }
)
CONSOLE = Console(theme=THEME, highlight=False)
ERROR = Console(stderr=True, theme=THEME, highlight=False)

# Typer creates its own help console, so share the colour values with it
rich_utils.STYLE_OPTION = f"bold {COLOURS['accent']}"
rich_utils.STYLE_SWITCH = f"bold {COLOURS['success']}"
rich_utils.STYLE_USAGE = COLOURS["accent"]
rich_utils.STYLE_OPTIONS_PANEL_BORDER = COLOURS["accent"]
rich_utils.STYLE_COMMANDS_PANEL_BORDER = COLOURS["accent"]
rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = rich_utils.STYLE_OPTION
rich_utils.STYLE_ERRORS_PANEL_BORDER = COLOURS["error"]


def intro(title: str, message: str) -> None:
    """Give each mini a small, friendly entrance without clearing scrollback"""
    flower = "✿" if CONSOLE.encoding.lower().startswith("utf") else "*"
    CONSOLE.print(
        Panel(
            Text(message),
            title=Text(f"{flower} {title}", style="heading"),
            title_align="left",
            border_style="accent",
            box=box.ROUNDED,
            padding=(1, 2),
            width=min(72, CONSOLE.width),
        )
    )


def table(*headers: str, title: str | None = None) -> Table:
    """Use airy, compact tables with the same emphasis across minis"""
    view = Table(
        *headers,
        title=title,
        title_justify="left",
        title_style="heading",
        header_style="bold",
        border_style="muted",
        box=box.SIMPLE,
        padding=(0, 2),
        pad_edge=False,
    )
    if view.columns:
        view.columns[0].style = "accent"
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


def application(*, add_completion: bool = False, **options) -> typer.Typer:
    """Create a command app with the shared presentation and exception settings"""
    return typer.Typer(
        add_completion=add_completion,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
        **options,
    )


class _Input:
    """Keep keyboard input and presentation shared across prompt types"""

    completer = None

    def get_input(self, console, question, password, stream=None):
        """Use the active terminal session or Rich's ordinary input fallback"""
        from prompt_toolkit import prompt
        from prompt_toolkit.application import get_app, get_app_session
        from prompt_toolkit.input import DummyInput, PipeInput
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
            return super().get_input(console, question, password, stream=stream)
        return prompt(
            [("class:question", question.plain)],
            completer=self.completer,
            complete_while_typing=True,
            is_password=password,
            reserve_space_for_menu=6 if self.completer else 0,
            mouse_support=True,
            pre_run=(lambda: get_app().current_buffer.start_completion(select_first=False))
            if self.completer and self.choices
            else None,
            rprompt=[("class:hint", "↑↓ browse · tab" if self.completer else "enter to continue")],
            color_depth=ColorDepth.DEPTH_1_BIT if console.no_color else None,
            style=Style.from_dict(
                {
                    "question": f"bold {COLOURS['accent']}",
                    "completion-menu.completion": "bg:#fce8ef #4f3544",
                    "completion-menu.completion.current": f"bold bg:{COLOURS['accent']} #ffffff",
                    "scrollbar.background": "bg:#edd1dc",
                    "scrollbar.button": f"bg:{COLOURS['accent']}",
                    "hint": "italic",
                }
                if not console.no_color
                else {
                    "completion-menu.completion.current": "reverse",
                }
            ),
        )


class _Prompt(_Input, Prompt):
    """Validate choices and required answers through Rich"""

    def process_response(self, value):
        """Reject empty answers when the caller requires a value"""
        value = super().process_response(value)
        if self.required and not value:
            raise InvalidResponse("Add a value to continue")
        return value


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
    suggestions: Sequence[str] = (),
    default: str = "",
    paths: bool = False,
    required: bool = False,
    ignore_case: bool = False,
    show_choices: bool = True,
    search: bool = False,
) -> str:
    """Complete labelled choices, suggestions and paths with optional empty answers"""
    from prompt_toolkit.completion import PathCompleter, WordCompleter, merge_completers

    question = _Prompt(
        f"[accent]›[/accent] {message}",
        console=CONSOLE,
        choices=list(choices) or None,
        show_choices=show_choices,
        case_sensitive=not ignore_case,
        show_default=bool(default),
    )
    completers = []
    if choices or suggestions:
        completers.append(
            WordCompleter(
                choices or suggestions,
                WORD=True,
                ignore_case=ignore_case,
                match_middle=search,
                display_dict=(
                    {key: f"{key}  {label}" for key, label in choices.items()}
                    if isinstance(choices, Mapping)
                    else None
                ),
            )
        )
    if paths:
        completers.append(PathCompleter(expanduser=True))
    question.completer = merge_completers(completers) if completers else None
    question.required = required
    return question(default=default) if default or not (required or choices) else question()


def confirm(message: str, *, default: bool = False) -> bool:
    """Ask for confirmation with the shared console and Rich validation"""
    return _Confirm.ask(f"[accent]›[/accent] {message}", console=CONSOLE, default=default)


def number(message: str, *, default: float) -> float:
    """Read a numeric answer with the shared console and Rich validation"""
    return _Number.ask(f"[accent]›[/accent] {message}", console=CONSOLE, default=default)
