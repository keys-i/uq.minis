"""Choose an event venue from UQ's editable room catalogue"""

from __future__ import annotations

import csv
import gzip
import webbrowser
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from urllib.parse import urlsplit

from uq_minis.assets import ROOT as ASSETS
from uq_minis.core.common import MiniError, table
from uq_minis.core.paths import STATE
from uq_minis.core.terminal import CONSOLE, ask, intro

TOURS = {"photos.google.com", "photos.app.goo.gl", "tour.panoee.net"}


@dataclass(frozen=True, slots=True)
class Room:
    """Room identity, seating capacity and optional official tour"""

    campus: str
    building: str
    room: str
    kind: str
    seats: int
    tour: str


def read(path: Path | None = None) -> list[Room]:
    """Load the compressed catalogue or a custom CSV, rejecting ambiguous entries"""
    custom = STATE / "event/rooms.csv"
    path = path or (custom if custom.is_file() else ASSETS / "event/rooms.csv.gz")
    rooms = []
    seen = set()
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
                identity = (campus, number)
                if (
                    not all((campus, building, number, kind))
                    or seats <= 0
                    or identity in seen
                    or any(ord(char) < 32 for value in row.values() if value for char in value)
                ):
                    raise ValueError(f"Invalid or duplicate room: {campus} {number}")
                if tour:
                    url = urlsplit(tour)
                    if (
                        url.scheme != "https"
                        or url.hostname not in TOURS
                        or url.username
                        or url.password
                        or url.port not in (None, 443)
                    ):
                        raise ValueError(f"Invalid virtual-tour link for {number}")
                rooms.append(Room(campus, building, number, kind, seats, tour))
                seen.add(identity)
        if not rooms:
            raise ValueError("Room CSV is empty")
    except (OSError, EOFError, ValueError, KeyError, TypeError, AttributeError, csv.Error) as exc:
        raise MiniError(f"Cannot read room catalogue {path}: {exc}") from exc
    return rooms


def choose(raw: dict, path: Path | None = None, *, form: bool = False) -> None:
    """Search buildings and rooms, with a tour before committing the venue"""
    rooms = read(path)
    event = table(raw, "event")
    intro("Find your room", "Room to gather · filter by seats, then take a look around")
    campuses = sorted({room.campus for room in rooms})
    campus = ask(
        "Campus",
        choices=campuses,
        default=event.get("campus") if event.get("campus") in campuses else campuses[0],
    )
    attendance = str(event.get("estimated_attendance", ""))
    while True:
        value = ask("Minimum seats", default=attendance if attendance.isdecimal() else "0")
        if value.isdecimal():
            minimum = int(value)
            available = [room for room in rooms if room.campus == campus and room.seats >= minimum]
            if available:
                break
        CONSOLE.print("Enter a non-negative seat count with matching rooms", style="error")
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
        room = choices[
            ask(
                "Room (type number, Tab to see capacity)",
                choices=sorted(choices),
                show_choices=False,
                search=True,
            )
        ]
        CONSOLE.print(
            f"{room.room} · {room.building} · {room.seats} seats · {room.kind}", markup=False
        )
        actions = ["select", "back", *(["tour"] if room.tour else [])]
        while True:
            action = ask("Venue", choices=actions, default="select")
            if action == "tour":
                CONSOLE.print(room.tour, markup=False)
                if not webbrowser.open(room.tour):
                    CONSOLE.print("Open the link above to view the tour")
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
    event.update(campus=room.campus, building=room.building, room=room.room, seats=room.seats)
    event.pop("location", None)
    raw["event"] = event
    if capacity is not None:
        raw.setdefault("form", {}).setdefault("values", {})["venue_capacity"] = capacity
