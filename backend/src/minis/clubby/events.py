"""Aggregate authorised Discord scheduled-event feeds without a persistent bot

Saved exports and explicitly accessible Discord guilds produce the same
validated scheduled-event records. Missing dates remain missing and source
identities deduplicate events before a complete export is published
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from dotenv import dotenv_values

from uq_minis.core.common import MiniError, write_csv
from uq_minis.core.paths import STATE
from uq_minis.core.web import fetch

FIELDS = (
    "guild_id",
    "event_id",
    "name",
    "start",
    "end",
    "status",
    "location",
    "description",
    "url",
)
STATUS = {1: "scheduled", 2: "active", 3: "completed", 4: "cancelled"}
ID = re.compile(r"[1-9]\d{0,19}")


def _id(value: Any) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise MiniError("Discord guild and event IDs must be positive numeric strings")
    return value


def _time(value: Any, *, optional: bool = False) -> str:
    if optional and value is None:
        return ""
    try:
        if not isinstance(value, str):
            raise ValueError
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is None:
            raise ValueError
        return moment.astimezone(UTC).isoformat()
    except ValueError as exc:
        raise MiniError("Discord event timestamps must include a time zone") from exc


def parse(text: str, *, guild: str = "") -> list[dict[str, str]]:
    """Validate a Discord scheduled-event JSON array and retain its source links"""
    try:
        source: Any = json.loads(text)
    except ValueError as exc:
        raise MiniError("Invalid Discord scheduled-event JSON") from exc
    if not isinstance(source, list):
        raise MiniError("Discord export must be an array of scheduled events")
    rows: list[dict[str, str]] = []
    for value in cast(list[Any], source):
        if not isinstance(value, dict):
            raise MiniError("Every Discord event must be an object")
        event = cast(dict[str, Any], value)
        guild_id, event_id = _id(event.get("guild_id")), _id(event.get("id"))
        if guild and guild_id != guild:
            raise MiniError("Discord returned an event for a different guild")
        name, description = event.get("name"), event.get("description") or ""
        metadata: Any = event.get("entity_metadata") or {}
        if not isinstance(metadata, dict):
            raise MiniError("Discord event location metadata must be an object")
        metadata = cast(dict[str, Any], metadata)
        location = metadata.get("location") or event.get("channel_id") or ""
        status = event.get("status")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(description, str)
            or not isinstance(location, str)
            or type(status) is not int
            or status not in STATUS
        ):
            raise MiniError(
                "Discord event needs a name, valid status and text description/location"
            )
        start = _time(event.get("scheduled_start_time"))
        end = _time(event.get("scheduled_end_time"), optional=True)
        if end and datetime.fromisoformat(end) < datetime.fromisoformat(start):
            raise MiniError("Discord event ends before it starts")
        rows.append(
            dict(
                guild_id=guild_id,
                event_id=event_id,
                name=name.strip(),
                start=start,
                end=end,
                status=STATUS[status],
                location=location,
                description=description,
                url=f"https://discord.com/events/{guild_id}/{event_id}",
            )
        )
    return rows


def collect(*, guilds: list[str], source: Path | None = None) -> list[dict[str, str]]:
    """Read deduplicated events from saved JSON or accessible guilds

    Live reads use DISCORD_BOT_TOKEN and never send messages or register a gateway
    A failed guild preserves the previous combined export rather than dropping events
    """
    guilds = list(dict.fromkeys(_id(guild) for guild in guilds))
    if source is not None:
        if guilds:
            raise MiniError("Choose saved JSON or live --guild feeds, not both")
        rows = parse(source.expanduser().read_text(encoding="utf-8"))
    else:
        if not guilds:
            raise MiniError("Supply --guild ID or --json FILE for Discord scheduled events")
        token = (
            os.environ.get("DISCORD_BOT_TOKEN")
            or dotenv_values(STATE / "clubby" / ".env").get("DISCORD_BOT_TOKEN")
            or ""
        ).strip()
        if not token or any(char.isspace() for char in token):
            raise MiniError("Set DISCORD_BOT_TOKEN to a bot token with access to these guilds")
        rows: list[dict[str, str]] = []
        with httpx.Client(
            timeout=30, follow_redirects=False, headers={"Authorization": f"Bot {token}"}
        ) as client:
            for guild in guilds:
                text = fetch(
                    f"https://discord.com/api/v10/guilds/{guild}/scheduled-events",
                    client=client,
                    hosts=("discord.com",),
                )
                rows.extend(parse(text, guild=guild))
    unique = {(row["guild_id"], row["event_id"]): row for row in rows}
    return sorted(unique.values(), key=lambda row: (row["start"], row["guild_id"], row["event_id"]))


def export(output: Path, *, guilds: list[str], source: Path | None = None) -> int:
    """Publish a complete event collection without replacing its source"""
    if source is not None and source.expanduser().resolve() == output.expanduser().resolve():
        raise MiniError("Choose a different output file from the Discord JSON")
    ordered = collect(guilds=guilds, source=source)
    write_csv(output, FIELDS, ordered)
    return len(ordered)
