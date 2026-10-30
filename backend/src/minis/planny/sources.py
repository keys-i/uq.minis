"""Normalise public Rubric events and explicitly imported social announcements

Normalise public events and explicitly authorised imports into shared
announcement records. Complete snapshots can replace their own source
without deleting saved selections or posts from other sources
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import time
from typing import Any, cast
from urllib.parse import urljoin

from uq_minis.core import cache
from uq_minis.core.common import MiniError, atomic_json
from uq_minis.minis.clubby import events
from uq_minis.minis.clubby.directory import BASE, records
from uq_minis.minis.planny import plan


def rubric() -> list[dict[str, Any]]:
    """Read current public UQ club events without inventing missing end times"""
    rows: list[dict[str, Any]] = []
    for item in records("events"):
        stamp = item.get("sortindex")
        if type(stamp) is not int or not 0 <= stamp <= 253402300799:
            raise MiniError("Rubric event has no exact start time")
        url = urljoin(BASE, item["destination"])
        rows.append({
            "id": "rubric-" + sha256(url.encode()).hexdigest()[:24],
            "title": item.get("title", ""),
            "source": "Rubric",
            "club": item.get("societyname", ""),
            "start": datetime.fromtimestamp(stamp, UTC).isoformat(),
            "end": "",
            "url": url,
            "notes": " · ".join(str(item.get(key, "")) for key in ("subtitle", "info")),
            "status": "scheduled",
            "club_url": f"{BASE}?s={item.get('societyid', '')}",
            "saved": False,
            "banner": item.get("image") or "",
            "logo": item.get("societylogo") or "",
        })
    return rows


def feed(path: Path) -> dict[str, Any]:
    """Reuse an hourly public feed and keep the last complete snapshot on failure"""
    saved = cache.read(path, fresh=False)
    if saved and time() - path.stat().st_mtime < 3600:
        return {"rows": json.loads(saved)["rows"], "warning": ""}
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with cache.locked(path.with_suffix(".lock")):
            rows = plan.validate({**plan.empty(), "announcements": rubric()})["announcements"]
            if len(json.dumps(rows).encode()) > cache.SNAPSHOT:
                raise MiniError("The announcement feed exceeds the saved snapshot budget")
            atomic_json(path, {"rows": rows})
        return {"rows": rows, "warning": ""}
    except MiniError as exc:
        if saved:
            return {"rows": json.loads(saved)["rows"], "warning": str(exc)}
        raise


def imported(text: str, kind: str) -> list[dict[str, Any]]:
    """Import a Discord API export or normalised social-post JSON for review"""
    if kind == "discord":
        return scheduled(events.parse(text))
    if kind != "social":
        raise MiniError("Choose Discord scheduled events or social announcements")
    return social(text)


def scheduled(items: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Convert Clubby's validated events into stable calendar records"""
    return [
        {
            "id": f"discord-{item['guild_id']}-{item['event_id']}",
            "title": item["name"],
            "source": "Discord",
            "club": item["guild_id"],
            "start": item["start"],
            "end": item["end"],
            "url": item["url"],
            "notes": item["description"] + "\n" + item["location"],
            "status": item["status"],
        }
        for item in items
    ]


def social(source: str | list[dict[str, str]]) -> list[dict[str, Any]]:
    """Validate imported JSON or live records from authorised social sources"""
    raw: Any = source
    if isinstance(source, str):
        try:
            raw = json.loads(source)
        except ValueError as exc:
            raise MiniError("Announcement import needs a JSON array") from exc
    if not isinstance(raw, list) or len(cast(list[Any], raw)) > 5000:
        raise MiniError("Import at most 5000 announcements at a time")
    rows: list[dict[str, Any]] = []
    for value in cast(list[Any], raw):
        if not isinstance(value, dict):
            raise MiniError("Each announcement must be an object")
        item = cast(dict[str, Any], value)
        url = plan.link(item.get("url", ""))
        title = plan.text(item.get("title", ""), 300)
        if not url or not title:
            raise MiniError("Announcements need a title and original source URL")
        rows.append({
            "id": "post-" + sha256(url.encode()).hexdigest()[:24],
            "title": title,
            "source": plan.text(item.get("source", "Imported"), 60),
            "club": plan.text(item.get("club", ""), 300),
            "club_url": plan.link(item.get("club_url", "")),
            "banner": plan.link(item.get("banner", "")),
            "logo": plan.link(item.get("logo", "")),
            "start": plan.moment(item.get("start", "")),
            "end": plan.moment(item.get("end", "")),
            "url": url,
            "notes": plan.text(item.get("notes", "")),
            "status": "scheduled",
        })
    return rows


def merge(
    current: list[dict[str, Any]], incoming: list[dict[str, Any]], *, replace_source: str = ""
) -> list[dict[str, Any]]:
    """Replace a complete feed snapshot while retaining other imported sources"""
    rows = {
        item["id"]: item
        for item in current
        if not replace_source or item["source"] != replace_source
    }
    rows.update({item["id"]: item for item in incoming})
    previous = {item["id"]: item for item in current}
    for item in rows.values():
        if item["id"] in previous:
            item["saved"] = previous[item["id"]].get("saved", True)
            item["club_url"] = item.get("club_url") or previous[item["id"]].get("club_url", "")
    return list(rows.values())


def calendar(current: dict[str, Any], path: Path) -> dict[str, Any]:
    """Keep followed clubs current in subscriptions without changing the student's saved plan"""
    if not current["settings"].get("following"):
        return current
    try:
        rows = feed(path)["rows"]
    except MiniError:
        return current
    return {
        **current,
        "announcements": merge(current["announcements"], rows, replace_source="Rubric"),
    }
