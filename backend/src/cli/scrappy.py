"""Course browsing and export commands

The terminal browses bounded catalogue pages and resumes complete exports
using the shared parsers. Interactive navigation preserves the current
shortlist and expected upstream failures remain editable
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.text import Text

from uq_minis.cli.planny import investigate, knowledge, ready, secat
from uq_minis.core.art import RESIDENTS
from uq_minis.core.common import MiniError
from uq_minis.core.terminal import (
    CONSOLE,
    Back,
    activity,
    application,
    ask,
    intro,
    recover,
    table,
)
lazy from uq_minis.minis.scrappy import (
    export_details,
    export_links,
    list_courses,
    load_offerings,
)

app = application(theme=RESIDENTS["scrappy"], invoke_without_command=True)
app.command("research")(investigate)
app.command("knowledge")(knowledge)
app.command("ready")(ready)
app.command("secat")(secat)


def _show_courses(offerings: Path, query: str = "", offset: int = 0, limit: int = 20) -> int:
    page = list_courses(offerings, query=query, offset=offset, limit=limit)
    view = table("Code", "Course", title=f"Courses · {page['total']} matches")
    for row in page["courses"]:
        view.add_row(Text(row["course_code"]), Text(row["course_name"]))
    CONSOLE.print(view)
    if page["courses"]:
        CONSOLE.print(f"Showing {offset + 1}–{offset + len(page['courses'])}")
    else:
        CONSOLE.print("No courses found · try another code or keyword", style="warning")
    return page["total"]


def _browse(offerings: Path) -> None:

    offset, query = 0, ""
    while True:
        total = _show_courses(offerings, query, offset)
        action = ask("Browse", choices=("next", "prev", "search", "back"), default="back")
        if action == "back":
            return
        if action == "search":
            query, offset = ask("Search code or name (blank for all)"), 0
        elif action == "next" and offset + 20 < total:
            offset += 20
        elif action == "prev":
            offset = max(0, offset - 20)


def _export(offerings: Path, output: Path, course: str | None, jobs: int, fresh: bool) -> None:
    with activity("Gathering your courses") as progress:

        def update(done: int, total: int, message: str) -> None:
            progress(done / total if total else None, message)

        count = export_details(
            offerings, output, course=course, jobs=jobs, fresh=fresh, progress=update
        )
    CONSOLE.print(f"Wrote {count} courses to {output}", markup=False, style="success")


@app.callback()
def menu(
    ctx: typer.Context,
    offerings: Annotated[Path, typer.Option(help="Menu offering CSV.")] = Path(
        "courses_offerings.csv"
    ),
    output_dir: Annotated[Path, typer.Option(help="Menu detail export directory.")] = Path(
        "courses"
    ),
    html: Annotated[Path | None, typer.Option(help="Saved HTML for menu link refresh.")] = None,
    jobs: Annotated[int, typer.Option(min=1, max=8, help="Concurrent menu requests.")] = 4,
    no_input: Annotated[bool, typer.Option(help="Show help instead of opening the menu.")] = False,
) -> None:
    """Browse courses and export details. Run without a command for the interactive menu"""
    if ctx.invoked_subcommand:
        return
    if no_input or not sys.stdin.isatty():
        typer.echo(ctx.get_help())
        return

    offerings, output_dir = offerings.expanduser(), output_dir.expanduser()
    html = html.expanduser() if html else None
    intro("Scrappy", "Browse courses and save a shortlist")
    actions = {
        "1": "Browse / search courses",
        "2": "Refresh course links",
        "3": "Save one course",
        "4": "Save all courses",
        "5": "Back to minis",
    }
    while True:
        try:
            choice = ask(
                "What’s next?",
                choices=actions,
                default="1",
                show_choices=False,
            )
            if choice == "5":
                raise Back
            if choice == "2" or not offerings.exists():
                with activity("Reading course links"):
                    count = export_links(offerings, html=html)
                CONSOLE.print(f"Wrote {count} offerings to {offerings}", markup=False)
            if choice == "1":
                _browse(offerings)
            elif choice == "3":
                codes = sorted({row["course_code"] for row in load_offerings(offerings)})
                code = ask("Course code", suggestions=codes, ignore_case=True).strip().upper()
                if code not in codes:
                    raise MiniError(f"Course {code!r} is not in the offering CSV")
                _export(offerings, output_dir / f"{code}.csv", code, jobs, False)
            elif choice == "4":
                _export(offerings, output_dir / "courses.csv", None, jobs, False)
        except EOFError, KeyboardInterrupt:
            return
        except (MiniError, OSError, ValueError) as exc:
            recover(exc, ())


@app.command("list")
def courses(
    offerings: Annotated[Path, typer.Argument(help="Offering CSV.")] = Path(
        "courses_offerings.csv"
    ),
    query: Annotated[str, typer.Option(help="Filter by course code or name.")] = "",
    offset: Annotated[int, typer.Option(min=0)] = 0,
    limit: Annotated[int, typer.Option(min=1, max=200)] = 50,
) -> None:
    """Browse one page of saved course offerings"""
    _show_courses(offerings, query, offset, limit)


@app.command()
def links(
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("courses_offerings.csv"),
    html: Annotated[Path | None, typer.Option(help="Saved search HTML.")] = None,
    university: Annotated[str, typer.Option(help="Official index: uq or unsw.")] = "uq",
    term: Annotated[str, typer.Option(help="Select a published UNSW term, such as 26T3.")] = "",
) -> None:
    """Write UQ offerings or published UNSW teaching links"""
    with activity("Reading course links"):
        count = export_links(output, html=html, university=university, term=term)
    CONSOLE.print(f"Wrote {count} offerings to {output}", style="success", markup=False)


@app.command()
def details(
    offerings: Annotated[Path, typer.Argument(help="Offering CSV from links.")],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("courses.csv"),
    course: Annotated[str | None, typer.Option(help="Export only this course code.")] = None,
    jobs: Annotated[
        int, typer.Option("--jobs", "-j", min=1, max=8, help="Concurrent requests.")
    ] = 4,
    fresh: Annotated[bool, typer.Option(help="Discard checkpointed work and fetch again.")] = False,
) -> None:
    """Write course details from offering links"""
    _export(offerings, output, course, jobs, fresh)


@app.command("catalogue")
def catalogue() -> None:
    """Crawl the official UQ course index used by browser course discovery"""
    from uq_minis.core.paths import STATE
    from uq_minis.minis.planny import research

    data = research.catalogue(STATE / "planny" / "research.json")
    CONSOLE.print(f"Saved {len(data['courses'])} official UQ courses", markup=False)
