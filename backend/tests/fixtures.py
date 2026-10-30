"""Shared test inputs, isolated state and terminal setup"""

from __future__ import annotations

from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol

from prompt_toolkit.formatted_text import StyleAndTextTuples, to_formatted_text
from prompt_toolkit.layout import (
    ConditionalContainer,
    Container,
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from rich.console import Console

type Frames = list[list[str]]


class Canvas(Protocol):
    def __call__(
        self,
        width: int = 80,
        rows: int = 24,
        no_color: bool = False,
        reply: tuple[str, str] | None = None,
    ) -> Frames: ...


class Screen(Protocol):
    def __call__(
        self, *, width: int = 80, live: bool = False, no_color: bool = False
    ) -> tuple[Console, StringIO]: ...


class Keys(Protocol):
    def __call__(self, *texts: str, interval: float = 0.1) -> None: ...


class Clip(Protocol):
    def __call__(
        self,
        name: str,
        source: str,
        seconds: float = 1,
        *,
        audio: bool = False,
        options: Sequence[str] = (),
    ) -> Path: ...


def columns(app: SimpleNamespace) -> VSplit:
    root = app.layout.container
    assert isinstance(root, ConditionalContainer) and isinstance(root.content, HSplit)
    row = root.content.children[0]
    assert isinstance(row, VSplit)
    return row


def parts(container: Container) -> StyleAndTextTuples:
    assert isinstance(container, Window) and isinstance(container.content, FormattedTextControl)
    return to_formatted_text(container.content.text)
