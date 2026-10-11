"""Shared Typer applications, Rich output and terminal input"""

import os
import random
import sys
import time
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial
from math import cos, pi
from pathlib import Path

import typer
from rich import box
from rich.cells import cell_len, get_character_cell_size, set_cell_size
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
from typer._click.exceptions import ClickException

from uq_minis.core.art import Habitat, Preview, _habitats, blend

COLOURS = {
    "accent": "#ffb66f",
    "success": "#6cddb0",
    "warning": "#f4d66b",
    "error": "#ff879a",
    "ink": "#20262d",
    "peach": "#ffb68d",
    "mint": "#83dfcf",
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
_MENU = ContextVar("mini_menu", default=False)
_RECENT = ContextVar("mini_answers", default=())
_DRAFT = ContextVar("mini_draft", default=None)
_RESTORE = ContextVar("mini_restore", default=False)
_STILL = False
_POKES = {}


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
    return _HABITAT.get() or _habitats()["numbat"]


@contextmanager
def habitat(name: str, *, menu: bool = True):
    """Apply a mini's look and restore it after completion, errors or cancellation"""
    look = _habitats()[name]
    token = _HABITAT.set(look)
    navigation = _MENU.set(menu)
    answers = _RECENT.set(())
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
        _RECENT.reset(answers)
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
        row_styles=[_look().primary, _look().secondary],
    )
    if view.columns:
        view.columns[0].style = "key"
    return view


@contextmanager
def activity(title: str, *, show: bool = True):
    """Show real progress, unknown-duration stages and useful redirected logs"""
    with Progress(
        SpinnerColumn("dots", style="accent"),
        TextColumn("{task.description}", markup=False, style="heading"),
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
                        style="accent",
                    )
                    previous[:] = [name, bucket]

        update(None, title)
        yield update


def application(*, theme: str = "numbat", add_completion: bool = False, **options) -> typer.Typer:
    """Create a command app with the shared presentation and exception settings"""
    app = typer.Typer(
        add_completion=add_completion,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
        **options,
    )
    app.habitat = theme
    return app


def problem(error: Exception) -> None:
    """Keep expected failures readable and consistent across terminal workflows"""
    message = error.format_message() if isinstance(error, ClickException) else str(error)
    ERROR.print(Text("› " + message, style="error"))


