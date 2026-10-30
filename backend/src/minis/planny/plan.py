"""Validated private planner state with atomic saves and stale-tab protection

A complete document is validated before reading or publishing private state
Atomic saves compare revisions under the shared lock, so a stale browser
edit cannot silently replace a newer plan
"""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from uq_minis.core.cache import locked
from uq_minis.core.common import MiniError, atomic_json


def text(value: Any, limit: int = 12000) -> str:
    """Accept bounded plain text without interpreting markup"""
    if not isinstance(value, str) or len(value) > limit:
        raise MiniError(f"Expected text of at most {limit} characters")
    return value.strip()


def number(value: Any, low: float = 0, high: float = 100) -> float:
    """Require a finite number inside an explicit range"""
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise MiniError(f"Expected a number between {low:g} and {high:g}")
    return float(value)


def link(value: Any) -> str:
    """Permit only ordinary web links for display, without fetching their targets"""
    clean = text(value, 4000)
    if not clean:
        return ""
    try:
        parsed = urlsplit(clean)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 80, 443)
            and not any(char.isspace() for char in clean)
        ):
            return clean
    except ValueError:
        pass
    raise MiniError("Links must use HTTP or HTTPS without credentials")


def moment(value: Any) -> str:
    """Normalise an optional exact timestamp to UTC and reject ambiguous local dates"""
    clean = text(value, 100)
    if not clean:
        return ""
    try:
        parsed = datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC).isoformat()
    except ValueError as exc:
        raise MiniError("Dates need an exact time and time zone") from exc


def empty() -> dict[str, Any]:
    """Start without fabricated enrolments, assessment rules or marks"""
    return {
        "revision": 0,
        "updated": datetime.now(UTC).isoformat(),
        "settings": {"buffer": 2, "target": 75},
        "courses": [],
        "assessments": [],
        "announcements": [],
    }


