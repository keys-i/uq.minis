"""Buzzy's live calendar subscription using the shared student plan

The subscription derives stable events from saved courses, deadlines and
followed clubs. Calendar reads preserve the private plan and leave official
dates separate from the student’s earlier personal targets
"""

from fastapi import APIRouter, Request, Response

from uq_minis.app.core import workspace
from uq_minis.minis import buzzy
from uq_minis.minis.planny import plan, sources

router = APIRouter()


@router.get("/calendar.ics")
def feed(request: Request) -> Response:
    """Serve a stable calendar subscription while the local backend is running"""
    context = workspace(request)
    current = sources.calendar(plan.load(context.state), context.clubs.with_name("feed.json"))
    return Response(buzzy.render(current), media_type="text/calendar")
