"""Choose an event venue from UQ's editable room catalogue

Venue selection uses bounded bundled records with official preview links
Applying a choice updates the in-memory event; saving source or submitting
a booking remains a separate action
"""

from __future__ import annotations

import csv
import gzip
import webbrowser
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from uq_minis.assets import ROOT as ASSETS
from uq_minis.core.common import MiniError, table
from uq_minis.core.paths import STATE
from uq_minis.core.terminal import CONSOLE, ask, intro, number

TOURS = {"photos.google.com", "photos.app.goo.gl", "tour.panoee.net"}
PHOTOS = {"campuses.uq.edu.au"}


@dataclass(frozen=True, slots=True)
class Room:
    """Room identity, seating capacity and optional official previews"""

    campus: str
    building: str
    room: str
    kind: str
    seats: int
    tour: str
    photo: str = ""


def read(path: Path | None = None) -> list[Room]:
    """Load room identities, capacities and optional official preview links

    Use an explicit CSV, then .minis/event/rooms.csv, otherwise the bundled gzip
    Limit decoded input to 1 MiB and reject missing fields, non-positive seats,
    duplicate campus/room identities and unsafe photo or tour URLs
    Return rooms in source order; malformed or unreadable input raises MiniError
    """
    custom = STATE / "event/rooms.csv"
    path = path or (custom if custom.is_file() else ASSETS / "event/rooms.csv.gz")
    rooms: list[Room] = []
    seen: set[tuple[str, str]] = set()
    try:
        with gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb") as source:
            data = source.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Room CSV exceeds 1 MiB")
        with StringIO(data.decode("utf-8-sig"), newline="") as handle:
            for row in csv.DictReader(handle):
                campus, building, number, kind = (
                    row[key].strip() for key in ("campus", "building", "room", "kind")
                )
                seats = int(row["seats"])
                tour = (row.get("tour") or "").strip()
                photo = (row.get("photo") or "").strip()
                identity = (campus, number)
                if (
                    not all((campus, building, number, kind))
                    or seats <= 0
                    or identity in seen
                    or any(ord(char) < 32 for value in row.values() if value for char in value)
                ):
                    raise ValueError(f"Invalid or duplicate room: {campus} {number}")
                for link, hosts in ((tour, TOURS), (photo, PHOTOS)):
                    if not link:
                        continue
                    url = urlsplit(link)
                    if (
                        url.scheme != "https"
                        or url.hostname not in hosts
                        or url.username
                        or url.password
                        or url.port not in (None, 443)
                    ):
                        raise ValueError(f"Invalid room-preview link for {number}")
                rooms.append(Room(campus, building, number, kind, seats, tour, photo))
                seen.add(identity)
        if not rooms:
            raise ValueError("Room CSV is empty")
    except (
        OSError,
        EOFError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        csv.Error,
    ) as exc:
        raise MiniError(f"Cannot read room catalogue {path}: {exc}") from exc
    return rooms


def apply(raw: dict[str, Any], room: Room, *, capacity: str | None = None) -> None:
    """Apply a reviewed venue to an in-memory event without rewriting its source"""
    event = dict(table(raw, "event"))
    event.update(campus=room.campus, building=room.building, room=room.room, seats=room.seats)
    event.pop("location", None)
    raw["event"] = event
    if capacity is not None:
        raw.setdefault("form", {}).setdefault("values", {})["venue_capacity"] = capacity


def choose(raw: dict[str, Any], path: Path | None = None, *, form: bool = False) -> None:
    """Choose a venue by campus, minimum seats, building and room number

    Right opens the highlighted room's photo and Left opens its virtual tour
    Neither shortcut confirms the venue; a separate review accepts the choice
    Update ``raw['event']`` in memory after selection and, with ``form=True``,
    collect the Forms capacity answer without rewriting the source TOML
    A listed room is a candidate venue, not a confirmed booking
    """
    rooms = read(path)
    event = dict(table(raw, "event"))
    raw["event"] = event
    intro("Find your room", "Room to gather · filter by seats, then take a look around")
    campuses = sorted({room.campus for room in rooms})
    campus = ask(
        "Campus",
        choices=campuses,
        default=str(event["campus"]) if event.get("campus") in campuses else campuses[0],
    )
    attendance = str(event.get("estimated_attendance", ""))
    maximum = max(room.seats for room in rooms if room.campus == campus)
    minimum = number(
        "Minimum seats",
        default=min(int(attendance), maximum) if attendance.isdecimal() else 0,
        minimum=0,
        maximum=maximum,
        unit=" seats",
    )
    available = [room for room in rooms if room.campus == campus and room.seats >= minimum]
    buildings = {
        f"{room.room.split('-', 1)[0]} · {room.building}": room.building for room in available
    }
    while True:
        building = buildings[
            ask(
                "Building (type name or number, Tab to browse)",
                choices=sorted(buildings),
                ignore_case=True,
                show_choices=False,
                search=True,
            )
        ]
        choices = {
            f"{room.room} · {room.seats} seats · {room.kind}": room
            for room in available
            if room.building == building
        }

        def open_room(key: str, *, picture: bool = False) -> None:
            if key not in choices:
                raise MiniError("Highlight a room first with ↑ or ↓")
            chosen = choices[key]
            link = chosen.photo if picture else chosen.tour
            name = "photo" if picture else "virtual tour"
            if not link:
                raise MiniError(f"No {name} listed for {chosen.room}")
            if not webbrowser.open(link):
                raise MiniError(f"Open the {name} in your browser: {link}")

        room = choices[
            ask(
                "Room (type number, Tab to see capacity)",
                choices=sorted(choices),
                show_choices=False,
                search=True,
                actions={
                    "right": ("photo", lambda key: open_room(key, picture=True)),
                    "left": ("virtual tour", open_room),
                },
            )
        ]
        actions = {"select": "Use this room", "back": "Choose another room"}
        if room.photo:
            actions["photo"] = "Open the room photo"
        if room.tour:
            actions["tour"] = "Open the virtual tour"
        while True:
            action = ask(
                "Use this venue?",
                choices=actions,
                default="select",
                details={
                    "Room": room.room,
                    "Building": room.building,
                    "Capacity": f"{room.seats} seats · {room.kind}",
                },
            )
            if action in {"tour", "photo"}:
                link = room.photo if action == "photo" else room.tour
                if not webbrowser.open(link):
                    CONSOLE.print(f"Open in your browser: {link}", markup=False)
            else:
                break
        if action == "select":
            break
    capacity = None
    if form:
        values = table(table(raw, "form"), "values")
        capacity = ask(
            f"Forms venue-capacity answer for {room.seats} seats",
            default=str(values.get("venue_capacity", "")),
            required=True,
        )
    apply(raw, room, capacity=capacity)
