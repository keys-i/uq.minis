"""Browser course research using Scrappy's existing parsers and resumable exports

The browser uses the same course parsers, offering validation and resumable
export operations as the CLI. Routes register completed files for download
without exposing arbitrary filesystem paths
"""

from pathlib import Path

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from uq_minis.app.core import Workspace, page, upload, value, workspace
from uq_minis.core.common import MiniError
from uq_minis.core.paths import STATE
from uq_minis.minis.scrappy import export_details, export_links, list_courses

router = APIRouter()


def _show(request: Request, **results: object) -> dict[str, object]:
    context = workspace(request)
    return page(
        request,
        "scrappy",
        fields=[
            {
                "name": "action",
                "label": "What would you like to do?",
                "type": "select",
                "options": [
                    ("list", "Search saved courses"),
                    ("links", "Refresh offering links"),
                    ("details", "Export UQ course details"),
                ],
            },
            {
                "name": "university",
                "label": "University",
                "type": "select",
                "options": [("uq", "UQ"), ("unsw", "UNSW CSE")],
            },
            {"name": "offerings", "label": "Offering CSV", "value": str(context.courses)},
            {"name": "query", "label": "Course code or search words"},
            {"name": "course", "label": "One course to export · blank exports all"},
            {"name": "term", "label": "UNSW term · for example 26T3", "group": "Export settings"},
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
            {
                "name": "fresh",
                "label": "Restart this export instead of resuming its checkpoint",
                "type": "checkbox",
                "group": "Export settings",
            },
            {"name": "html", "label": "Optional saved catalogue HTML", "type": "file"},
            {
                "name": "jobs",
                "label": "Concurrent requests",
                "type": "number",
                "min": 1,
                "max": 8,
                "value": 4,
            },
        ],
        note="UNSW links open published teaching resources; UQ detail exports preserve prerequisite wording and resume completed courses after a failed batch",
        **results,
    )


@router.get("/api/minis/scrappy")
def home(request: Request) -> dict[str, object]:
    """Show Scrappy's browser workflow"""
    return _show(request)


def _process(request: Request, form: FormData, context: Workspace) -> dict[str, object]:
    action = value(form, "action")
    if action not in {"list", "links", "details"}:
        raise MiniError("Choose a listed course action")
    source = Path(value(form, "offerings", str(context.courses))).expanduser()
    if action == "list":
        result = list_courses(
            source,
            query=value(form, "query"),
            offset=int(value(form, "offset", "0")),
            limit=int(value(form, "limit", "50")),
        )
        return _show(
            request,
            rows=result["courses"],
            columns=["course_code", "course_name", "offering_link"],
            result=f"{result['total']} matches; showing {len(result['courses'])}",
        )
    if action == "links":
        work = context.directory("scrappy")
        html = upload(form, "html", work / "search.html")
        university = value(form, "university", "uq")
        output = context.courses if university == "uq" else work / "unsw.csv"
        count = export_links(output, html=html, university=university, term=value(form, "term"))
    else:
        output = STATE / "scrappy" / "browser" / (value(form, "course").upper() or "courses")
        if not output.name.replace("_", "").isalnum():
            raise MiniError("Choose a valid course code")
        output = output.with_suffix(".csv")
        count = export_details(
            source,
            output,
            course=value(form, "course") or None,
            jobs=int(value(form, "jobs", "4")),
            fresh=value(form, "fresh") == "on",
        )
    return _show(request, result=f"Saved {count} records", downloads=[context.publish(output)])


@router.post("/api/minis/scrappy")
async def submit(request: Request) -> dict[str, object]:
    """Execute a bounded browser export without calling the CLI"""
    async with request.form(max_files=1, max_part_size=8 * 1024**2) as form:
        return await run_in_threadpool(_process, request, form, workspace(request))
