"""Planny's browser API, sharing course and planning rules with its CLI

The browser shares plan validation, revision checks and calculations with
the CLI. Public catalogue and announcement reads are separate from private
student edits, which are validated before atomic replacement
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from uq_minis.app.core import workspace
from uq_minis.core.common import MiniError
from uq_minis.core.search import matches as contains
from uq_minis.core.search import terms
from uq_minis.minis.clubby import directory, events, social
from uq_minis.minis.planny import marks, plan, profile, sources
from uq_minis.minis.scrappy.scraper import export_links, load_offerings

router = APIRouter()
course_info = lru_cache(maxsize=32)(profile.offerings)


@lru_cache(maxsize=4)
def _index(path: str, kind: str, modified: int, size: int) -> list[dict[str, str]]:
    return load_offerings(Path(path)) if kind == "courses" else directory.load(Path(path))


@router.get("/api/plan")
def read(request: Request) -> dict[str, Any]:
    """Read private enrolments, assessments and selected announcements"""
    return plan.load(workspace(request).state)


@router.post("/api/plan")
def save(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Reject stale edits before publishing a private plan"""
    return plan.save(workspace(request).state, data)


@router.get("/api/search")
def search(
    request: Request,
    kind: str = "courses",
    q: str = "",
    offset: int = 0,
    category: str = "",
    channel: str = "",
) -> dict[str, Any]:
    """Search bounded pages of saved course or club records"""
    if kind not in {"courses", "clubs"} or offset < 0:
        raise MiniError("Search courses or clubs with a nonnegative offset")
    topics = terms(q, kind)
    context = workspace(request)
    path = context.courses if kind == "courses" else context.clubs
    warning = directory.ensure(path) if kind == "clubs" else ""
    if not path.is_file():
        return {"rows": [], "total": 0}
    info = path.stat()
    rows = _index(str(path.resolve()), kind, info.st_mtime_ns, info.st_size)
    if channel not in {"", "instagram", "facebook", "discord", "website"}:
        raise MiniError("Choose a listed social channel")
    matches = [
        row
        for row in rows
        if contains(" ".join(row.values()), topics)
        and (not category or row.get("interests") == category)
        and (not channel or row.get(channel))
    ]
    return {
        "rows": matches[offset : offset + 40],
        "total": len(matches),
        "categories": sorted({row["interests"] for row in rows if row.get("interests")}),
        "warning": warning,
        "updated": info.st_mtime,
    }


@router.get("/api/club")
def club(request: Request, url: str) -> dict[str, Any]:
    """Bring the selected public club profile into Clubby without student data entry"""
    return directory.profile(workspace(request).clubs, url)


@router.get("/api/clubs/feed")
def club_feed(request: Request) -> dict[str, Any]:
    """Read upcoming public club announcements through the shared bounded snapshot"""
    return sources.feed(workspace(request).clubs.with_name("feed.json"))


@router.get("/api/course")
def course(code: str) -> dict[str, Any]:
    """Read one selected course and its actual published profile links"""
    return course_info(code)


@router.post("/api/profile")
def assessments(data: dict[str, Any]) -> dict[str, Any]:
    """Propose assessments for review from official or saved profile HTML"""
    html = data.get("html")
    if html is None:
        html = profile.read(plan.link(data.get("url", "")))
    return profile.parse(plan.text(html, 8 * 1024**2))


@router.post("/api/marks")
def calculate(data: dict[str, Any]) -> dict[str, Any]:
    """Compute transparent course-mark scenarios from validated inputs"""
    current = plan.validate(data.get("plan"))
    estimate = plan.number(data.get("estimate", 75))
    return {
        course["id"]: marks.calculate(
            course,
            [item for item in current["assessments"] if item["course"] == course["id"]],
            target=current["settings"]["target"],
            estimate=estimate,
        )
        for course in current["courses"]
    }


@router.post("/api/sync")
def sync(request: Request) -> dict[str, Any]:
    """Replace the complete public Rubric feed while retaining personal selections"""
    path = workspace(request).state
    current = plan.load(path)
    incoming = sources.rubric()
    current["announcements"] = sources.merge(
        current["announcements"], incoming, replace_source="Rubric"
    )
    return plan.save(path, current)


@router.post("/api/import")
def imported(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Merge authorised Discord or social exports with stable source identities"""
    path = workspace(request).state
    current = plan.load(path)
    incoming = sources.imported(
        plan.text(data.get("text", ""), 8 * 1024**2), plan.text(data.get("kind", "social"), 20)
    )
    current["announcements"] = sources.merge(current["announcements"], incoming)
    return plan.save(path, current)


@router.post("/api/discord")
def discord(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Refresh only the selected authorised servers without exposing their token"""
    guilds = list(
        dict.fromkeys(
            item.strip()
            for item in plan.text(data.get("guilds", ""), 2000).split(",")
            if item.strip()
        )
    )
    if len(guilds) > 50:
        raise MiniError("Refresh at most 50 Discord servers at a time")
    path = workspace(request).state
    current = plan.load(path)
    incoming = sources.scheduled(events.collect(guilds=guilds))
    prefixes = tuple(f"discord-{guild}-" for guild in guilds)
    merged = sources.merge(current["announcements"], incoming)
    active = {item["id"] for item in incoming}
    current["announcements"] = [
        item for item in merged if not item["id"].startswith(prefixes) or item["id"] in active
    ]
    return plan.save(path, current)


@router.post("/api/social")
def posts(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Merge a recent authorised feed without treating absent older posts as deleted"""
    path = workspace(request).state
    current = plan.load(path)
    club_url = plan.link(data.get("club_url", ""))
    rows = social.collect(
        plan.text(data.get("provider", ""), 20),
        plan.text(data.get("account", ""), 32),
        club=plan.text(data.get("club", ""), 300),
    )
    incoming = sources.social(rows)
    for item in incoming:
        item["club_url"] = club_url
    current["announcements"] = sources.merge(current["announcements"], incoming)
    return plan.save(path, current)


@router.post("/api/catalogues")
def refresh(request: Request, data: dict[str, Any]) -> dict[str, int]:
    """Refresh selected catalogues atomically without refetching enrolled profiles"""
    context = workspace(request)
    kind = data.get("kind")
    if kind == "courses":
        count = export_links(context.courses)
        course_info.cache_clear()
    elif kind == "clubs":
        count = directory.refresh(context.clubs)
    elif kind == "club-details":
        count = directory.enrich(context.clubs)
    else:
        raise MiniError("Refresh courses or clubs")
    return {"count": count}


@router.get("/api/backup")
def backup(request: Request) -> dict[str, Any]:
    """Download the editable private plan without exposing credentials"""
    return plan.load(workspace(request).state)
