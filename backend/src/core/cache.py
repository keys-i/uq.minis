"""Bounded file caches with atomic publication and safe eviction

Cache meaning and validation belong to each mini; this module owns canonical
identities, exclusive publication, access tracking and shared eviction budgets
A failed writer leaves the previous published entry available
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from contextlib import contextmanager
from errno import EACCES, EAGAIN, EDEADLK
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Any

from uq_minis.core.common import MiniError, atomic_json

LIMIT = 2 * 1024**3
ENTRIES = 32
NAME = re.compile(r"[a-f0-9]{16}-[a-f0-9]{16}")
SNAPSHOT = 4 * 1024**2
AGE = 7 * 24 * 60 * 60
SEMANTIC_AGE = 5 * 60
SEMANTIC_ENTRIES = 128
SEMANTIC_LIMIT = 256 * 1024


def identity(namespace: str, semantic: Any) -> str:
    """Hash canonical meaning so changed inputs invalidate their previous cache entry"""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", namespace):
        raise MiniError("Invalid cache namespace")
    try:
        payload = json.dumps(
            semantic,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise MiniError("Cache identity needs JSON-compatible values") from exc
    return hashlib.sha256(namespace.encode() + b"\0" + payload).hexdigest()[:16]


class SemanticCache:
    """Keep small public lookup results in memory by their canonical meaning"""

    def __init__(self) -> None:
        """Start with no cached results or process counters"""
        self.values: dict[str, tuple[float, bytes]] = {}
        self.bytes = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.lock = Lock()

    def get(self, namespace: str, semantic: Any) -> Any | None:
        """Return an unshared JSON value while expiring stale or corrupt entries"""
        key = identity(namespace, semantic)
        with self.lock:
            found = self.values.pop(key, None)
            if found is None:
                self.misses += 1
                return None
            expires, payload = found
            if expires <= time.monotonic():
                self.bytes -= len(payload)
                self.misses += 1
                self.evictions += 1
                return None
            try:
                value = json.loads(payload)
            except TypeError, ValueError:
                self.bytes -= len(payload)
                self.misses += 1
                self.evictions += 1
                return None
            self.values[key] = found
            self.hits += 1
            return value

    def put(self, namespace: str, semantic: Any, value: Any) -> None:
        """Store one bounded JSON result and evict expired or least-recent entries"""
        payload = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        if len(payload) > SEMANTIC_LIMIT:
            return
        key = identity(namespace, semantic)
        now = time.monotonic()
        with self.lock:
            previous = self.values.pop(key, None)
            if previous is not None:
                self.bytes -= len(previous[1])
            for stale, (expires, cached) in list(self.values.items()):
                if expires <= now:
                    del self.values[stale]
                    self.bytes -= len(cached)
                    self.evictions += 1
            while self.values and (
                len(self.values) >= SEMANTIC_ENTRIES or self.bytes + len(payload) > SEMANTIC_LIMIT
            ):
                oldest = next(iter(self.values))
                _, cached = self.values.pop(oldest)
                self.bytes -= len(cached)
                self.evictions += 1
            self.values[key] = (now + SEMANTIC_AGE, payload)
            self.bytes += len(payload)

    def stats(self) -> dict[str, int]:
        """Snapshot low-cardinality counters and current resource use"""
        with self.lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "entries": len(self.values),
                "bytes": self.bytes,
            }


@contextmanager
def locked(path: Path):
    """Hold an exclusive, nonblocking lock for a state-file operation

    Args:
        path: Lock file in an existing parent directory

    Yields:
        Control while the platform file lock is held

    Raises:
        MiniError: The lock is a symlink or another operation owns it
        OSError: The lock cannot be opened or the platform lock fails

    Exiting releases the lock on Windows and Unix, including after exceptions
    """
    if path.is_symlink():
        raise MiniError("A state lock must not be a symlink")
    with path.open("a+b") as stream:
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in {EACCES, EAGAIN, EDEADLK}:
                raise
            raise MiniError("Another operation is using this state file") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def read(path: Path, *, fresh: bool = True) -> bytes | None:
    """Read bounded snapshot bytes without parsing mini-specific data

    Args:
        path: Snapshot file, with no symlink at the file or immediate parent
        fresh: Require a modification time within the last seven days

    Returns:
        At most 4 MiB, or None for missing, unreadable, oversized or stale files

    Raises:
        MiniError: The snapshot or its immediate parent is a symlink
    """
    if path.is_symlink() or path.parent.is_symlink():
        raise MiniError("A cached snapshot must not be a symlink")
    try:
        info = path.stat()
        if info.st_size > SNAPSHOT or fresh and time.time() - info.st_mtime > AGE:
            return None
        with path.open("rb") as stream:
            data = stream.read(SNAPSHOT + 1)
        return data if len(data) <= SNAPSHOT else None
    except OSError:
        return None


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
    """Reuse a validated cache hit in place or by copying and record its last use"""
    if source != target:
        copy(source, target)
    (source.parent / "info.json").touch()


def save(root: Path, key: str, source: Path, metadata: dict[str, Any]) -> None:
    """Publish cache metadata last and enforce shared storage budgets

    Args:
        root: Mini-owned cache directory
        key: Validated pair of sixteen-character hexadecimal identities
        source: Complete regular file to hard-link or copy into the cache
        metadata: Mini-specific index including a safe file basename

    Raises:
        MiniError: An entry name or destination is unsafe
        OSError: Copying, publishing or evicting a file fails

    Empty files and entries exceeding the byte budget are left uncached
    """
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
    owned: list[tuple[float, int, Path]] = []
    for _, path in entries(root):
        files = list(path.parent.iterdir())
        if any(file.is_symlink() or file.name not in {"info.json", path.name} for file in files):
            continue
        owned.append((
            (path.parent / "info.json").stat().st_mtime,
            sum(file.stat().st_size for file in files),
            path.parent,
        ))
    total, count = sum(size for _, size, _ in owned), len(owned)
    for _, size, entry in sorted(owned):
        if total <= LIMIT and count <= ENTRIES:
            break
        shutil.rmtree(entry)
        total -= size
        count -= 1


@contextmanager
def writing(target: Path):
    """Keep a previous cached asset until its replacement is complete

    Args:
        target: Destination whose parent directories may be created

    Yields:
        Scratch path in the destination filesystem for the caller to write

    Raises:
        MiniError: The destination is a symlink
        OSError: Writing or publishing the scratch file fails

    An exception from the caller removes scratch files without publishing them
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise MiniError("A cached asset must not be a symlink")
    with TemporaryDirectory(prefix=".cache-", dir=target.parent) as scratch:
        temporary = Path(scratch) / target.name
        yield temporary
        temporary.replace(target)