def validate(value: Any) -> dict[str, Any]:
    """Validate a complete editable plan before any state is published

    Args:
        value: Untrusted plan object from a file, browser or import

    Returns:
        A fresh document with bounded values, normalised dates and known fields

    Raises:
        MiniError: The shape, links, identifiers, numbers or limits are invalid
    """
    if not isinstance(value, dict):
        raise MiniError("Planner data must be an object")
    source = cast(dict[str, Any], value)
    settings = source.get("settings", {})
    if not isinstance(settings, dict):
        raise MiniError("Planner settings must be an object")
    settings = cast(dict[str, Any], settings)
    result = empty()
    clean_settings: dict[str, Any] = {
        "buffer": number(settings.get("buffer", 2), high=30),
        "target": number(settings.get("target", 75)),
    }
    following = settings.get("following", [])
    if not isinstance(following, list) or len(cast(list[Any], following)) > 500:
        raise MiniError("Follow at most 500 club links")
    clean_settings["following"] = [link(item) for item in cast(list[Any], following)]
    completed = settings.get("completed", [])
    if not isinstance(completed, list) or len(cast(list[Any], completed)) > 300:
        raise MiniError("Enter at most 300 completed courses")
    codes = [text(code, 20).upper() for code in cast(list[Any], completed)]
    if any(not re.fullmatch(r"[A-Z]{4}\d{4}[A-Z]?", code) for code in codes):
        raise MiniError("Completed courses need valid UQ course codes")
    clean_settings["completed"] = list(dict.fromkeys(codes))
    clean_settings["skills"] = text(settings.get("skills", ""), 6000)
    result["settings"] = clean_settings
    revision = source.get("revision", 0)
    if type(revision) is not int or revision < 0:
        raise MiniError("Planner revision must be a nonnegative integer")
    result["revision"] = revision
    identities: set[str] = set()
    courses: set[str] = set()
    for kind, maximum in (
        ("courses", 100),
        ("assessments", 5000),
        ("announcements", 5000),
    ):
        records = source.get(kind, [])
        if not isinstance(records, list) or len(cast(list[Any], records)) > maximum:
            raise MiniError(f"Planner {kind} must contain at most {maximum} records")
        output: list[dict[str, Any]] = []
        for raw in cast(list[Any], records):
            if not isinstance(raw, dict):
                raise MiniError(f"Every {kind} entry must be an object")
            row = cast(dict[str, Any], raw)
            key = text(row.get("id", ""), 120)
            if not re.fullmatch(r"[A-Za-z0-9_:-]+", key) or key in identities:
                raise MiniError("Planner records need unique stable IDs")
            identities.add(key)
            item: dict[str, Any] = {"id": key}
            if kind == "courses":
                code = text(row.get("code", ""), 20).upper()
                if not re.fullmatch(r"[A-Z]{4}\d{4}[A-Z]?", code):
                    raise MiniError("Choose a valid course code")
                item.update(
                    code=code,
                    name=text(row.get("name", ""), 300),
                    profile=link(row.get("profile", "")),
                    prerequisites=text(row.get("prerequisites", "")),
                    notes=text(row.get("notes", "")),
                    verified=row.get("verified", False) is True,
                    pass_mark=number(row.get("pass_mark", 50)),
                    hurdle_cap=number(row.get("hurdle_cap", 49)),
                    drop_group=text(row.get("drop_group", ""), 100),
                    drop_count=number(row.get("drop_count", 0), high=100),
                )
                if not item["drop_count"].is_integer():
                    raise MiniError("Drop count must be a whole number")
                courses.add(key)
            elif kind == "assessments":
                course = text(row.get("course", ""), 120)
                if course not in courses:
                    raise MiniError("Assessment course is not enrolled")
                factor = number(row.get("factor", 1), high=10)
                team = row.get("team") is True or ("team" not in row and factor != 1)
                item.update(
                    course=course,
                    title=text(row.get("title", ""), 300),
                    due=moment(row.get("due", "")),
                    start=moment(row.get("start", "")),
                    weight=number(row.get("weight", 0)),
                    maximum=number(row.get("maximum", 100), 0.000001, 1000000),
                    score=None if row.get("score") is None else number(row["score"], high=1000000),
                    team=team,
                    factor=factor if team else 1.0,
                    penalty=number(row.get("penalty", 0)),
                    hurdle=None if row.get("hurdle") is None else number(row["hurdle"]),
                    group=text(row.get("group", ""), 100),
                    notes=text(row.get("notes", "")),
                    url=link(row.get("url", "")),
                    source=text(row.get("source", ""), 20),
                    due_text=text(row.get("due_text", ""), 500),
                    done=row.get("done", False) is True,
                    buffer=None if row.get("buffer") is None else number(row["buffer"], high=30),
                )
                if item["source"] not in {"", "profile"}:
                    raise MiniError("Assessment source must be profile or blank")
                if item["start"] and item["due"] and item["start"] > item["due"]:
                    raise MiniError("Assessment start must be before its official deadline")
            else:
                item.update(
                    title=text(row.get("title", ""), 300),
                    source=text(row.get("source", "manual"), 60),
                    club=text(row.get("club", ""), 300),
                    notes=text(row.get("notes", "")),
                    club_url=link(row.get("club_url", "")),
                    banner=link(row.get("banner", "")),
                    logo=link(row.get("logo", "")),
                    saved=row.get("saved", True) is True,
                    start=moment(row.get("start", "")),
                    end=moment(row.get("end", "")),
                    url=link(row.get("url", "")),
                    status=text(row.get("status", "scheduled"), 30),
                )
                if item["start"] and item["end"] and item["end"] < item["start"]:
                    raise MiniError("Announcement end must be after its start")
            if not item.get("name", item.get("title", "")):
                raise MiniError("Courses, assessments and announcements need a name")
            output.append(item)
        result[kind] = output
    return result


def load(path: Path) -> dict[str, Any]:
    """Read a saved plan without changing unreadable or invalid data

    Args:
        path: Private plan file, limited to 8 MiB

    Returns:
        Validated saved state, or an empty plan when the file does not exist

    Raises:
        MiniError: The path, JSON or saved document is invalid
        OSError: The existing file cannot be read
    """
    if path.is_symlink() or path.parent.is_symlink():
        raise MiniError("Planner state must not be a symlink")
    if not path.exists():
        return empty()
    if path.stat().st_size > 8 * 1024**2:
        raise MiniError("Planner state exceeds 8 MiB")
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise MiniError("Saved planner data is invalid; restore a backup before saving") from exc
    result = validate(raw)
    result["updated"] = moment(raw.get("updated", "")) or result["updated"]
    return result


def save(path: Path, value: Any) -> dict[str, Any]:
    """Publish a private plan only when its revision still matches disk

    Args:
        path: Mini-owned JSON destination, protected by a sibling lock file
        value: Complete proposed document carrying the last accepted revision

    Returns:
        Validated document with its revision incremented after a successful save

    Raises:
        MiniError: Validation fails, the path is unsafe or the revision is stale
        OSError: Locking, reading or atomically writing state fails
    """
    result = validate(value)
    if path.parent.parent.is_symlink() or path.parent.is_symlink() or path.is_symlink():
        raise MiniError("Planner state must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path.with_suffix(".lock")):
        current = load(path)
        if result["revision"] != current["revision"]:
            raise MiniError("Another tab changed the plan; reload before saving")
        result["revision"] += 1
        atomic_json(path, result, private=True)
    return result