def recover(error: Exception, arguments: Sequence[str]) -> list[str]:
    """Reopen editable answers only after an explicit choice, without repeating actions"""
    import shlex

    problem(error)
    CONSOLE.print("Your answers are kept for review · nothing retries automatically", style="muted")
    choice = ask(
        "What next?",
        choices={"edit": "Review saved answers and rerun", "menu": "Back to the mini menu"},
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


class _Input:
    """Keep keyboard input and presentation shared across prompt types"""

    completer = None

    def get_input(self, console, question, password, stream=None):
        """Use the active terminal session or Rich's ordinary input fallback"""
        from prompt_toolkit import prompt
        from prompt_toolkit.application import get_app, get_app_session
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.input import DummyInput, PipeInput
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import ConditionalContainer, HSplit, VSplit, Window
        from prompt_toolkit.layout.containers import VerticalAlign
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.layout.menus import CompletionsMenuControl
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
        status = {
            "endangered": ("#ffae77", "#f4d66b"),
            "critically endangered": ("#ff879a", "#ffc18a"),
            "extinct": ("#c6adff", "#8dbefa"),
        }[look.status.partition(" · ")[0]]
        allowed = os.getenv("MINI_MOTION", "1") != "0" and not console.no_color
        moving = allowed and not _STILL
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
        bubble = 0
        blurb = ""
        menu = _MENU.get()
        bindings = KeyBindings()
        shown = {}
        touches = {}

        def caption(value, width=40, slot="picture"):
            now = time.monotonic()
            if slot not in shown or shown[slot][0] != value:
                shown[slot] = (value, now)
            if not moving and cell_len(value) > width:
                return set_cell_size(value, width - 1) + "…"
            return _marquee(value, width, now - shown[slot][1])

        class Choices(CompletionsMenuControl):
            """Scroll the selected completion while keeping native input and pointer behaviour"""

            def create_content(self, width, height):
                """Use the actual menu width after terminal layout and resizing"""
                content = super().create_content(width, height)
                original = content.get_line
                state = get_app().current_buffer.complete_state

                def line(index):
                    if state and index == state.complete_index:
                        choice = state.completions[index]
                        text = caption(choice.display_text, max(1, width - 2), "choice")
                        style = f"class:completion-menu.completion.current {choice.style} {choice.selected_style}"
                        return [(style, " " + set_cell_size(text, max(1, width - 2)) + " ")]
                    return [
                        (style + f" class:row{index % 2}", text, *handler)
                        for style, text, *handler in original(index)
                    ]

                content.get_line = line
                return content

        def command(name):
            nonlocal helping, moving, hot, pressed
            global _STILL
            hot = pressed = ""
            if name == "menu" and menu:
                get_app().exit(exception=Back())
                return
            if name == "keys":
                helping = not helping
            elif name == "motion" and allowed:
                _STILL = not _STILL
                moving = not _STILL
                get_app().refresh_interval = 1 / 16 if moving or bubble else 0
            get_app().invalidate()

        @bindings.add("escape", "h")
        @bindings.add(
            "?",
            filter=Condition(lambda: not get_app().current_buffer.text and not password),
        )
        def shortcuts(event):
            command("keys")

        @bindings.add("escape", filter=Condition(lambda: menu or helping))
        @bindings.add("escape", "left", filter=Condition(lambda: menu))
        def back(event):
            command("keys" if helping else "menu")

        @bindings.add("escape", "m")
        def motion(event):
            command("motion")

        @bindings.add("c-space")
        def complete(event):
            event.current_buffer.start_completion(select_first=False)

        def button(name, event):
            nonlocal hot, pressed
            if event.event_type == MouseEventType.MOUSE_MOVE:
                hot = name
            elif event.event_type == MouseEventType.MOUSE_DOWN:
                pressed = name
            elif event.event_type == MouseEventType.MOUSE_UP:
                command(name)
                return
            get_app().invalidate()

        def shortcuts_text():
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
                ("", f"  {_key('Ctrl+C')}  cancel\n\n  ? / {_key('Alt+H')}  shortcuts"),
            ]

        def roomy():
            size = get_app_session().output.get_size()
            return (
                min(console.width, size.columns) >= 80
                and size.rows >= 24
                and console.encoding.lower().startswith("utf")
                and not console.no_color
            )

        def portrait():
            nonlocal action, acted, deadline, state, hover, last, hot, pressed, drawn, bubble
            if helping:
                return shortcuts_text()
            now = time.monotonic()
            if bubble and now >= bubble:
                bubble = 0
                get_app().refresh_interval = 1 / 16 if moving else 0
            buffer = get_app().current_buffer
            chosen = buffer.complete_state and buffer.complete_state.current_completion
            previews = getattr(self, "previews", {})
            key = chosen.text if chosen else buffer.text or getattr(self, "preview_default", "")
            preview = getattr(self, "preview", None) or previews.get(key)
            pose = "idle"
            frame = 0
            if moving and not preview:
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
                    frame = int(max(0, now - acted) * 8)
                elif focus != "idle":
                    pose = focus
                    frame = 7
                else:
                    pose, frame = "breathe", int(now * 8) % 16
            drawn = (frame, pose)
            fragments = []
            picture = look.picture(frame, pose) if not preview else preview.picture
            if preview and cell_len(preview.description) > 40:
                picture = Text()
                for index, line in enumerate(preview.picture.split("\n", allow_blank=True)):
                    if index:
                        picture.append("\n")
                    picture.append(caption(line.plain) if line.cell_len > 40 else line)
            for segment in picture.render(console):
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
            if not preview:
                phase = (1 - cos((now - started) * pi / 4)) / 2 if moving else 0
                colour = blend(look.primary, look.secondary, phase)
                fragments.append((f"class:animal fg:{colour}", f"  {look.name}\n"))
                if now < bubble:
                    lines = Text(blurb).wrap(console, 38)[:2]
                    fragments.append(
                        (
                            "class:bubble",
                            "  ╭ " + "\n  │ ".join(line.plain for line in lines) + "\n  ╰─\n",
                        )
                    )
                else:
                    colour = blend(*status, phase)
                    fragments.append((f"class:status fg:{colour}", f"  {look.status}\n  "))
                    elapsed = now - started if moving else 0
                    shift = int(elapsed / 3)
                    fade = min(1, max(0, elapsed % 3 - 2))
                    countries = look.country.split(" · ")
                    flags = (
                        look.flag.split("|") if look.flag else [f"{look.water} {look.secondary}"]
                    )
                    for index, country in enumerate(countries):
                        if index:
                            fragments.append(("class:country", " · "))
                        colours = flags[min(index, len(flags) - 1)].split()
                        for offset, letter in enumerate(country):
                            band = offset * len(colours) // len(country) + shift
                            colour = blend(
                                colours[band % len(colours)],
                                colours[(band + 1) % len(colours)],
                                fade,
                            )
                            fragments.append((f"class:country fg:{colour}", letter))
                    colour = blend(look.leaf, look.water, phase)
                    fragments.append((f"class:place fg:{colour}", f"\n  {look.place}\n"))
            return fragments

        def touch(event):
            nonlocal action, acted, deadline, state, hover, bubble, blurb
            if helping:
                return
            if event.event_type in {MouseEventType.MOUSE_MOVE, MouseEventType.MOUSE_UP}:
                x, y = event.position.x, event.position.y
                if region := look.region(*drawn, x, y):
                    buffer = get_app().current_buffer
                    chosen = buffer.complete_state and buffer.complete_state.current_completion
                    if getattr(self, "preview", None) or getattr(self, "previews", {}).get(
                        chosen.text if chosen else buffer.text
                    ):
                        return
                    hover = {
                        "ears": look.head,
                        "pet": look.body,
                        "object": f"{look.object} · click to explore",
                    }[region]
                    if event.event_type == MouseEventType.MOUSE_MOVE:
                        get_app().invalidate()
                        return
                    state = "look" if chosen else "listen" if buffer.text else "idle"
                    poses = getattr(
                        look,
                        {"ears": "head_moves", "pet": "body_moves", "object": "object_moves"}[
                            region
                        ],
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
                            get_app().refresh_interval = 1 / 16
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
            elif chosen:
                count = len(buffer.complete_state.completions)
                action += f" · {buffer.complete_state.complete_index + 1}/{count}"
            return [
                (
                    "class:chosen" if chosen else "class:hint",
                    f"  {action}",
                )
            ]

        def nav():
            fragments = []
            buttons = {"menu": ("← menu", "esc")} if menu else {}
            buttons["keys"] = ("keys", "?")
            if allowed:
                buttons["motion"] = ("play" if not moving else "pause", _key("Alt+M"))
            size = get_app_session().output.get_size()
            width = min(console.width, size.columns) - (46 if roomy() else 0)
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
            original = app.layout.container
            # The native input otherwise expands to the full portrait height
            original.height = lambda: max(
                6 if self.completer else 0,
                2
                + min(
                    6,
                    len(get_app().current_buffer.complete_state.completions)
                    if get_app().current_buffer.complete_state
                    else 0,
                ),
            )
            for window in app.layout.find_all_windows():
                if isinstance(window.content, CompletionsMenuControl):
                    window.content = Choices()
            portrait_control = FormattedTextControl(portrait)
            portrait_control.mouse_handler = touch

            def recent():
                answers = _RECENT.get()
                return [
                    (
                        "class:saved"
                        if moving
                        and time.monotonic() - started < 0.75
                        and index == len(answers) - 1
                        else "class:history",
                        answer + "\n",
                    )
                    for index, answer in enumerate(answers)
                ]

            panel = HSplit(
                [
                    Window(
                        FormattedTextControl(recent),
                        height=len(_RECENT.get()),
                        style="class:history",
                        wrap_lines=False,
                    ),
                    Window(FormattedTextControl(nav), height=1),
                    original,
                    Window(FormattedTextControl(footer), height=1),
                ],
                padding=1,
                align=VerticalAlign.TOP,
            )
            app.layout.container = ConditionalContainer(
                HSplit(
                    [
                        VSplit(
                            [
                                Window(
                                    portrait_control,
                                    width=44,
                                    height=22,
                                ),
                                panel,
                            ],
                            padding=2,
                            height=22,
                        )
                    ]
                ),
                filter=Condition(roomy),
                alternative_content=HSplit(
                    [
                        ConditionalContainer(
                            Window(FormattedTextControl(shortcuts_text), height=12),
                            filter=Condition(lambda: helping),
                        ),
                        Window(FormattedTextControl(nav), height=1),
                        original,
                        Window(FormattedTextControl(footer), height=1),
                    ]
                ),
            )
            if self.completer and (self.choices or getattr(self, "previews", None)):
                app.current_buffer.start_completion(select_first=False)

        rows = [
            blend(COLOURS["surface"], colour, 0.22) for colour in (look.primary, look.secondary)
        ]
        answer = prompt(
            [("class:question", question.plain)],
            completer=self.completer,
            complete_while_typing=True,
            is_password=password,
            reserve_space_for_menu=6 if self.completer else 0,
            mouse_support=True,
            key_bindings=bindings,
            pre_run=ready,
            refresh_interval=1 / 16 if moving else 0,
            color_depth=ColorDepth.DEPTH_1_BIT if console.no_color else None,
            style=Style.from_dict(
                {
                    "question": f"bold {look.secondary}",
                    "completion-menu.completion": f"bg:{COLOURS['surface']} {COLOURS['text']}",
                    "completion-menu.completion.current": f"bold noreverse bg:{look.primary} {COLOURS['ink']}",
                    "row0": f"bg:{rows[0]} {COLOURS['text']}",
                    "row1": f"bg:{rows[1]} {COLOURS['text']}",
                    "scrollbar.background": f"bg:{COLOURS['surface']}",
                    "scrollbar.button": f"bg:{look.secondary}",
                    "chosen": f"bold {look.primary}",
                    "hint": "",
                    "history": "italic",
                    "bubble": f"{look.secondary}",
                    "animal": f"bold {look.primary}",
                    "status": status[0],
                    "country": look.secondary,
                    "place": look.leaf,
                    "saved": f"bold {look.secondary}",
                    "button": f"bg:{COLOURS['surface']} {look.secondary}",
                    "hot": f"bold bg:{look.secondary} {COLOURS['ink']}",
                    "pressed": f"bold bg:{look.secondary} {COLOURS['ink']}",
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
        elif label := getattr(self, "labels", {}).get(answer):
            console.print(Text(label))
        return answer

    def process_response(self, value):
        """Keep validated recent answers beside the next question"""
        answer = super().process_response(value)
        if getattr(self, "required", False) and not answer:
            raise InvalidResponse("Add a value to continue")
        if not self.password:
            _RECENT.set((*_RECENT.get()[-2:], f"✓ {self.prompt.plain}: {answer}"))
            if (draft := _DRAFT.get()) is not None and not isinstance(self, Confirm):
                draft[self.prompt.plain] = answer
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

    if _RESTORE.get():
        saved = (_DRAFT.get() or {}).get(f"› {message}", default)
        if not choices or saved in choices:
            default = saved
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
    question.labels = (
        choices
        if isinstance(choices, Mapping)
        else suggestions
        if isinstance(suggestions, Mapping)
        else {}
    )
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
    if _RESTORE.get():
        default = (_DRAFT.get() or {}).get(f"› {message}", default)
    return _Number.ask(f"[accent]›[/accent] {message}", console=CONSOLE, default=default)
