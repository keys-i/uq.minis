"""Event form and risk-document commands"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.text import Text

from uq_minis.core.common import MiniError, RiskLayout
from uq_minis.core.terminal import CONSOLE, ERROR, application, ask, intro, table

app = application()


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
        Path | None, typer.Option(help="Custom room CSV for interactive venue selection.")
    ] = None,
) -> None:
    """Generate event form JSON, risk documents, or both"""
    import httpx

    from uq_minis.minis.event import generate

    if submit and preview:
        raise typer.BadParameter("--submit and --preview are mutually exclusive")
    interactive = sys.stdin.isatty() and not no_input
    if interactive:
        intro("Event", "Good plans start here · forms, rooms and your risk assessment")
    if input is None:
        if not interactive:
            raise typer.BadParameter("input is required; pass event.toml or a directory")
        input = Path(
            ask("Event TOML or directory", default="event.toml", paths=True, required=True)
        )
    mode = "both" if form and risk else "form" if form else "risk" if risk else None
    try:
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
        )
    except (MiniError, OSError, ValueError, httpx.HTTPError) as exc:
        ERROR.print(Panel.fit(Text(str(exc)), title="event", border_style="error"))
        raise typer.Exit(2) from exc
    view = table("Made for you", "Saved to", title="Your event pack is ready")
    for kind, path in result.outputs:
        view.add_row(Text(kind), Text(str(path)))
    CONSOLE.print(view)
    for source, status in result.submissions:
        CONSOLE.print(f"Submitted {source} (HTTP {status})", markup=False)
