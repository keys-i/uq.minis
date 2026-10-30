"""Event form and risk-document commands

The command resolves input files and review choices before invoking the
event pipeline. Batch document generation and Forms submission retain
their separate output, overwrite and authority checks
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.text import Text
lazy import httpx

from uq_minis.core.art import RESIDENTS
from uq_minis.core.common import MiniError, OutputMode, RiskLayout
from uq_minis.core.terminal import (
    CONSOLE,
    Back,
    application,
    ask,
    clock,
    confirm,
    day,
    intro,
    number,
    table,
)
lazy from uq_minis.minis.event import generate

if TYPE_CHECKING:
    from uq_minis.minis.event.pipeline import Plan

app = application(theme=RESIDENTS["event"])


def _setup(path: Path, mode: OutputMode | None, rooms: Path | None) -> None:
    """Collect real event details and save the source before using it"""
    from uq_minis.minis.event import save
    from uq_minis.minis.event.rooms import choose

    selected = mode or ask(
        "What are you preparing?",
        choices={"risk": "Risk assessment", "form": "Booking draft", "both": "Both documents"},
        default="both",
    )
    raw: dict[str, Any] = {"output": {"mode": selected, "risk_layout": "form"}}
    fields = {
        "club": {"name": "Club or organisation"},
        "event": {
            "title": "Event name",
            "date": "Event date (YYYY-MM-DD)",
            "summary": "What will happen at the event?",
        },
        "coordinator": {
            "name": "Coordinator name",
            "role": "Coordinator role",
            "email": "Contact email",
            "phone": "Contact phone",
        },
        "schedule": {
            "setup_start": "Setup begins (HH:MM)",
            "setup_end": "Setup ends (HH:MM)",
            "event_start": "Event begins (HH:MM)",
            "event_end": "Event ends (HH:MM)",
            "pack_up_start": "Pack-up begins (HH:MM)",
            "pack_up_end": "Pack-up ends (HH:MM)",
        },
    }
    for section, entries in fields.items():
        raw[section] = {}
        for key, label in entries.items():
            raw[section][key] = (
                day(label).isoformat()
                if key == "date"
                else clock(label).isoformat(timespec="minutes")
                if section == "schedule"
                else ask(label, required=True)
            )
    raw["event"]["estimated_attendance"] = int(
        number(
            "Expected guests",
            default=20,
            minimum=1,
            maximum=10000,
            unit=" people",
        )
    )
    raw["operations"] = {
        key: confirm(label, default=default)
        for key, label, default in (
            ("indoor", "Indoors?", True),
            ("seated", "Mainly seated?", True),
            ("vehicles", "Vehicles involved?", False),
            ("temporary_structures", "Temporary structures?", False),
            ("electrical_equipment", "Electrical equipment?", False),
            ("cash_handling", "Handling cash?", False),
            ("alcohol", "Alcohol?", False),
            ("physical_competitions", "Physical competitions?", False),
            ("off_site_impact", "Activities beyond the venue?", False),
        )
    }
    food = ask("Food and drink (leave blank if none)")
    raw["catering"] = {"provided": bool(food), "description": food}
    if selected in {"form", "both"}:
        raw["form"] = {
            "action": "preview",
            "values": {
                "affiliated": "Yes" if confirm("Affiliated with UQ?", default=True) else "No",
                "date_flexibility": ask("Other dates that would work (optional)"),
                "under_18": int(
                    number(
                        "Guests under 18",
                        default=0,
                        minimum=0,
                        maximum=raw["event"]["estimated_attendance"],
                    )
                ),
                "non_uq": int(
                    number(
                        "Guests from outside UQ",
                        default=0,
                        minimum=0,
                        maximum=raw["event"]["estimated_attendance"],
                    )
                ),
                "food": food,
                "venue_capacity": "",
                "terms": "",
                "option_28": "",
                "option_30": "",
                "option_31": "",
                "option_32": "",
            },
        }
        CONSOLE.print(
            "The booking draft leaves the form’s additional questions and terms unanswered "
            "for review before submission",
            markup=False,
        )
    choose(raw, rooms, form=selected in {"form", "both"})
    if not confirm(
        "Save this event source?",
        default=True,
        details={
            "Event": raw["event"]["title"],
            "Date": raw["event"]["date"],
            "Venue": f"{raw['event']['campus']} · {raw['event']['room']}",
            "Guests": str(raw["event"]["estimated_attendance"]),
            "Save to": str(path),
        },
    ):
        raise Back
    save(path, raw)
    CONSOLE.print(f"Saved editable event: {path}", markup=False)


def _review(plans: Sequence[Plan]) -> None:
    """Review every event before writing files or sending an application"""
    for plan in plans:
        event = plan.config
        documents = ["Booking application"] if plan.form_output else []
        documents.extend(
            "Risk assessment pack" if layout == "pack" else "Risk assessment form"
            for layout, _ in plan.risk_outputs
        )
        details = {
            "Event": event.title,
            "When": event.event_date or "Date not supplied",
            "Where": event.location or "Venue not supplied",
            "Guests": event.estimated_attendance or "Attendance not supplied",
            "Timings": event.schedule.compact_sentence().removeprefix("Schedule: ").rstrip(".")
            or "Schedule not supplied",
            "Documents": ", ".join(documents),
            "Save to": str((plan.form_output or plan.risk_outputs[0][1]).parent),
            "Submission": "Send to Microsoft Forms now"
            if plan.form_action == "submit"
            else "Draft only · no booking is confirmed",
        }
        if not confirm(
            "Submit this event?" if plan.form_action == "submit" else "Make these documents?",
            default=plan.form_action != "submit",
            details=details,
        ):
            raise Back


@app.command()
def run(
    input: Annotated[Path | None, typer.Argument(help="Event TOML file or directory.")] = None,
    form: Annotated[bool, typer.Option("--form", help="Generate Microsoft Forms JSON.")] = False,
    risk: Annotated[bool, typer.Option("--risk", help="Generate risk-assessment DOCX.")] = False,
    layout: Annotated[
        RiskLayout | None,
        typer.Option("--layout", help="Risk form, pack, or both."),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", "-o", help="Destination directory."),
    ] = None,
    logo: Annotated[Path | None, typer.Option(help="Logo image for the risk document.")] = None,
    force: Annotated[bool, typer.Option(help="Replace existing output files.")] = False,
    jobs: Annotated[
        int,
        typer.Option("--jobs", "-j", min=0, help="DOCX workers; 0 chooses up to four."),
    ] = 0,
    form_profile: Annotated[
        Path | None, typer.Option(help="Custom Microsoft Forms profile.")
    ] = None,
    submit: Annotated[bool, typer.Option(help="Submit the event to Microsoft Forms.")] = False,
    preview: Annotated[bool, typer.Option(help="Generate JSON without submitting.")] = False,
    no_input: Annotated[bool, typer.Option(help="Never prompt for missing input.")] = False,
    choose_room: Annotated[
        bool, typer.Option(help="Choose a venue by building, room number and capacity.")
    ] = False,
    rooms: Annotated[
        Path | None,
        typer.Option(help="Custom room CSV for interactive venue selection."),
    ] = None,
) -> None:
    """Generate event form JSON, risk documents, or both"""
    if submit and preview:
        raise typer.BadParameter("--submit and --preview are mutually exclusive")
    interactive = sys.stdin.isatty() and not no_input
    if interactive:
        intro("Event", "Choose a room and build your event pack")
    mode = "both" if form and risk else "form" if form else "risk" if risk else None
    if input is None:
        if not interactive:
            raise typer.BadParameter("input is required; pass event.toml or a directory")
        input = Path(
            ask(
                "Event TOML or folder (a new .toml starts setup)",
                default="event.toml",
                paths=True,
                required=True,
            )
        )
    try:
        input = input.expanduser()
        if interactive and not input.exists() and input.suffix.casefold() == ".toml":
            _setup(input, mode, rooms)
            choose_room = False
            if submit:
                raise MiniError(
                    "Your event TOML is saved; review the unanswered booking questions and terms "
                    "in it before requesting submission"
                )
        result = generate(
            input,
            mode=mode,
            risk_layout=layout,
            destination=output_dir,
            logo=logo,
            form_profile=form_profile,
            form_action="submit" if submit else "preview" if preview else None,
            force=force,
            jobs=jobs,
            interactive=interactive,
            show_progress=True,
            choose_room=choose_room,
            rooms=rooms,
            review=_review if interactive else None,
        )
    except (MiniError, OSError, ValueError, httpx.HTTPError) as exc:
        raise MiniError(str(exc)) from exc
    view = table("Made for you", "Saved to", title="Your event pack is ready")
    for kind, path in result.outputs:
        view.add_row(Text(kind), Text(str(path)))
    CONSOLE.print(view)
    for source, status in result.submissions:
        CONSOLE.print(f"Submitted {source} (HTTP {status})", markup=False)
