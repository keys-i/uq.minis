"""Shared browser presentation and workspace paths for every mini

Workspace owns browser exports and their opaque download registrations
Upload and cancellation helpers share lifecycle rules while domain parsing,
media rendering and credential validation remain with their owning minis
"""

from __future__ import annotations

import asyncio
import json
import re
import tomllib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from threading import Event, Lock
from typing import Any, cast
from uuid import uuid4

from fastapi import Request
from starlette.datastructures import FormData, UploadFile

from uq_minis.core.common import MiniError, atomic_json
from uq_minis.core.paths import OUT, STATE

TOOLS = {
    name: (mini["title"], mini["about"])
    for name, mini in tomllib.loads(
        files("uq_minis.assets").joinpath("minis.toml").read_text()
    ).items()
}


@asynccontextmanager
async def cancellation(request: Request) -> AsyncGenerator[Event]:
    """Cancel abandoned browser work and release its resources"""
    cancelled = Event()

    async def disconnect() -> None:
        while not cancelled.is_set() and not await request.is_disconnected():
            await asyncio.sleep(0.25)
        cancelled.set()

    watcher = asyncio.create_task(disconnect())
    try:
        yield cancelled
    finally:
        cancelled.set()
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass


@dataclass(slots=True)
class Workspace:
    """Own browser state paths while keeping mini logic in its existing modules"""

    state: Path = STATE / "planny" / "plan.json"
    courses: Path = STATE / "scrappy" / "offerings.csv"
    clubs: Path = STATE / "clubby" / "clubs.csv"
    exports: Path = OUT
    downloads: dict[str, Path] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)
    port: int = 8765

    def __post_init__(self) -> None:
        """Recover bounded media registrations so shared drafts survive a restart"""
        registry = self.registry
        if any(path.is_symlink() for path in (registry, *registry.parents)):
            raise MiniError("Browser registrations must not be symlinks")
        if not registry.exists():
            return
        if registry.stat().st_size > 256 * 4096:
            raise MiniError("The browser registry is too large; keep a backup before repairing it")
        entries: object = json.loads(registry.read_text())
        if not isinstance(entries, dict):
            raise MiniError("The browser registry couldn't be read; keep it before repairing it")
        for key, value in cast(dict[object, object], entries).items():
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"[a-f0-9]{32}", key)
                or not isinstance(value, str)
            ):
                raise MiniError("The browser registry contains an invalid file registration")
            path = Path(value)
            if path.is_file() and not path.is_symlink():
                self.downloads[key] = path
        while len(self.downloads) > 256:
            del self.downloads[next(iter(self.downloads))]

    @property
    def registry(self) -> Path:
        """Keep opaque download references durable when generated exports are cleared"""
        return (
            STATE / "app/registry.json"
            if self.exports == OUT
            else self.exports.parent / "registry.json"
        )

    def directory(self, mini: str = "app") -> Path:
        """Reserve an isolated output directory without overwriting another run"""
        if any(parent.is_symlink() for parent in (self.exports, *self.exports.parents)):
            raise MiniError("Browser exports must not be symlinks")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", mini):
            raise MiniError("Choose a valid mini output directory")
        target = self.exports / mini / uuid4().hex
        target.mkdir(parents=True)
        return target

    def publish(self, path: Path) -> dict[str, str]:
        """Register a completed download without exposing arbitrary local paths"""
        if not path.is_file() or path.is_symlink():
            raise MiniError("The requested output is not a completed file")
        key = uuid4().hex
        with self.lock:
            self.downloads[key] = path
            while len(self.downloads) > 256:
                del self.downloads[next(iter(self.downloads))]
            atomic_json(
                self.registry,
                {key: str(path.resolve()) for key, path in self.downloads.items()},
                private=True,
            )
        return {"name": path.name, "url": "/download/" + key}

    def download(self, key: str) -> Path | None:
        """Read the registry while other minis publish results"""
        with self.lock:
            return self.downloads.get(key)


def workspace(request: Request) -> Workspace:
    """Read the active browser workspace without importing CLI modules"""
    return cast(Workspace, request.app.state.workspace)


def page(
    request: Request,
    name: str,
    *,
    fields: list[dict[str, Any]],
    **values: Any,
) -> dict[str, Any]:
    """Describe a browser form without embedding presentation or CLI behaviour"""
    title, about = TOOLS.get(name, (name.replace("-", " ").title(), "Open this mini"))
    return {"tool": name, "title": title, "about": about, "fields": fields, **values}


def upload(form: FormData, name: str, target: Path) -> Path | None:
    """Save a bounded uploaded input privately using an owned filename"""
    value = form.get(name)
    if not isinstance(value, UploadFile) or not value.filename:
        return None
    data = value.file.read(8 * 1024**2 + 1)
    if len(data) > 8 * 1024**2:
        raise MiniError("Uploaded inputs must be at most 8 MiB")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    target.chmod(0o600)
    return target


def value(form: FormData, name: str, default: str = "") -> str:
    """Read text form fields without treating an uploaded file as a path"""
    result = form.get(name, default)
    if not isinstance(result, str):
        raise MiniError(f"{name} must be text")
    return result.strip()
