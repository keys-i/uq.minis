"""Browser capture for Microsoft Forms credentials."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from rich.console import Console

from uq_minis.helper.common import MiniError

if TYPE_CHECKING:
    from uq_minis.helper.forms import FormProfile

_HOST = "forms.cloud.microsoft"
_AUTH_COOKIES = {"AADAuth.forms", "OIDCAuth.forms"}
CONSOLE = Console()


def _same_target(url: str, profile: FormProfile) -> bool:
    """Check whether a request belongs to the configured HTTPS form."""
    candidate, target = urlsplit(url), urlsplit(profile.endpoint)
    return (
        candidate.scheme == "https"
        and candidate.hostname == _HOST
        and candidate.port in {None, 443}
        and candidate.username is None
        and unquote(candidate.path).startswith(
            unquote(target.path).removesuffix("/responses") + "/"
        )
    )


def _response_post(url: str, method: str, profile: FormProfile) -> bool:
    """Identify Forms response submissions that the auth window must block."""
    parsed = urlsplit(url)
    return (
        method.upper() == "POST"
        and parsed.scheme == "https"
        and parsed.hostname == _HOST
        and parsed.path.casefold().startswith("/formapi/")
        and parsed.path.casefold().rstrip("/").endswith("/responses")
    )


def _capture(request: object, profile: FormProfile, values: dict[str, str]) -> None:
    """Capture session headers only from the configured form."""
    if not _same_target(request.url, profile):
        return
    for name, header in (
        (profile.verification_token_env, "__requestverificationtoken"),
        (profile.session_id_env, "x-usersessionid"),
        (profile.muid_env, "x-ms-form-muid"),
    ):
        if value := request.all_headers().get(header):
            values[name] = value


def _guard(route: object, profile: FormProfile, values: dict[str, str]) -> None:
    """Capture matching headers and block Forms response submissions."""
    request = route.request
    _capture(request, profile, values)
    if _response_post(str(request.url), str(request.method), profile):
        route.abort()
    else:
        route.continue_()


def _cookie_header(cookies: list[object]) -> str:
    """Join Forms cookies only when an authentication cookie is present."""
    items = [
        (cookie["name"], cookie["value"])
        for cookie in cookies
        if isinstance(cookie, Mapping) and cookie.get("domain", "").lstrip(".") == _HOST
    ]
    if not {name for name, value in items if value} & _AUTH_COOKIES:
        return ""
    return "; ".join(f"{name}={value}" for name, value in items)


def _complete(values: Mapping[str, str], profile: FormProfile) -> bool:
    """Check whether all four required credential values have been captured."""
    return all(
        values.get(name)
        for name in (
            profile.cookie_env,
            profile.verification_token_env,
            profile.session_id_env,
            profile.muid_env,
        )
    )


def _launch(playwright: object, browser: str) -> object:
    """Open the requested browser with a visible window."""
    name, channel = {
        "chrome": ("chromium", "chrome"),
        "edge": ("chromium", "msedge"),
    }.get(browser, (browser, None))
    options = {"headless": False}
    if channel:
        options["channel"] = channel
    return getattr(playwright, name).launch(**options)


def capture(profile: FormProfile, *, browser: str, timeout: int) -> dict[str, str]:
    """Open the form for sign-in and capture its outgoing session credentials."""
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise MiniError(
            "Install browser support: uv run --extra auth playwright install chromium\n"
            "Then run: uv run --extra auth mini --tool auth"
        ) from exc
    values: dict[str, str] = {}
    try:
        with sync_playwright() as playwright:
            instance = _launch(playwright, browser)
            context = instance.new_context(service_workers="block")
            page = context.new_page()
            context.route(
                "https://forms.cloud.microsoft/**",
                lambda route: _guard(route, profile, values),
            )
            page.goto(profile.referer, wait_until="domcontentloaded")
            CONSOLE.print(
                "Sign in in the browser. This window blocks form submissions. "
                "If credentials are not captured on load, complete the form and click Submit once.",
                style="cyan",
            )
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                values[profile.cookie_env] = _cookie_header(context.cookies(profile.endpoint))
                if not values[profile.cookie_env]:
                    values.pop(profile.cookie_env, None)
                if _complete(values, profile):
                    context.close()
                    instance.close()
                    return values
                page.wait_for_timeout(250)
            context.close()
            instance.close()
    except Error as exc:
        raise MiniError(f"Could not start {browser}: {exc}") from exc
    raise MiniError(
        "Timed out before Forms credentials were captured; sign in and click Submit once"
    )
