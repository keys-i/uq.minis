"""Microsoft Forms event mini"""

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

app = typer.Typer(
    add_completion=False, rich_markup_mode="rich", pretty_exceptions_show_locals=False
)


@app.command()
def run(
    input: Annotated[
        Path | None,
        typer.Argument(help="Event TOML file or directory."),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", "-o", help="Destination directory."),
    ] = None,
    form_profile: Annotated[
        Path | None,
        typer.Option(help="Custom Microsoft Forms profile."),
    ] = None,
    submit: Annotated[
        bool, typer.Option("--submit", help="Submit the event to Microsoft Forms.")
    ] = False,
    preview: Annotated[
        bool, typer.Option("--preview", help="Generate JSON without submitting.")
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Replace existing output files.")] = False,
    no_input: Annotated[
        bool, typer.Option("--no-input", help="Never prompt for missing input.")
    ] = False,
) -> None:
    """Prepare booking JSON or submit an event form"""
    import httpx

    from uq_minis.minis.event import ERROR, _input, form_action, generate, show_result

    action = form_action(submit, preview)
    interactive = sys.stdin.isatty() and not no_input
    try:
        result = generate(
            _input(input, interactive=interactive),
            mode="form",
            destination=output_dir,
            form_profile=form_profile,
            form_action=action,
            force=force,
            interactive=interactive,
        )
    except (OSError, ValueError, httpx.HTTPError) as exc:
        ERROR.print(Panel.fit(str(exc), title="event-form", border_style="red"))
        raise typer.Exit(2) from exc
    show_result(result)


def main(argv: list[str] | None = None) -> None:
    """Run the event-form mini"""
    app(args=argv, prog_name="mini --tool event-form")


if __name__ == "__main__":
    main()
