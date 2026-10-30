"""Separate durable mini state, disposable caches and user-visible exports

Paths stay relative to the current workspace so hosted accounts retain their
existing filesystem isolation and explicit CLI path overrides keep working
Legacy files are copied and verified once, never removed by migration
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, cast

from uq_minis.core.common import MiniError, atomic_json

STATE = Path(".config")
CACHE = Path("out/.cache")
OUT = Path("out")


def _digest(path: Path) -> bytes:
    """Hash bounded chunks without retaining saved file bytes in memory"""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").digest()


def _destination(relative: Path) -> Path:
    """Keep original uploads durable while relocating regenerable media"""
    parts = relative.parts
    if parts[:2] == ("app", "exports"):
        return OUT / "legacy" / Path(*parts[2:])
    if parts[:2] == ("timey", "parts"):
        return CACHE / relative
    if parts[:2] == ("timey", "media") and len(parts) > 3:
        entry = Path(".minis") / Path(*parts[:3])
        uploaded = any(item.name.startswith("upload.") for item in entry.iterdir())
        return (STATE / "timey/sources" if uploaded else CACHE / "timey/media") / Path(*parts[2:])
    return STATE / relative


def migrate() -> None:
    """Copy legacy workspace files without overwriting different saved data

    Raises:
        MiniError: A path is unsafe, saved files conflict or a source changes
        OSError: The workspace cannot preserve a complete verified copy

    An interrupted migration is resumable and the original .minis tree stays
    available for rollback until its owner explicitly removes it
    """
    legacy = Path(".minis")
    marker = STATE / ".migration.json"
    if not legacy.exists():
        return
    if legacy.is_symlink() or STATE.is_symlink() or marker.is_symlink():
        raise MiniError("Workspace migration cannot follow symlinks")
    if marker.is_file():
        return
    from uq_minis.core.cache import locked

    STATE.mkdir(mode=0o700, exist_ok=True)
    with locked(STATE / ".migration.lock"):
        if marker.is_file():
            return
        sources = sorted(legacy.rglob("*"))
        if any(item.is_symlink() or not (item.is_file() or item.is_dir()) for item in sources):
            raise MiniError("Keep a backup and remove unsafe links before migrating this workspace")
        mapping = {
            item.resolve(): _destination(item.relative_to(legacy))
            for item in sources
            if item.is_file()
        }
        for source, target in mapping.items():
            if any(parent.is_symlink() for parent in (target, *target.parents)):
                raise MiniError("A migration destination must not be a symlink")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            rewritten: bytes | None = None
            if source == (legacy / "app/registry.json").resolve():
                if source.stat().st_size > 1024**2:
                    raise MiniError("The legacy download registry needs repair before migration")
                data = json.loads(source.read_text())
                if not isinstance(data, dict):
                    raise MiniError("The legacy download registry needs repair before migration")
                data = cast(dict[str, Any], data)
                if any(not isinstance(v, str) for v in data.values()):
                    raise MiniError("The legacy download registry needs repair before migration")
                rewritten = (
                    json.dumps(
                        {
                            key: str(mapping.get(Path(value).resolve(), Path(value)).resolve())
                            for key, value in data.items()
                        },
                        indent=2,
                    )
                    + "\n"
                ).encode()
            if target.exists():
                expected = (
                    hashlib.sha256(rewritten).digest() if rewritten is not None else _digest(source)
                )
                with target.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").digest() != expected:
                        raise MiniError(
                            "Existing saved data differs from .minis; both copies are safe, resolve the migration conflict before continuing"
                        )
                continue
            temporary = target.with_name(f".{target.name}.{os.getpid()}.migration")
            before = source.stat()
            try:
                if rewritten is not None:
                    temporary.write_bytes(rewritten)
                else:
                    shutil.copy2(source, temporary)
                    with source.open("rb") as original, temporary.open("rb") as copied:
                        if (
                            hashlib.file_digest(original, "sha256").digest()
                            != hashlib.file_digest(copied, "sha256").digest()
                        ):
                            raise MiniError(
                                "A saved file changed during migration; close its editor and try again"
                            )
                if before.st_mtime_ns != source.stat().st_mtime_ns:
                    raise MiniError(
                        "A saved file changed during migration; close its editor and try again"
                    )
                temporary.chmod(0o600)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        atomic_json(
            marker, {"version": 1, "files": len(mapping), "legacy": str(legacy)}, private=True
        )
