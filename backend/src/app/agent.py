"""Browser booking follow-up with explicit authority for email processing

Mailbox reads and mutations run only through an explicitly selected action
Blocking work stays outside the request loop and uses the persistent worker
state, transport checks and submission safeguards
"""

from pathlib import Path

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from uq_minis.app.core import page, value
from uq_minis.core.common import MiniError
from uq_minis.core.paths import STATE
from uq_minis.worker.mail import RECIPIENTS, RETURN_TO

router = APIRouter()


def _show(request: Request, **results: object) -> dict[str, object]:
    return page(
        request,
        "agent",
        fields=[
            {
                "name": "action",
                "label": "Booking follow-up",
                "type": "select",
                "options": [
                    ("status", "Show booking status"),
                    ("login", "Sign into Outlook"),
                    ("watch", "Register an event and its risk reply"),
                    ("poll", "Process a mailbox pass"),
                    ("stop", "Stop watching an event"),
                    ("retry-send", "Allow a checked, unsent reply to retry"),
                ],
            },
            {"name": "mailbox", "label": "Outlook mailbox", "type": "email"},
            {
                "name": "username",
                "label": "Sign-in account · if different from the mailbox",
                "type": "email",
                "group": "Mailbox settings",
            },
            {
                "name": "backend",
                "label": "Connection",
                "type": "select",
                "options": [("browser", "Outlook browser"), ("graph", "Microsoft Graph")],
                "group": "Mailbox settings",
            },
            {
                "name": "client_id",
                "label": "Microsoft app ID · Graph only",
                "group": "Mailbox settings",
            },
            {
                "name": "tenant_id",
                "label": "Microsoft tenant ID · Graph only",
                "group": "Mailbox settings",
            },
            {
                "name": "state_dir",
                "label": "Private mailbox state",
                "value": str(STATE / "agent"),
                "group": "Mailbox settings",
            },
            {
                "name": "since",
                "label": "Look for replies since · ISO timestamp with time zone",
                "group": "Mailbox settings",
            },
            {"name": "source", "label": "Event TOML path"},
            {"name": "event_id", "label": "Exact booking reference ID"},
            {"name": "attachment", "label": "Approved risk assessment path · optional"},
            {
                "name": "recipient",
                "label": "Risk assessment recipient",
                "type": "select",
                "value": RETURN_TO,
                "options": [(address, address) for address in RECIPIENTS],
            },
            {
                "name": "confirm",
                "label": "I authorise this event's automatic risk reply or processing of the configured replies",
                "type": "checkbox",
            },
            {
                "name": "confirm_not_sent",
                "label": "I checked Outlook Sent Items and this reply was not sent",
                "type": "checkbox",
                "when": {"action": ["retry-send"]},
            },
        ],
        note="Status omits email text. Signing in does not authorise email. Registering a watch or processing mail can send the configured reply, and requires the checkbox above",
        **results,
    )


@router.get("/api/minis/agent")
def home(request: Request) -> dict[str, object]:
    """Show an explicit mailbox workflow without reading mail automatically"""
    return _show(request)


def _process(request: Request, form: FormData) -> dict[str, object]:
    from uq_minis.minis import agent

    action = value(form, "action", "status")
    if action not in {"status", "login", "watch", "poll", "stop", "retry-send"}:
        raise MiniError("Choose a listed booking action")
    if action in {"watch", "poll"} and value(form, "confirm") != "on":
        raise MiniError("Explicitly authorise the configured event replies before continuing")
    state = Path(value(form, "state_dir", str(STATE / "agent"))).expanduser()
    if action == "login":
        agent.login(
            mailbox=value(form, "mailbox"),
            username=value(form, "username") or None,
            backend=value(form, "backend", "browser"),
            client_id=value(form, "client_id") or None,
            tenant_id=value(form, "tenant_id") or None,
            state_dir=state,
        )
    elif action == "watch":
        attachment = value(form, "attachment")
        agent.watch(
            Path(value(form, "source")),
            event_id=value(form, "event_id"),
            attachment=Path(attachment) if attachment else None,
            recipient=value(form, "recipient", RETURN_TO),
            since=value(form, "since") or None,
            state_dir=state,
        )
    elif action == "poll":
        agent.poll(state_dir=state)
    elif action == "stop":
        agent.stop(value(form, "event_id"), state_dir=state)
    elif action == "retry-send":
        agent.retry_send(
            value(form, "event_id"),
            confirm_not_sent=value(form, "confirm_not_sent") == "on",
            state_dir=state,
        )
    rows = [
        {key: row.get(key, "") for key in ("event_id", "title", "state", "outcome", "error")}
        for row in agent.status(state_dir=state)
    ]
    return _show(
        request,
        result="Booking status checked" if action == "status" else "Requested action completed",
        rows=rows,
        columns=["event_id", "title", "state", "outcome", "error"],
    )


@router.post("/api/minis/agent")
async def submit(request: Request) -> dict[str, object]:
    """Run the selected mailbox action in a worker rather than the event loop"""
    async with request.form() as form:
        return await run_in_threadpool(_process, request, form)
