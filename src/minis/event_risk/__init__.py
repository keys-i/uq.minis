"""Risk-assessment DOCX event mini"""

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from uq_minis.helper.common import RiskLayout

app = typer.Typer(
    add_completion=False, rich_markup_mode="rich", pretty_exceptions_show_locals=False
)


@app.command()
def run(
    input: Annotated[
        Path | None,
        typer.Argument(help="Event TOML file or directory."),
    ] = None,
    layout: Annotated[
        RiskLayout | None,
        typer.Option("--layout", "--risk-layout", help="Risk form, summary pack, or both."),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", "-o", help="Destination directory."),
    ] = None,
    logo: Annotated[Path | None, typer.Option(help="Logo image for the document.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace existing output files.")] = False,
    jobs: Annotated[
        int, typer.Option("--jobs", "-j", min=0, help="DOCX workers; 0 chooses up to four.")
    ] = 0,
    no_input: Annotated[
        bool, typer.Option("--no-input", help="Never prompt; require input and layout.")
    ] = False,
) -> None:
    """Build a risk assessment, an event pack or both"""
    from uq_minis.minis.event import ERROR, _input, generate, show_result

    interactive = sys.stdin.isatty() and not no_input
    try:
        result = generate(
            _input(input, interactive=interactive),
            mode="risk",
            risk_layout=layout,
            destination=output_dir,
            logo=logo,
            force=force,
            jobs=jobs,
            interactive=interactive,
        )
    except (OSError, ValueError) as exc:
        ERROR.print(Panel.fit(str(exc), title="event-risk", border_style="red"))
        raise typer.Exit(2) from exc
    show_result(result)


def main(argv: list[str] | None = None) -> None:
    """Run the event-risk mini"""
    app(args=argv, prog_name="mini --tool event-risk")


if __name__ == "__main__":
    main()
