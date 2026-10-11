"""Microsoft Forms sign-in commands"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from uq_minis.core.common import MiniError
from uq_minis.core.paths import STATE
from uq_minis.core.terminal import CONSOLE, ERROR, application, intro
lazy from uq_minis.core.forms import load_form_profile
lazy from uq_minis.minis import auth

app = application()


@app.command()
def run(
    browser: Annotated[
        Literal["chromium", "firefox", "webkit", "chrome", "edge"],
        typer.Option(help="Browser for the sign-in window."),
    ] = "chromium",
    timeout: Annotated[int, typer.Option(min=1, help="Seconds to wait for sign-in.")] = 300,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Private environment file for captured credentials.",
        ),
    ] = STATE / "auth/.env",
    form_profile: Annotated[
        Path | None, typer.Option(help="Custom Microsoft Forms profile.")
    ] = None,
    force: Annotated[bool, typer.Option(help="Refresh credentials in an existing file.")] = False,
    no_input: Annotated[
        bool, typer.Option(help="Reject browser sign-in for unattended runs.")
    ] = False,
) -> None:
    """Sign in through a browser and save Forms credentials"""
    if no_input:
        raise typer.BadParameter(
            "auth requires browser sign-in; use saved .env credentials for unattended submissions"
        )
    output = output.expanduser()
    if output.is_symlink() or (output.exists() and not force):
        raise typer.BadParameter(
            "Output already exists or is a symlink; choose another path or --force"
        )
    try:
        if CONSOLE.is_terminal:
            intro("Auth", "Let’s get you signed in · finish the sign-in in your browser")
        auth.write_env(
            output,
            auth.capture(load_form_profile(form_profile), browser=browser, timeout=timeout),
            force=force,
        )
    except (MiniError, OSError, ValueError) as exc:
        ERROR.print(f"auth: {exc}", style="error", markup=False)
        raise typer.Exit(2) from exc
    CONSOLE.print(f"Saved Forms credentials to {output}", style="success", markup=False)
