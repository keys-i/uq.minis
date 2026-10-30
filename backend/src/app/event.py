"""Browser event documents with preview as the explicit default

Event input is reviewed through the same validation and document pipeline
as the CLI. Preview remains the default and a university session alone
does not authorise a Forms submission
"""

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from uq_minis.app.core import Workspace, page, upload, value, workspace
from uq_minis.core.common import MiniError
from uq_minis.core.search import matches as contains
from uq_minis.core.search import terms
from uq_minis.minis.event import generate, rooms, save

router = APIRouter()
DETAILS = {
    "club": ("Your club", {"name": ("Club or organisation", "text")}),
    "event": (
        "Your event",
        {
            "title": ("Event name", "text"),
            "date": ("Event date", "date"),
            "summary": ("What will happen?", "textarea"),
        },
    ),
    "coordinator": (
        "Your contact",
        {
            "name": ("Coordinator name", "text"),
            "role": ("Coordinator role", "text"),
            "email": ("Contact email", "email"),
            "phone": ("Contact phone", "tel"),
        },
    ),
    "schedule": (
        "On the day",
        {
            "setup_start": ("Setup begins", "time"),
            "setup_end": ("Setup ends", "time"),
            "event_start": ("Event begins", "time"),
            "event_end": ("Event ends", "time"),
            "pack_up_start": ("Pack-up begins", "time"),
            "pack_up_end": ("Pack-up ends", "time"),
        },
    ),
}
OPERATIONS = {
    "indoor": "Indoors",
    "seated": "Mainly seated",
    "vehicles": "Vehicles involved",
    "temporary_structures": "Temporary structures",
    "electrical_equipment": "Electrical equipment",
    "cash_handling": "Handling cash",
    "alcohol": "Alcohol",
    "physical_competitions": "Physical competitions",
    "off_site_impact": "Activities beyond the venue",
}


def _show(request: Request, **results: object) -> dict[str, object]:
    return page(
        request,
        "event",
        fields=[
            {
                "name": "input",
                "label": "Start with",
                "type": "select",
                "options": [("new", "Tell us about your event"), ("saved", "Use a saved event")],
            },
            *[
                {
                    "name": f"{section}.{key}",
                    "label": label,
                    "type": kind,
                    "required": True,
                    "group": group,
                    "when": {"input": ["new"]},
                }
                for section, (group, fields) in DETAILS.items()
                for key, (label, kind) in fields.items()
            ],
            {
                "name": "attendance",
                "label": "Expected guests",
                "type": "range",
                "min": 1,
                "max": 10000,
                "value": 20,
                "group": "Your event",
                "when": {"input": ["new"]},
            },
            *[
                {
                    "name": f"operations.{key}",
                    "label": label,
                    "type": "checkbox",
                    "checked": key in {"indoor", "seated"},
                    "group": "Activities & catering",
                    "when": {"input": ["new"]},
                }
                for key, label in OPERATIONS.items()
            ],
            {
                "name": "food",
                "label": "Food and drink · blank if none",
                "group": "Activities & catering",
                "when": {"input": ["new"]},
            },
            {
                "name": "equipment",
                "label": "Equipment you'll use",
                "group": "Activities & catering",
                "when": {"input": ["new"]},
            },
            {
                "name": "affiliated",
                "label": "Affiliated with UQ",
                "type": "select",
                "options": [("Yes", "Yes"), ("No", "No")],
                "group": "Booking details",
                "when": {"input": ["new"]},
            },
            {
                "name": "date_flexibility",
                "label": "Other dates that could work",
                "group": "Booking details",
                "when": {"input": ["new"]},
            },
            *[
                {
                    "name": key,
                    "label": label,
                    "type": "number",
                    "min": 0,
                    "value": 0,
                    "group": "Booking details",
                    "when": {"input": ["new"]},
                }
                for key, label in (
                    ("under_18", "Guests under 18"),
                    ("non_uq", "Guests from outside UQ"),
                )
            ],
            {
                "name": "source",
                "label": "Existing event TOML path",
                "help": "Use the original path when the source refers to nearby logos or other assets",
                "when": {"input": ["saved"]},
            },
            {
                "name": "file",
                "label": "Or choose an event TOML file",
                "type": "file",
                "when": {"input": ["saved"]},
            },
            {
                "name": "venue",
                "label": "Venue",
                "type": "room",
                "group": "Venue & document settings",
            },
            {
                "name": "capacity",
                "label": "Reviewed Forms venue-capacity answer · needed for a new venue",
                "group": "Venue & document settings",
            },
            {
                "name": "rooms",
                "label": "Custom room catalogue path · optional",
                "group": "Venue & document settings",
            },
            {
                "name": "logo",
                "label": "Custom logo path · optional",
                "group": "Venue & document settings",
            },
            {
                "name": "form_profile",
                "label": "Custom booking form profile path · optional",
                "group": "Venue & document settings",
            },
            {
                "name": "jobs",
                "label": "Document workers · 0 chooses automatically",
                "type": "range",
                "value": 0,
                "min": 0,
                "max": 8,
                "group": "Venue & document settings",
            },
            {
                "name": "mode",
                "label": "Prepare",
                "type": "select",
                "options": [
                    ("both", "Form preview and risk documents"),
                    ("form", "Form preview"),
                    ("risk", "Risk documents"),
                ],
            },
            {
                "name": "layout",
                "label": "Risk layout",
                "type": "select",
                "options": [
                    ("both", "Form and event pack"),
                    ("form", "Form"),
                    ("pack", "Event pack"),
                ],
            },
            {
                "name": "submit",
                "label": "Submit the reviewed booking to UQ",
                "type": "checkbox",
                "help": "Only select this after checking the completed event source and all booking answers",
            },
            {
                "name": "confirm",
                "label": "I authorise this specific booking submission and have checked for an earlier submission",
                "type": "checkbox",
            },
        ],
        submit="Prepare this event",
        note="New events create an editable draft. Additional booking questions and terms stay unanswered for review. A listed room is not a confirmed reservation. Keep contact details and downloads private",
        **results,
    )


