"""Course research endpoints shared with Planny's terminal workflows

Discovery reads bounded snapshots and fetches selected official details on
demand. Translation, independent feedback and official SECaT retain their
distinct data rules rather than fabricating missing scores or eligibility
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from uq_minis.app.core import workspace
from uq_minis.app.planny import course_info
from uq_minis.core import translate
from uq_minis.core.common import MiniError
from uq_minis.minis.planny import plan, readiness, research
from uq_minis.minis.scrappy import trail

router = APIRouter()


@router.post("/api/translate")
def translated(data: dict[str, Any]) -> dict[str, str]:
    """Translate bounded public text while keeping its original with the caller"""
    target = plan.text(data.get("target"), 20)
    source = plan.text(data.get("source", "auto"), 20)
    try:
        text = translate.text(plan.text(data.get("text"), 4000), target, source)
    except translate.Unavailable as exc:
        raise HTTPException(
            exc.status, str(exc), headers={"Retry-After": str(exc.retry)} if exc.retry else None
        ) from exc
    return {
        "text": text,
        "language": target,
        "provider": "Microsoft Translator",
    }


@router.get("/api/research")
def search(
    request: Request,
    q: str = "",
    faculty: str = "",
    metric: str = "",
    order: str = "",
    minimum: int = 1,
    offset: int = 0,
    target: str = "course",
    semester: str = "auto",
) -> dict[str, Any]:
    """Search saved public reviews without repeatedly calling upstream systems"""
    context = workspace(request)
    student = plan.load(context.state)["settings"]
    return research.search(
        research.load(context.state.with_name("research.json")),
        q,
        faculty=faculty,
        metric=metric,
        order=order,
        minimum=minimum,
        offset=offset,
        target=target,
        semester=semester,
        completed=student.get("completed", []),
        skills=student.get("skills", ""),
    )


@router.post("/api/research/refresh")
def refresh(request: Request) -> dict[str, Any]:
    """Refresh at most one complete public snapshot per day"""
    data = research.refresh(workspace(request).state.with_name("research.json"))
    return {
        "courses": len(data["courses"]),
        "reviews": len(data["reviews"]),
        "updated": data["updated"],
    }


@router.post("/api/research/catalogue")
def catalogue(request: Request) -> dict[str, Any]:
    """Crawl the official UQ index without replacing independent course feedback"""
    data = research.catalogue(workspace(request).state.with_name("research.json"))
    return {"courses": len(data["courses"]), "updated": data["catalogue_updated"]}


@router.post("/api/research/feedback")
def feedback(request: Request) -> dict[str, int]:
    """Expand public course feedback at most weekly without replacing saved reviews"""
    data = research.expand(workspace(request).state.with_name("research.json"))
    return {"courses": len(data["feedback"])}


@router.get("/api/research/course")
def course(request: Request, code: str) -> dict[str, Any]:
    """Show the selected course's provenance and current prerequisite checks"""
    context = workspace(request)
    data = research.course(research.load(context.state.with_name("research.json")), code)
    saved: dict[str, Any] = data["course"] or {}
    info: dict[str, Any]
    try:
        info = course_info(code)
        research.remember(
            context.state.with_name("research.json"), code, info["details"], info["offerings"]
        )
    except MiniError as exc:
        info = {
            "details": saved.get("requirements", {}),
            "offerings": saved.get("offerings", []),
            "url": f"https://programs-courses.uq.edu.au/course.html?course_code={code}",
            "official_error": str(exc),
        }
    student = plan.load(context.state)["settings"]
    return {
        **data,
        **info,
        "readiness": readiness.check(
            info["details"], student.get("completed", []), student.get("skills", "")
        ),
    }


@router.get("/api/research/professor")
def professor(request: Request, id: str) -> dict[str, Any]:
    """Show attributable teacher reviews without publishing a new forum"""
    data = research.load(workspace(request).state.with_name("research.json"))
    rows = [
        row
        for row in data["reviews"]
        if row["target"] == "professor" and (row["professor_id"] or row["professor"]) == id
    ]
    if not rows:
        raise MiniError("No saved reviews for that professor")
    return {
        "name": rows[0]["professor"],
        "faculty": rows[0]["faculty"],
        "reviews": rows[:200],
        "metrics": research.metrics(rows),
    }


@router.get("/api/research/trail")
def prerequisites(request: Request, code: str) -> dict[str, Any]:
    """Expand prerequisite branches independently from the initial course view"""
    courses = research.load(workspace(request).state.with_name("research.json"))["courses"]
    return trail.build(code, courses, course_info)


@router.post("/api/research/secat")
def secat(request: Request, data: dict[str, Any]) -> dict[str, int]:
    """Import an authorised saved official chart into the private research snapshot"""
    return {
        "count": research.import_secat(
            workspace(request).state.with_name("research.json"),
            plan.text(data.get("html"), 8 * 1024**2),
        )
    }
