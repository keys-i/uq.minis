"""Shared test inputs, isolated state and terminal setup"""

from __future__ import annotations

import random
import time
from io import StringIO
from operator import itemgetter
from threading import Timer
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import prompt_toolkit
import pytest
from prompt_toolkit.application import Application, create_app_session, get_app, get_app_session
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import PipeInput, create_pipe_input
from prompt_toolkit.layout import (
    Layout,
    Window,
    menus,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from tests.fixtures import Frames, Screen
from uq_minis.core import terminal


@pytest.fixture
def pipe(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(terminal, "_POKES", {})
    monkeypatch.setattr(terminal, "still", False)
    with (
        create_pipe_input() as input,
        create_app_session(input=input, output=DummyOutput()),
    ):
        preview = terminal._PREVIEW.set(None)
        try:
            yield input
        finally:
            terminal._PREVIEW.reset(preview)


@pytest.fixture
def entry(monkeypatch: pytest.MonkeyPatch):
    prompt = Mock(return_value="first")
    monkeypatch.setattr(prompt_toolkit, "prompt", prompt)
    return prompt


@pytest.fixture
def cursor(monkeypatch: pytest.MonkeyPatch):
    buffer = SimpleNamespace(
        text="",
        complete_state=SimpleNamespace(
            current_completion=None, completions=["first"], complete_index=0
        ),
        start_completion=Mock(),
    )
    app = SimpleNamespace(
        current_buffer=buffer,
        layout=Layout(Window(FormattedTextControl())),
        renderer=SimpleNamespace(last_rendered_screen=object()),
        invalidate=Mock(),
        exit=Mock(),
    )
    clock = Mock(return_value=0)
    monkeypatch.setattr(time, "monotonic", clock)
    monkeypatch.setattr(prompt_toolkit.application, "get_app", lambda: app)
    monkeypatch.setattr(menus, "get_app", lambda: app)
    monkeypatch.setattr(random, "uniform", Mock(return_value=3))
    monkeypatch.setattr(random, "choice", itemgetter(0))
    return buffer, clock, app


@pytest.fixture
def canvas(pipe: PipeInput, screen: Screen, monkeypatch: pytest.MonkeyPatch):
    frames: Frames = []
    response: tuple[str, str] | None = None
    native = prompt_toolkit.prompt

    def draw(*args: Any, **kwargs: Any) -> str:
        app: Application[str] | None = None

        def sample(app: Application[str]):
            nonlocal response
            view = app.renderer.last_rendered_screen
            if view:
                frames.append([
                    "".join(
                        view.data_buffer[y][x].char
                        for x in range(get_app_session().output.get_size().columns)
                    )
                    for y in range(view.height)
                ])
                if response and any(response[0] in row for row in frames[-1]):
                    _, text = response
                    response = None
                    pipe.send_text(text)

        def ready():
            nonlocal app
            app = get_app()
            assert app.loop is not None
            kwargs["pre_run"]()
            app.after_render += sample
            current = app
            app.loop.set_exception_handler(
                lambda loop, context: current.exit(exception=context["exception"])
            )

        try:
            return native(*args, **{**kwargs, "pre_run": ready})
        finally:
            if app:
                app.after_render -= sample

    monkeypatch.setattr(prompt_toolkit, "prompt", draw)

    def setup(
        width: int = 80,
        rows: int = 24,
        no_color: bool = False,
        reply: tuple[str, str] | None = None,
    ):
        nonlocal response
        response = reply
        screen(width=width, live=True, no_color=no_color)
        monkeypatch.setattr(
            get_app_session().output, "get_size", lambda: Size(rows=rows, columns=width)
        )
        monkeypatch.setattr(
            get_app_session().output, "get_rows_below_cursor_position", lambda: rows
        )
        return frames

    return setup


@pytest.fixture
def keys(pipe: PipeInput):
    timers: list[Timer] = []

    def send(*texts: str, interval: float = 0.1) -> None:
        for index, text in enumerate(texts):
            timer = Timer(0.05 + index * interval, pipe.send_text, args=(text,))
            timers.append(timer)
            timer.start()

    yield send
    for timer in timers:
        timer.join()


@pytest.fixture
def tab(pipe: PipeInput, monkeypatch: pytest.MonkeyPatch):
    pending: list[str] = []
    prompt = prompt_toolkit.prompt

    def complete(*args: Any, **kwargs: Any) -> str:
        if not pending:
            return prompt(*args, **kwargs)
        prefix = pending.pop(0)
        before = kwargs.get("pre_run")
        handles: list[Any] = []

        def select(buffer: Buffer):
            if (
                buffer.text == prefix
                and buffer.complete_state
                and buffer.complete_state.completions
            ):
                buffer.on_completions_changed -= select
                pipe.send_text("\t\n")

        def ready():
            app = get_app()
            assert app.loop is not None
            app.current_buffer.on_completions_changed += select
            handles.append(app.current_buffer)
            handles.append(
                app.loop.call_later(
                    5,
                    lambda: app.exit(exception=TimeoutError("No completions appeared")),
                )
            )
            if before:
                before()
            pipe.send_text(prefix or "\x00")

        try:
            return prompt(*args, **{**kwargs, "pre_run": ready})
        finally:
            if handles:
                handles[0].on_completions_changed -= select
                handles[1].cancel()

    monkeypatch.setattr(prompt_toolkit, "prompt", complete)

    def send(prefix: str):
        pending.append(prefix)

    return send


@pytest.fixture
def screen(monkeypatch: pytest.MonkeyPatch):
    def make(*, width: int = 80, live: bool = False, no_color: bool = False):
        monkeypatch.setenv("TERM", "xterm-256color")
        output = StringIO()
        console = Console(
            file=output,
            width=width,
            force_terminal=live,
            no_color=no_color,
            theme=terminal.THEME,
            highlight=False,
            color_system="truecolor",
        )
        monkeypatch.setattr(terminal, "CONSOLE", console)
        return console, output

    return make


@pytest.fixture
def tty():
    return SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