@router.get("/api/minis/event")
def home(request: Request) -> dict[str, object]:
    """Offer the same event-generation workflow as the terminal"""
    return _show(request)


@router.get("/api/rooms")
def venues(q: str = "", seats: int = 0, catalogue: str = "") -> dict[str, object]:
    """Find a bounded venue shortlist with capacity, photos and tours"""
    if not 0 <= seats <= 10000 or len(q) > 200 or len(catalogue) > 1000:
        raise MiniError("Choose a valid room search and capacity")
    rows = rooms.read(Path(catalogue).expanduser() if catalogue else None)
    capacity = re.search(r"\b(\d+)\s*(?:seats?|people|persons?|guests?)\b", q, re.IGNORECASE)
    if capacity:
        seats = max(seats, int(capacity[1]))
        q = q[: capacity.start()] + q[capacity.end() :]
    topics = terms(q, "rooms")
    matches = [
        room
        for room in rows
        if room.seats >= seats
        and contains(f"{room.campus} {room.building} {room.room} {room.kind}", topics)
    ]
    return {
        "rows": [asdict(room) for room in matches[:20]],
        "total": len(matches),
        "maximum": max(room.seats for room in rows),
    }


def _process(request: Request, form: FormData, context: Workspace) -> dict[str, object]:
    work = context.directory("event")
    source = None
    if value(form, "input", "saved") != "new":
        source = upload(form, "file", work / "event.toml")
        if source is None and not value(form, "source"):
            raise MiniError("Choose an event source file or enter its path")
        source = source or Path(value(form, "source")).expanduser()
    submit = value(form, "submit") == "on"
    if submit and value(form, "confirm") != "on":
        raise MiniError("Review and explicitly authorise the booking before submitting")
    mode, layout = value(form, "mode", "both"), value(form, "layout", "both")
    if mode not in {"form", "risk", "both"} or layout not in {"form", "pack", "both"}:
        raise MiniError("Choose a listed document mode and risk layout")
    from typing import cast

    from uq_minis.core.common import OutputMode, RiskLayout

    selected = None
    if value(form, "venue"):
        catalogue = rooms.read(
            Path(value(form, "rooms")).expanduser() if value(form, "rooms") else None
        )
        selected = next(
            (room for room in catalogue if f"{room.campus}|{room.room}" == value(form, "venue")),
            None,
        )
        if selected is None:
            raise MiniError("Choose a venue from the selected room catalogue")
    jobs = int(value(form, "jobs", "0"))
    if not 0 <= jobs <= 8:
        raise MiniError("Choose between 0 and 8 document workers")
    downloads: list[dict[str, str]] = []
    if source is None:
        if submit:
            raise MiniError("Prepare and review the new event's booking draft before submitting it")
        if selected is None:
            raise MiniError("Choose a room for your new event")
        raw: dict[str, Any] = {
            section: {key: value(form, f"{section}.{key}") for key in fields}
            for section, (_, fields) in DETAILS.items()
        }
        attendance = int(value(form, "attendance", "20"))
        if not 1 <= attendance <= 10000 or attendance > selected.seats:
            raise MiniError("Choose a room with enough seats for your expected guests")
        if any(not 0 <= int(value(form, key, "0")) <= attendance for key in ("under_18", "non_uq")):
            raise MiniError("Guest counts must be between zero and your expected attendance")
        raw["event"]["estimated_attendance"] = attendance
        raw["operations"] = {
            **{key: value(form, f"operations.{key}") == "on" for key in OPERATIONS},
            "equipment": value(form, "equipment"),
        }
        raw["catering"] = {
            "provided": bool(value(form, "food")),
            "description": value(form, "food"),
        }
        raw["output"] = {"mode": mode, "risk_layout": layout}
        raw["form"] = {
            "action": "preview",
            "values": {
                **{
                    key: value(form, key)
                    for key in ("affiliated", "date_flexibility", "under_18", "non_uq")
                },
                "food": value(form, "food"),
                "terms": "",
                "option_28": "",
                "option_30": "",
                "option_31": "",
                "option_32": "",
            },
        }
        rooms.apply(raw, selected, capacity=value(form, "capacity"))
        source = work / "event.toml"
        save(source, raw)
        source.chmod(0o600)
        downloads.append(context.publish(source))

    result = generate(
        source,
        mode=cast(OutputMode, mode),
        risk_layout=cast(RiskLayout, layout),
        destination=work,
        form_action="submit" if submit else "preview",
        jobs=jobs,
        logo=Path(value(form, "logo")).expanduser() if value(form, "logo") else None,
        form_profile=Path(value(form, "form_profile")).expanduser()
        if value(form, "form_profile")
        else None,
        selected_room=selected,
        capacity=value(form, "capacity") or None,
    )
    return _show(
        request,
        result="Event submitted"
        if result.submissions
        else "Event documents ready; no booking was submitted",
        downloads=[*downloads, *[context.publish(path) for _, path in result.outputs]],
    )


@router.post("/api/minis/event")
async def submit(request: Request) -> dict[str, object]:
    """Keep unattended browser actions out of the terminal wizard"""
    async with request.form(max_files=1) as form:
        return await run_in_threadpool(_process, request, form, workspace(request))
