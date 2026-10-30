"""Browser club discovery and authorised Discord event collection

Routes call the existing directory and event collectors rather than a
second scraper implementation. Public exports are complete before they are
registered for download; collection does not post to club accounts
"""

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from uq_minis.app.core import Workspace, page, upload, value, workspace
from uq_minis.core.common import MiniError
from uq_minis.minis.clubby import directory, events, social

router = APIRouter()


def _show(request: Request, **results: object) -> dict[str, object]:
    return page(
        request,
        "clubby",
        fields=[
            {
                "name": "action",
                "label": "What would you like to do?",
                "type": "select",
                "options": [
                    ("search", "Find clubs by interest"),
                    ("refresh", "Refresh the public UQ directory"),
                    ("enrich", "Update full club profiles"),
                    ("import", "Import historical club exports"),
                    ("events", "Collect Discord scheduled events"),
                    ("posts", "Read authorised social announcements"),
                ],
            },
            {"name": "query", "label": "Club name or interest"},
            {
                "name": "offset",
                "label": "Start at result",
                "type": "number",
                "value": 0,
                "min": 0,
                "group": "Export settings",
            },
            {
                "name": "limit",
                "label": "Results per page",
                "type": "range",
                "value": 50,
                "min": 1,
                "max": 200,
                "group": "Export settings",
            },
            {"name": "source", "label": "Club directory CSV or Discord JSON", "type": "file"},
            {"name": "details", "label": "Optional historical club details CSV", "type": "file"},
            {
                "name": "guilds",
                "label": "Discord server IDs · separate with commas",
                "help": "Live reads use DISCORD_BOT_TOKEN from this computer, never a token entered into this page",
            },
            {
                "name": "provider",
                "label": "Social source",
                "type": "select",
                "options": [(key, label) for key, label in social.PROVIDERS.items()],
            },
            {"name": "account", "label": "Authorised social account ID"},
            {"name": "club", "label": "Club name for social announcements"},
        ],
        note="Open Planny's Clubby and Buzzy views to follow clubs and bring their events into your personal calendar",
        **results,
    )


@router.get("/api/minis/clubby")
def home(request: Request) -> dict[str, object]:
    """Show club discovery in the browser"""
    return _show(request)


def _process(request: Request, form: FormData, context: Workspace) -> dict[str, object]:
    action = value(form, "action")
    if action not in {"search", "refresh", "enrich", "import", "events", "posts"}:
        raise MiniError("Choose a listed club action")
    if action == "search":
        rows, total = directory.search(
            context.clubs,
            query=value(form, "query"),
            offset=int(value(form, "offset", "0")),
            limit=int(value(form, "limit", "50")),
        )
        return _show(
            request,
            rows=rows,
            columns=["name", "interests", "directory_url"],
            result=f"{total} matches; showing {len(rows)}",
        )
    work = context.directory("clubby")
    if action == "refresh":
        count, output = directory.refresh(context.clubs), context.clubs
    elif action == "enrich":
        count, output = directory.enrich(context.clubs), context.clubs
    elif action == "import":
        source = upload(form, "source", work / "clubs.csv")
        if source is None:
            raise MiniError("Choose a historical directory CSV")
        output = work / "combined.csv"
        count = directory.import_csv(
            source, output, details=upload(form, "details", work / "details.csv")
        )
    elif action == "posts":
        output = work / "posts.json"
        count = social.export(
            output, value(form, "provider"), value(form, "account"), club=value(form, "club")
        )
    else:
        source = upload(form, "source", work / "events.json")
        output = work / "events.csv"
        count = events.export(
            output,
            guilds=[item.strip() for item in value(form, "guilds").split(",") if item.strip()],
            source=source,
        )
    return _show(request, result=f"Saved {count} records", downloads=[context.publish(output)])


@router.post("/api/minis/clubby")
async def submit(request: Request) -> dict[str, object]:
    """Collect complete exports without posting to social services"""
    async with request.form(max_files=2, max_part_size=8 * 1024**2) as form:
        return await run_in_threadpool(_process, request, form, workspace(request))
