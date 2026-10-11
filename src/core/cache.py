"""Bounded file caches with atomic publication and safe eviction"""

from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from uq_minis.core.common import MiniError, atomic_json

LIMIT = 2 * 1024**3
ENTRIES = 32
NAME = re.compile(r"[a-f0-9]{16}-[a-f0-9]{16}")


def entries(root: Path, key: str = "*"):
    """Read owned entries while ignoring corrupt metadata and unsafe paths"""
    if root.is_symlink():
        raise MiniError("The cache must not be a symlink")
    for entry in root.glob(f"{key}-*"):
        if not NAME.fullmatch(entry.name) or entry.is_symlink():
            continue
        index = entry / "info.json"
        try:
            if index.is_symlink() or index.stat().st_size > 4096:
                continue
            data = json.loads(index.read_text(encoding="utf-8"))
            filename = data["file"]
            if not isinstance(filename, str) or not re.fullmatch(r"[\w-]+\.[\w]+", filename):
                continue
            path = entry / filename
            if (
                filename == "info.json"
                or type(data["bytes"]) is not int
                or data["bytes"] <= 0
                or path.is_symlink()
                or not path.is_file()
                or path.stat().st_size != data["bytes"]
            ):
                continue
            yield data, path
        except OSError, ValueError, KeyError, TypeError:
            continue


def copy(source: Path, target: Path) -> None:
    """Reuse cached bytes through a hard link when the filesystem permits it"""
    if target.exists() or target.is_symlink():
        raise MiniError("Cache destination already exists")
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def reuse(source: Path, target: Path) -> None:
    """Copy a validated cache hit and record its last use for eviction"""
    copy(source, target)
    (source.parent / "info.json").touch()


def save(root: Path, key: str, source: Path, metadata: dict) -> None:
    """Publish the index last and enforce the shared byte and entry budgets"""
    size = source.stat().st_size
    if size <= 0 or size > LIMIT:
        return
    filename = metadata["file"]
    if (
        not NAME.fullmatch(key)
        or not re.fullmatch(r"[\w-]+\.[\w]+", filename)
        or filename == "info.json"
    ):
        raise MiniError("Invalid cache entry name")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise MiniError("The cache must not be a symlink")
    destination = root / key
    with TemporaryDirectory(prefix=".cache-", dir=root) as scratch:
        work = Path(scratch)
        target = work / filename
        copy(source, target)
        atomic_json(work / "info.json", {**metadata, "bytes": size})
        destination.mkdir(exist_ok=True)
        if destination.is_symlink():
            raise MiniError("A cache entry must not be a symlink")
        target.replace(destination / filename)
        (work / "info.json").replace(destination / "info.json")
    owned = []
    for _, path in entries(root):
        files = list(path.parent.iterdir())
        if any(file.is_symlink() or file.name not in {"info.json", path.name} for file in files):
            continue
        owned.append(
            (
                (path.parent / "info.json").stat().st_mtime,
                sum(file.stat().st_size for file in files),
                path.parent,
            )
        )
    total, count = sum(size for _, size, _ in owned), len(owned)
    for _, size, entry in sorted(owned):
        if total <= LIMIT and count <= ENTRIES:
            break
        shutil.rmtree(entry)
        total -= size
        count -= 1


@contextmanager
def writing(target: Path):
    """Publish a validated cached asset only after its writer completes"""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise MiniError("A cached asset must not be a symlink")
    with TemporaryDirectory(prefix=".cache-", dir=target.parent) as scratch:
        temporary = Path(scratch) / target.name
        yield temporary
        temporary.replace(target)
