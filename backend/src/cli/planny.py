"""Headless planner exports alongside the shared browser experience

Commands inspect or edit the shared private plan and expose reviewed course
research, mark scenarios and calendar exports. Domain modules load lazily so
help and shell completion remain independent of optional integrations
"""

import json
from pathlib import Path
from typing import Annotated

import typer

from uq_minis.core.art import RESIDENTS
from uq_minis.core.common import MiniError
from uq_minis.core.paths import STATE
from uq_minis.core.terminal import application
lazy from uq_minis.minis import buzzy as ical
lazy from uq_minis.minis.planny import marks as calculator
lazy from uq_minis.minis.planny import plan, profile, readiness, research, sources

app = application(theme=RESIDENTS["planny"], no_args_is_help=True)
DEFAULT = STATE / "planny" / "plan.json"


@app.command("knowledge")
def knowledge(
    completed: Annotated[
        str | None,
        typer.Option(help="Completed course codes, separated by commas or spaces"),
    ] = None,
    skills: Annotated[str | None, typer.Option(help="Topics and skills you already know")] = None,
    state: Annotated[Path, typer.Option()] = DEFAULT,
) -> None:
    """Read or update the same private starting point used by the course browser"""
    current = plan.load(state.expanduser())
    if completed is not None:
        current["settings"]["completed"] = completed.replace(",", " ").split()
    if skills is not None:
        current["settings"]["skills"] = skills
    if completed is not None or skills is not None:
        current = plan.save(state.expanduser(), current)
    typer.echo(json.dumps(current["settings"], ensure_ascii=False, indent=2))


@app.command("ready")
def ready(code: str, state: Annotated[Path, typer.Option()] = DEFAULT) -> None:
    """Check published prerequisites without claiming official enrolment eligibility"""
    info = profile.offerings(code)
    student = plan.load(state.expanduser())["settings"]
    typer.echo(
        json.dumps(
            {
                "url": info["url"],
                **readiness.check(
                    info["details"],
                    student.get("completed", []),
                    student.get("skills", ""),
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("translate")
def translate(
    text: str,
    to: Annotated[str, typer.Option(help="Target language code, such as hi, ar or fr")] = "en",
    source: Annotated[
        str, typer.Option(help="Known source language, or auto to detect it")
    ] = "auto",
) -> None:
    """Translate public text with the configured provider and retain its original"""
    from uq_minis.core import translate as provider

    typer.echo(
        json.dumps(
            {
                "original": text,
                "translated": provider.text(text, to, source),
                "language": to,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("research")
def investigate(
    query: Annotated[str, typer.Argument()] = "",
    refresh: Annotated[
        bool, typer.Option(help="Refresh the daily public research snapshot")
    ] = False,
    faculty: Annotated[str, typer.Option()] = "",
    metric: Annotated[str, typer.Option(help="overall, usefulness, fun, difficulty or secat")] = "",
    order: Annotated[str, typer.Option(help="asc or desc")] = "",
    professors: Annotated[bool, typer.Option()] = False,
    semester: Annotated[str, typer.Option(help="auto, all, 1, 2 or summer")] = "auto",
    minimum: Annotated[int, typer.Option(min=1, max=10000)] = 1,
    offset: Annotated[int, typer.Option(min=0, max=12000)] = 0,
    expand: Annotated[
        bool,
        typer.Option(help="Fill feedback gaps from the weekly public rating index"),
    ] = False,
    state: Annotated[Path, typer.Option()] = DEFAULT,
) -> None:
    """Search course and teacher reviews using the browser's research rules"""
    path = state.expanduser().with_name("research.json")
    data = research.refresh(path) if refresh else research.load(path)
    if expand:
        data = research.expand(path)
    student = plan.load(state.expanduser())["settings"]
    typer.echo(
        json.dumps(
            research.search(
                data,
                query,
                faculty=faculty,
                metric=metric,
                order=order,
                target="professor" if professors else "course",
                semester=semester,
                minimum=minimum,
                offset=offset,
                completed=student.get("completed", []),
                skills=student.get("skills", ""),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("secat")
def secat(
    source: Path,
    state: Annotated[Path, typer.Option()] = DEFAULT,
) -> None:
    """Combine a saved official UQ SECaT chart with the private course research"""
    source = source.expanduser()
    if source.stat().st_size > 8 * 1024**2:
        raise MiniError("Saved SECaT charts must be at most 8 MiB")
    count = research.import_secat(
        state.expanduser().with_name("research.json"),
        source.read_text(encoding="utf-8"),
    )
    typer.echo(f"Imported {count} official question results with their periods and sample sizes")


@app.command("show")
def show(state: Annotated[Path, typer.Option()] = DEFAULT) -> None:
    """Print the editable plan; use mini browser for the React interface"""
    typer.echo(json.dumps(plan.load(state.expanduser()), ensure_ascii=False, indent=2))


@app.command()
def calendar(
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("out/planny/calendar.ics"),
    state: Annotated[Path, typer.Option()] = DEFAULT,
) -> None:
    """Export official deadlines and separate personal targets as a calendar"""
    from uq_minis.core.cache import writing

    if output.expanduser().resolve() == state.expanduser().resolve():
        raise MiniError("Choose a different output from the private plan")
    with writing(output.expanduser()) as temporary:
        temporary.write_text(
            ical.render(
                sources.calendar(
                    plan.load(state.expanduser()),
                    state.expanduser().parent.parent / "clubby" / "feed.json",
                )
            ),
            encoding="utf-8",
            newline="",
        )
    typer.echo(f"Saved calendar to {output}")


@app.command()
def marks(
    state: Annotated[Path, typer.Option()] = DEFAULT,
    estimate: Annotated[float, typer.Option(min=0, max=100)] = 75,
) -> None:
    """Calculate group-project PAF, hurdle and drop-lowest scenarios from the saved plan"""
    current = plan.load(state.expanduser())
    typer.echo(
        json.dumps(
            {
                course["code"]: calculator.calculate(
                    course,
                    [item for item in current["assessments"] if item["course"] == course["id"]],
                    target=current["settings"]["target"],
                    estimate=estimate,
                )
                for course in current["courses"]
            },
            indent=2,
        )
    )


@app.command("import")
def imported(
    source: Path,
    state: Annotated[Path, typer.Option()] = DEFAULT,
    force: Annotated[
        bool, typer.Option(help="Replace an existing plan after checking its backup.")
    ] = False,
) -> None:
    """Load an editable JSON plan or restore a reviewed backup"""
    state = state.expanduser()
    current = plan.load(state)
    if state.exists() and not force:
        raise MiniError("A plan exists; back it up and use --force to replace it")
    incoming = plan.validate(json.loads(source.expanduser().read_text(encoding="utf-8")))
    incoming["revision"] = current["revision"]
    plan.save(state, incoming)
    typer.echo(f"Saved private plan to {state}")
