"""Small strict helpers shared by every mini"""

from __future__ import annotations

import json
import os
import tomllib
from collections import Counter
from collections.abc import Mapping, Sequence
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
    """Read a TOML file with mini-friendly errors"""
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
    return value


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
    return (path if path.is_dir() else path.parent) / "generated"


def ensure_outputs(paths: Sequence[Path], *, force: bool) -> None:
    """Reject output collisions and unsafe overwrites"""
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
    """Atomically write formatted JSON, optionally owner-only"""
    path.parent.mkdir(parents=True, exist_ok=True)
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
    try:
        if private:
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_docx(path: Path, document: Any) -> None:
    """Atomically save a DOCX document"""
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
