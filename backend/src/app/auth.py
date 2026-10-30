"""Explicit browser sign-in using the established private Forms session flow

These routes connect Forms credentials after the person explicitly starts
the capture workflow. They are separate from the short-lived university
access session and never return credential values to the frontend
"""

from pathlib import Path

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from uq_minis.app.core import page, value
from uq_minis.core.common import MiniError
from uq_minis.core.forms import load_form_profile
from uq_minis.core.paths import STATE

router = APIRouter()


def _show(request: Request, **results: object) -> dict[str, object]:
    return page(
        request,
        "auth",
        fields=[
            {
                "name": "browser",
                "label": "Sign-in browser",
                "type": "select",
                "options": [
                    (name, name.title())
                    for name in ("chromium", "chrome", "edge", "firefox", "webkit")
                ],
            },
            {
                "name": "output",
                "label": "Private session file",
                "value": str(STATE / "auth" / ".env"),
            },
            {"name": "force", "label": "Refresh the intended existing session", "type": "checkbox"},
            {
                "name": "timeout",
                "label": "Sign-in window · seconds",
                "type": "range",
                "value": 300,
                "min": 30,
                "max": 1800,
                "step": 30,
                "group": "Sign-in settings",
            },
            {
                "name": "form_profile",
                "label": "Custom form profile path · optional",
                "group": "Sign-in settings",
            },
        ],
        submit="Open secure sign-in",
        note="A separate browser window opens on this computer. Complete account selection and MFA there. Passwords and tokens never appear in this page; sign-in does not submit an event booking",
        **results,
    )


@router.get("/api/minis/auth")
def home(request: Request) -> dict[str, object]:
    """Offer a human-controlled sign-in window"""
    return _show(request)


def _process(request: Request, form: FormData) -> dict[str, object]:
    from uq_minis.minis import auth

    output = Path(value(form, "output", str(STATE / "auth" / ".env"))).expanduser()
    force = value(form, "force") == "on"
    timeout = int(value(form, "timeout", "300"))
    if not 30 <= timeout <= 1800:
        raise MiniError("Allow between 30 and 1800 seconds for sign-in")
    if output.is_symlink() or output.exists() and not force:
        raise MiniError("A session already exists; select refresh to replace that intended session")
    auth.write_env(
        output,
        auth.capture(
            load_form_profile(Path(value(form, "form_profile")))
            if value(form, "form_profile")
            else load_form_profile(),
            browser=value(form, "browser", "chromium"),
            timeout=timeout,
        ),
        force=force,
    )
    return _show(
        request, result="Forms sign-in saved privately. You can return to your event booking"
    )


@router.post("/api/minis/auth")
async def submit(request: Request) -> dict[str, object]:
    """Start sign-in only after the person requests it"""
    async with request.form() as form:
        return await run_in_threadpool(_process, request, form)
