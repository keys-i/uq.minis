"""Typer commands for built-in minis."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from uq_minis.helper.common import MiniError, RiskLayout
from uq_minis.helper.prompt import ask

CONSOLE = Console()
ERROR = Console(stderr=True)
DEFAULT_AGENT_STATE = Path("~/Library/Application Support/UQ minis/agent").expanduser()


def _event() -> typer.Typer:
    app = typer.Typer(
        add_completion=False,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
    )

    @app.command()
    def run(
        input: Annotated[Path | None, typer.Argument(help="Event TOML file or directory.")] = None,
        form: Annotated[
            bool, typer.Option("--form", help="Generate Microsoft Forms JSON.")
        ] = False,
        risk: Annotated[
            bool, typer.Option("--risk", help="Generate risk-assessment DOCX.")
        ] = False,
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
    ) -> None:
        """Generate event form JSON, risk documents, or both."""
        import httpx

        from uq_minis.minis.event import generate

        if submit and preview:
            raise typer.BadParameter("--submit and --preview are mutually exclusive")
        interactive = sys.stdin.isatty() and not no_input
        if input is None:
            if not interactive:
                raise typer.BadParameter("input is required; pass event.toml or a directory")
            input = Path(ask("Event TOML or directory", default="event.toml"))
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
            )
        except (MiniError, OSError, ValueError, httpx.HTTPError) as exc:
            ERROR.print(Panel.fit(str(exc), title="event", border_style="red"))
            raise typer.Exit(2) from exc
        view = Table("Type", "Path", title="Generated", header_style="bold green")
        for kind, path in result.outputs:
            view.add_row(kind, str(path))
        CONSOLE.print(view)
        for source, status in result.submissions:
            CONSOLE.print(f"Submitted {source} (HTTP {status})", markup=False)

    return app


def _auth() -> typer.Typer:
    app = typer.Typer(
        add_completion=False,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
    )

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
        ] = Path(".env"),
        form_profile: Annotated[
            Path | None, typer.Option(help="Custom Microsoft Forms profile.")
        ] = None,
        force: Annotated[
            bool, typer.Option(help="Refresh credentials in an existing file.")
        ] = False,
        no_input: Annotated[
            bool, typer.Option(help="Reject browser sign-in for unattended runs.")
        ] = False,
    ) -> None:
        """Sign in through a browser and save Forms credentials."""
        from uq_minis.helper.forms import load_form_profile
        from uq_minis.minis import auth

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
            auth.write_env(
                output,
                auth.capture(load_form_profile(form_profile), browser=browser, timeout=timeout),
                force=force,
            )
        except (MiniError, OSError, ValueError) as exc:
            ERROR.print(f"auth: {exc}", style="red")
            raise typer.Exit(2) from exc
        CONSOLE.print(f"Saved Forms credentials to {output}", style="green")

    return app


def _scrappy() -> typer.Typer:
    app = typer.Typer(
        invoke_without_command=True,
        add_completion=False,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
    )

    def show_courses(offerings: Path, query: str = "", offset: int = 0, limit: int = 20) -> int:
        from rich.text import Text

        from uq_minis.minis.scrappy import list_courses

        page = list_courses(offerings, query=query, offset=offset, limit=limit)
        view = Table(
            "Code", "Course", title=f"Courses · {page['total']} matches", header_style="bold cyan"
        )
        for row in page["courses"]:
            view.add_row(Text(row["course_code"]), Text(row["course_name"]))
        CONSOLE.print(view)
        if page["courses"]:
            CONSOLE.print(f"Showing {offset + 1}–{offset + len(page['courses'])}")
        return page["total"]

    def browse(offerings: Path) -> None:
        from prompt_toolkit import prompt

        offset, query = 0, ""
        while True:
            total = show_courses(offerings, query, offset)
            action = ask("Browse", choices=("next", "prev", "search", "back"), default="back")
            if action == "back":
                return
            if action == "search":
                query, offset = prompt("Search code or name (blank for all): "), 0
            elif action == "next" and offset + 20 < total:
                offset += 20
            elif action == "prev":
                offset = max(0, offset - 20)

    def run_export(
        offerings: Path, output: Path, course: str | None, jobs: int, fresh: bool
    ) -> None:
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            TextColumn,
            TimeElapsedColumn,
        )
        from rich.text import Text

        from uq_minis.minis.scrappy import export_details

        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=CONSOLE,
            disable=not CONSOLE.is_terminal,
        ) as progress:
            task = progress.add_task("Courses", total=None)

            def update(done, total, message):
                progress.update(task, total=total, completed=done, description=Text(message))

            count = export_details(
                offerings, output, course=course, jobs=jobs, fresh=fresh, progress=update
            )
        CONSOLE.print(f"Wrote {count} courses to {output}", markup=False)

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
        no_input: Annotated[
            bool, typer.Option(help="Show help instead of opening the menu.")
        ] = False,
    ) -> None:
        """Browse courses and export details. Run without a command for the interactive menu."""
        if ctx.invoked_subcommand:
            return
        if no_input or not sys.stdin.isatty():
            typer.echo(ctx.get_help())
            return
        from prompt_toolkit import prompt
        from prompt_toolkit.completion import WordCompleter

        from uq_minis.minis.scrappy import export_links, load_offerings

        offerings, output_dir = offerings.expanduser(), output_dir.expanduser()
        html = html.expanduser() if html else None
        while True:
            menu_view = Table("", "Scrappy", header_style="bold cyan", box=None)
            for number, label in enumerate(
                (
                    "Browse / search courses",
                    "Refresh course links",
                    "Scrape one course",
                    "Scrape all courses",
                    "Exit",
                ),
                1,
            ):
                menu_view.add_row(str(number), label)
            CONSOLE.print(menu_view)
            try:
                choice = ask("Action", choices=("1", "2", "3", "4", "5"), default="5")
                if choice == "5":
                    return
                if choice == "2" or not offerings.exists():
                    with CONSOLE.status("Reading course links…"):
                        count = export_links(offerings, html=html)
                    CONSOLE.print(f"Wrote {count} offerings to {offerings}", markup=False)
                if choice == "1":
                    browse(offerings)
                elif choice == "3":
                    codes = sorted({row["course_code"] for row in load_offerings(offerings)})
                    code = (
                        prompt("Course code: ", completer=WordCompleter(codes, ignore_case=True))
                        .strip()
                        .upper()
                    )
                    if code not in codes:
                        raise MiniError(f"Course {code!r} is not in the offering CSV")
                    run_export(offerings, output_dir / f"{code}.csv", code, jobs, False)
                elif choice == "4":
                    run_export(offerings, output_dir / "courses.csv", None, jobs, False)
            except (EOFError, KeyboardInterrupt):
                return
            except (MiniError, OSError, ValueError) as exc:
                ERROR.print(f"scrappy: {exc}", style="red", markup=False)

    @app.command("list")
    def courses(
        offerings: Annotated[Path, typer.Argument(help="Offering CSV.")] = Path(
            "courses_offerings.csv"
        ),
        query: Annotated[str, typer.Option(help="Filter by course code or name.")] = "",
        offset: Annotated[int, typer.Option(min=0)] = 0,
        limit: Annotated[int, typer.Option(min=1, max=200)] = 50,
    ) -> None:
        """Browse one page of saved course offerings."""
        show_courses(offerings, query, offset, limit)

    @app.command()
    def links(
        output: Annotated[Path, typer.Option("--output", "-o")] = Path("courses_offerings.csv"),
        html: Annotated[Path | None, typer.Option(help="Saved search HTML.")] = None,
    ) -> None:
        """Write course offering links."""
        from uq_minis.minis.scrappy import export_links

        count = export_links(output, html=html)
        typer.echo(f"Wrote {count} offerings to {output}")

    @app.command()
    def details(
        offerings: Annotated[Path, typer.Argument(help="Offering CSV from links.")],
        output: Annotated[Path, typer.Option("--output", "-o")] = Path("courses.csv"),
        course: Annotated[str | None, typer.Option(help="Export only this course code.")] = None,
        jobs: Annotated[
            int, typer.Option("--jobs", "-j", min=1, max=8, help="Concurrent requests.")
        ] = 4,
        fresh: Annotated[
            bool, typer.Option(help="Discard checkpointed work and fetch again.")
        ] = False,
    ) -> None:
        """Write course details from offering links."""
        run_export(offerings, output, course, jobs, fresh)

    return app


def _agent() -> typer.Typer:
    app = typer.Typer(
        add_completion=False,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
    )

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
        ] = DEFAULT_AGENT_STATE,
    ) -> None:
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
        since: Annotated[
            str | None, typer.Option(help="Only process mail since YYYY-MM-DD.")
        ] = None,
        state_dir: Annotated[
            Path, typer.Option(help="Persistent agent state directory.")
        ] = DEFAULT_AGENT_STATE,
    ) -> None:
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
        ] = DEFAULT_AGENT_STATE,
    ) -> None:
        from uq_minis.minis import agent

        agent.poll(state_dir=state_dir)

    @app.command()
    def status(
        state_dir: Annotated[
            Path, typer.Option(help="Persistent agent state directory.")
        ] = DEFAULT_AGENT_STATE,
        as_json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
    ) -> None:
        from uq_minis.minis import agent

        rows = agent.status(state_dir=state_dir)
        if as_json:
            typer.echo(json.dumps(rows))
            return
        view = Table("Event ID", "Title", "State", "Outcome", "Error")
        for row in rows:
            view.add_row(
                *(
                    str(row.get(key, ""))
                    for key in ("event_id", "title", "state", "outcome", "error")
                )
            )
        CONSOLE.print(view)

    @app.command("retry-send")
    def retry_send(
        event_id: Annotated[str, typer.Argument()],
        confirm_not_sent: Annotated[
            bool, typer.Option(help="Confirm no matching email is in Sent Items.")
        ] = False,
        state_dir: Annotated[
            Path, typer.Option(help="Persistent agent state directory.")
        ] = DEFAULT_AGENT_STATE,
    ) -> None:
        from uq_minis.minis import agent

        agent.retry_send(event_id, confirm_not_sent=confirm_not_sent, state_dir=state_dir)

    @app.command()
    def stop(
        event_id: Annotated[str, typer.Argument()],
        state_dir: Annotated[
            Path, typer.Option(help="Persistent agent state directory.")
        ] = DEFAULT_AGENT_STATE,
    ) -> None:
        from uq_minis.minis import agent

        agent.stop(event_id, state_dir=state_dir)

    @app.command()
    def install(
        state_dir: Annotated[
            Path, typer.Option(help="Persistent agent state directory.")
        ] = DEFAULT_AGENT_STATE,
        interval: Annotated[int, typer.Option(min=1, help="Seconds between mailbox polls.")] = 60,
    ) -> None:
        from uq_minis.workers.service import install as install_service

        typer.echo(str(install_service(state_dir, interval)))

    @app.command()
    def uninstall() -> None:
        from uq_minis.workers.service import uninstall as uninstall_service

        uninstall_service()

    return app


_BUILTINS = {"agent": _agent, "auth": _auth, "event": _event, "scrappy": _scrappy}


def get_app(name: str) -> typer.Typer:
    """Return a central built-in command or wrap a mini's plain run function."""
    builder = _BUILTINS.get(name)
    if builder:
        return builder()
    module = importlib.import_module(f"uq_minis.minis.{name.replace('-', '_')}")
    run = getattr(module, "run", None)
    if not callable(run):
        raise MiniError(f"{name} must export a run function")
    app = typer.Typer(
        add_completion=False,
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,
    )
    app.command()(run)
    return app
