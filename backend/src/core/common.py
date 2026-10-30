"""Small strict helpers shared by every mini

Shared validation turns expected input failures into MiniError
Atomic writers publish complete files in the destination directory and
validate overwrite rules before replacing an existing result
"""

from __future__ import annotations

import csv
import json
import os
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal, TypeVar, cast

OutputMode = Literal["form", "risk", "both"]
RiskLayout = Literal["form", "pack", "both"]
FormAction = Literal["preview", "submit"]
OUTPUT_MODES: tuple[OutputMode, ...] = ("form", "risk", "both")
RISK_LAYOUTS: tuple[RiskLayout, ...] = ("form", "pack", "both")
FORM_ACTIONS: tuple[FormAction, ...] = ("preview", "submit")
Choice = TypeVar("Choice", OutputMode, RiskLayout, FormAction)


class MiniError(ValueError):
    """Report invalid mini input or configuration"""


def read_toml(path: Path) -> dict[str, Any]:
    """Read a TOML document with actionable input errors

    Args:
        path: Input file, expanded and resolved before opening

    Returns:
        Parsed TOML tables and scalar values

    Raises:
        MiniError: The file is unreadable or contains invalid TOML
    """
    path = path.expanduser().resolve(strict=False)
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError as exc:
        raise MiniError(f"Cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise MiniError(f"Invalid TOML in {path}: {exc}") from exc


def table(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return a named TOML table"""
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise MiniError(f"[{key}] must be a TOML table")
    return cast(Mapping[str, Any], value)


def text(value: Any, *, field: str, required: bool = False) -> str:
    """Render a permitted TOML scalar as text"""
    if value is None:
        result = ""
    elif isinstance(value, bool):
        result = "Yes" if value else "No"
    elif isinstance(value, (str, int, float)) or hasattr(value, "isoformat"):
        result = str(value).strip()
    else:
        raise MiniError(f"{field} must be a scalar value")
    if required and not result:
        raise MiniError(f"Missing required {field}")
    return result


def choose(value: Any, *, field: str, allowed: Sequence[Choice]) -> Choice | None:
    """Validate an optional choice against allowed values"""
    selected = text(value, field=field).casefold()
    if not selected:
        return None
    if selected not in allowed:
        raise MiniError(f"{field} must be one of: {', '.join(allowed)}")
    return cast(Choice, selected)


def discover_events(input_path: Path) -> list[Path]:
    """Find event TOML files from a file or directory"""
    path = input_path.expanduser().resolve(strict=False)
    if path.is_file():
        if path.suffix.casefold() != ".toml":
            raise MiniError(f"Input must be a TOML file: {path}")
        return [path]
    if not path.is_dir():
        raise MiniError(f"Input does not exist: {path}")
    found = {
        item.resolve()
        for item in path.rglob("*.toml")
        if (item.name in {"event.toml", "events.toml"} or item.name.endswith(".event.toml"))
        and item.is_file()
        and not item.is_symlink()
    }
    if not found:
        raise MiniError(f"No event.toml, events.toml or *.event.toml files found under {path}")
    return sorted(found)


def output_directory(input_path: Path, override: Path | None) -> Path:
    """Choose an output directory for an event input"""
    if override is not None:
        return override.expanduser().resolve(strict=False)
    path = input_path.expanduser().resolve(strict=False)
    return Path("out/event") / (path.name if path.is_dir() else path.stem)


def unique(path: Path) -> Path:
    """Return a free output path, adding -1, -2 and so on when needed

    Keep the requested name when unused and preserve its final extension
    Reject a directory or symlink at the original path, and skip occupied
    numbered names, including dangling symlinks
    This chooses a name without reserving it; writers must recheck before saving
    """
    if path.is_symlink() or path.exists() and not path.is_file():
        raise MiniError(f"Output is not a regular file: {path}")
    candidate = path
    number = 0
    while candidate.exists() or candidate.is_symlink():
        number += 1
        candidate = path.with_name(f"{path.stem}-{number}{path.suffix}")
    return candidate


def ensure_outputs(paths: Sequence[Path], *, force: bool) -> None:
    """Validate a batch of output paths before any files are written

    Raise ``MiniError`` for duplicate paths, existing non-files or an existing
    file when ``force`` is false; no directories or files are created
    Callers remain responsible for rejecting symlinks and protecting source files
    """
    duplicates = [path for path, count in Counter(paths).items() if count > 1]
    if duplicates:
        raise MiniError("Output collision: " + ", ".join(path.name for path in duplicates))
    invalid = [path for path in paths if path.exists() and not path.is_file()]
    if invalid:
        raise MiniError("Output is not a regular file: " + ", ".join(map(str, invalid)))
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        names = ", ".join(path.name for path in existing)
        raise MiniError(f"Refusing to overwrite {names}; pass --force")


def atomic_json(path: Path, value: Mapping[str, Any], *, private: bool = False) -> None:
    """Publish complete JSON without exposing a partial destination

    Args:
        path: Destination whose parent directories may be created
        value: JSON-compatible mapping, written as indented UTF-8
        private: Set the published file's permissions to owner read/write

    Raises:
        TypeError: A value cannot be serialised as JSON
        OSError: Writing, syncing or replacing the destination fails

    Failed writes remove temporary bytes and preserve the previous destination
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if private:
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_docx(path: Path, document: Any) -> None:
    """Save a complete Word document before replacing its destination

    Args:
        path: Destination whose parent directories may be created
        document: A python-docx document supporting save(path)

    Raises:
        OSError: Writing, syncing or replacing the output fails

    Scratch files are removed after failure and the previous output stays intact
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".docx",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        document.save(temporary)
        with temporary.open("rb+") as handle:
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_csv(path: Path, fields: Iterable[str], rows: Iterable[dict[str, str]]) -> None:
    """Write a complete UTF-8 CSV before atomically replacing the destination

    Preserve the supplied column order, write a header and ignore extra row keys
    Flush the temporary file to disk before publishing it in the same directory
    A failed row or filesystem operation removes scratch output and leaves the
    earlier destination intact; successful calls intentionally replace it
    """
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=tuple(fields), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
