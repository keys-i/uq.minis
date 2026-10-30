"""Club discovery and Discord scheduled-event exports

Commands select directory refreshes, profile enrichment and authorised
event sources. Collectors own validation and atomic exports; the terminal
layer owns options, previews and human-facing results
"""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.text import Text

from uq_minis.core.art import RESIDENTS
from uq_minis.core.paths import STATE
from uq_minis.core.terminal import CONSOLE, activity, application, table
lazy from uq_minis.minis.clubby import directory, events, social

app = application(theme=RESIDENTS["clubby"], no_args_is_help=True)
CATALOGUE = STATE / "clubby" / "clubs.csv"


@app.command()
def refresh(
    output: Annotated[Path, typer.Option("--output", "-o")] = CATALOGUE,
) -> None:
    """Save the complete current UQ club directory for offline search"""
    with activity("Reading UQ clubs"):
        count = directory.refresh(output)
    CONSOLE.print(f"Wrote {count} clubs to {output}", style="success", markup=False)


@app.command("enrich")
def enrich(
    output: Annotated[Path, typer.Option("--output", "-o")] = CATALOGUE,
) -> None:
    """Complete listed clubs' descriptions, artwork and links from UQU's public profiles"""
    with activity("Getting to know the clubs"):
        count = directory.enrich(output)
    CONSOLE.print(f"Saved {count} full club profiles to {output}", style="success", markup=False)


@app.command("profile")
def profile(url: str, source: Annotated[Path, typer.Option()] = CATALOGUE) -> None:
    """Read a listed club's full profile, social links and upcoming events"""
    typer.echo(json.dumps(directory.profile(source, url), ensure_ascii=False, indent=2))


@app.command("feed")
def feed(source: Annotated[Path, typer.Option()] = CATALOGUE) -> None:
    """Read the same public announcements shown beside the club browser"""
    from uq_minis.minis.planny import sources

    typer.echo(
        json.dumps(sources.feed(source.with_name("feed.json")), ensure_ascii=False, indent=2)
    )


@app.command("import")
def import_csv(
    source: Annotated[
        Path, typer.Argument(help="Saved club directory CSV, including old Name/Link exports.")
    ],
    details: Annotated[
        Path | None, typer.Option(help="Optional historical detail CSV to join by name.")
    ] = None,
    output: Annotated[Path, typer.Option("--output", "-o")] = CATALOGUE,
) -> None:
    """Combine historical club exports into a searchable catalogue"""
    with activity("Importing your clubs"):
        count = directory.import_csv(source, output, details=details)
    CONSOLE.print(f"Wrote {count} clubs to {output}", style="success", markup=False)


@app.command("list")
def clubs(
    source: Annotated[Path, typer.Argument(help="Saved club catalogue.")] = CATALOGUE,
    query: Annotated[str, typer.Option(help="Search names, interests and descriptions.")] = "",
    offset: Annotated[int, typer.Option(min=0)] = 0,
    limit: Annotated[int, typer.Option(min=1, max=200)] = 20,
) -> None:
    """Find clubs matching an interest and show their directory links"""
    rows, total = directory.search(source, query=query, offset=offset, limit=limit)
    view = table("Club", "Interests", "Directory", title=f"Clubs · {total} matches")
    for row in rows:
        view.add_row(Text(row["name"]), Text(row["interests"]), Text(row["directory_url"]))
    CONSOLE.print(view)
    if rows:
        CONSOLE.print(f"Showing {offset + 1}–{offset + len(rows)} of {total}")
    else:
        CONSOLE.print("No clubs found · try another name or interest", style="warning")


@app.command("events")
def scheduled(
    guild: Annotated[
        list[str] | None, typer.Option(help="Guild ID; repeat to combine servers.")
    ] = None,
    source: Annotated[
        Path | None, typer.Option("--json", help="Saved Discord scheduled-event JSON array.")
    ] = None,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("out/clubby/events.csv"),
) -> None:
    """Save Discord scheduled events using saved JSON or DISCORD_BOT_TOKEN"""
    with activity("Collecting scheduled events"):
        count = events.export(output, guilds=guild or [], source=source)
    CONSOLE.print(f"Wrote {count} events to {output}", style="success", markup=False)


@app.command()
def posts(
    provider: Annotated[str, typer.Option(help="facebook, instagram or linkedin")],
    account: Annotated[str, typer.Option(help="Authorised Page, Instagram or organisation ID")],
    club: Annotated[str, typer.Option(help="Club name for the imported announcements")] = "",
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("out/clubby/posts.json"),
) -> None:
    """Read recent authorised social posts into Buzzy's JSON import format"""
    with activity("Reading authorised club posts"):
        count = social.export(output, provider, account, club=club)
    CONSOLE.print(f"Wrote {count} posts to {output}", style="success", markup=False)
