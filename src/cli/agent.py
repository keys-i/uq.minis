"""Persistent event-mail watcher commands"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.text import Text

from uq_minis.core.terminal import CONSOLE, application, intro, table
from uq_minis.worker.event import DEFAULT_STATE

app = application(theme="huia")


@app.command()
def login(
    mailbox: Annotated[str, typer.Option(help="Actual Outlook email address.")],
    username: Annotated[
        str | None, typer.Option(help="Browser sign-in address, if different from mailbox.")
    ] = None,
    backend: Annotated[
        str | None, typer.Option(help="browser (default), or graph with app registration IDs.")
    ] = None,
    client_id: Annotated[str | None, typer.Option(help="Microsoft app client ID.")] = None,
    tenant_id: Annotated[str | None, typer.Option(help="Microsoft tenant ID.")] = None,
    state_dir: Annotated[
        Path, typer.Option(help="Persistent agent state directory.")
    ] = DEFAULT_STATE,
) -> None:
    """Sign into the selected Outlook backend"""
    from uq_minis.minis import agent

    agent.login(
        username=username,
        backend=backend,
        client_id=client_id,
        tenant_id=tenant_id,
        mailbox=mailbox,
        state_dir=state_dir,
    )


@app.command()
def watch(
    source: Annotated[Path, typer.Argument(help="Event TOML file.")],
    event_id: Annotated[str, typer.Option(help="UQ event reference ID.")],
    attachment: Annotated[Path | None, typer.Option(help="Risk assessment attachment.")] = None,
    since: Annotated[str | None, typer.Option(help="Only process mail since YYYY-MM-DD.")] = None,
    state_dir: Annotated[
        Path, typer.Option(help="Persistent agent state directory.")
    ] = DEFAULT_STATE,
) -> None:
    """Follow an event and authorise its risk-assessment reply"""
    from uq_minis.minis import agent

    typer.echo(
        json.dumps(
            agent.watch(
                source,
                event_id=event_id,
                attachment=attachment,
                since=since,
                state_dir=state_dir,
            )
        )
    )


@app.command()
def poll(
    state_dir: Annotated[
        Path, typer.Option(help="Persistent agent state directory.")
    ] = DEFAULT_STATE,
) -> None:
    """Process one mailbox pass"""
    from uq_minis.minis import agent

    agent.poll(state_dir=state_dir)


@app.command()
def status(
    state_dir: Annotated[
        Path, typer.Option(help="Persistent agent state directory.")
    ] = DEFAULT_STATE,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Show saved event progress"""
    from uq_minis.minis import agent

    rows = agent.status(state_dir=state_dir)
    if as_json:
        typer.echo(json.dumps(rows))
        return
    if not rows:
        intro("Agent", "Nothing to keep an eye on yet")
        CONSOLE.print("Follow a booking with mini agent watch event.toml --event-id ID")
        return
    view = table("Event ID", "Title", "State", "Outcome", "Error", title="Your bookings")
    for row in rows:
        view.add_row(
            *(
                Text(str(row.get(key, "")))
                for key in ("event_id", "title", "state", "outcome", "error")
            )
        )
    CONSOLE.print(view)


@app.command()
def retry_send(
    event_id: Annotated[str, typer.Argument()],
    confirm_not_sent: Annotated[
        bool, typer.Option(help="Confirm no matching email is in Sent Items.")
    ] = False,
    state_dir: Annotated[
        Path, typer.Option(help="Persistent agent state directory.")
    ] = DEFAULT_STATE,
) -> None:
    """Permit a retry after checking Sent Items"""
    from uq_minis.minis import agent

    agent.retry_send(event_id, confirm_not_sent=confirm_not_sent, state_dir=state_dir)


@app.command()
def stop(
    event_id: Annotated[str, typer.Argument()],
    state_dir: Annotated[
        Path, typer.Option(help="Persistent agent state directory.")
    ] = DEFAULT_STATE,
) -> None:
    """Stop following an event and preserve its history"""
    from uq_minis.minis import agent

    agent.stop(event_id, state_dir=state_dir)


@app.command()
def install(
    state_dir: Annotated[
        Path, typer.Option(help="Persistent agent state directory.")
    ] = DEFAULT_STATE,
    interval: Annotated[int, typer.Option(min=1, help="Seconds between mailbox polls.")] = 60,
) -> None:
    """Install the persistent mailbox watcher"""
    from uq_minis.worker.service import install as install_service

    typer.echo(str(install_service(state_dir, interval)))


@app.command()
def uninstall() -> None:
    """Uninstall the mailbox watcher"""
    from uq_minis.worker.service import uninstall as uninstall_service

    uninstall_service()
