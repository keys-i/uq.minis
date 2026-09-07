"""Capture Microsoft Forms session values through a user-operated browser"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Annotated, Literal
from urllib.parse import unquote, urlsplit

import typer
from dotenv import set_key
from rich.console import Console

from uq_minis.helper.common import MiniError

if TYPE_CHECKING:
    from uq_minis.helper.forms import FormProfile

_HOST = "forms.cloud.microsoft"
_AUTH_COOKIES = {"AADAuth.forms", "OIDCAuth.forms"}
CONSOLE = Console()


def _same_target(url: str, profile: FormProfile) -> bool:
    """Check whether a request belongs to the configured HTTPS form"""
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
    """Identify Forms response submissions that the auth window must block"""
    parsed = urlsplit(url)
    return (
        method.upper() == "POST"
        and parsed.scheme == "https"
        and parsed.hostname == _HOST
        and parsed.path.casefold().startswith("/formapi/")
        and parsed.path.casefold().rstrip("/").endswith("/responses")
    )


def _capture(request: object, profile: FormProfile, values: dict[str, str]) -> None:
    """Capture session headers only from the configured form"""
    if not _same_target(request.url, profile):
        return
    headers = request.all_headers()
    for name, header in (
        (profile.verification_token_env, "__requestverificationtoken"),
        (profile.session_id_env, "x-usersessionid"),
        (profile.muid_env, "x-ms-form-muid"),
    ):
        if value := headers.get(header):
            values[name] = value


def _guard(route: object, profile: FormProfile, values: dict[str, str]) -> None:
    """Capture matching headers and block Forms response submissions"""
    request = route.request
    _capture(request, profile, values)
    if _response_post(str(request.url), str(request.method), profile):
        route.abort()
    else:
        route.continue_()


def _cookie_header(cookies: list[object]) -> str:
    """Join Forms cookies only when an authentication cookie is present"""
    items = [
        (cookie["name"], cookie["value"])
        for cookie in cookies
        if isinstance(cookie, Mapping) and cookie.get("domain", "").lstrip(".") == _HOST
    ]
    names = {name for name, value in items if value}
    if not names & _AUTH_COOKIES:
        return ""
    return "; ".join(f"{name}={value}" for name, value in items)


def _complete(values: Mapping[str, str], profile: FormProfile) -> bool:
    """Check whether all four required credential values have been captured"""
    return all(
        values.get(name)
        for name in (
            profile.cookie_env,
            profile.verification_token_env,
            profile.session_id_env,
            profile.muid_env,
        )
    )


def _write_env(path: Path, values: Mapping[str, str], *, force: bool) -> None:
    """Save credentials atomically and reject accidental overwrites"""
    if path.is_symlink():
        raise MiniError("Credential output must not be a symlink")
    if path.exists() and not force:
        raise MiniError(f"Refusing to overwrite {path}; pass --force")
    if any(
        not value or any(ord(char) < 32 or ord(char) == 127 for char in value)
        for value in values.values()
    ):
        raise MiniError("Credential values must be nonempty and contain no control characters")
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        if path.exists():
            temporary.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        for name, value in values.items():
            set_key(str(temporary), name, value, quote_mode="always")
        temporary.chmod(0o600)
        if force:
            temporary.replace(path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _launch(playwright: object, browser: str) -> object:
    """Open the requested browser with a visible window"""
    name, channel = {"chrome": ("chromium", "chrome"), "edge": ("chromium", "msedge")}.get(
        browser, (browser, None)
    )
    engine = getattr(playwright, name)
    options = {"headless": False}
    if channel:
        options["channel"] = channel
    return engine.launch(**options)


def capture(profile: FormProfile, *, browser: str, timeout: int) -> dict[str, str]:
    """Open the form for sign-in and capture its outgoing session credentials"""
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
                "https://forms.cloud.microsoft/**", lambda route: _guard(route, profile, values)
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


app = typer.Typer(
    add_completion=False, rich_markup_mode="rich", pretty_exceptions_show_locals=False
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
        Path | None,
        typer.Option(help="Custom Microsoft Forms profile."),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Refresh credentials in an existing file.")
    ] = False,
    no_input: Annotated[
        bool, typer.Option("--no-input", help="Reject browser sign-in for unattended runs.")
    ] = False,
) -> None:
    """Sign in through a browser and save Forms credentials"""
    from uq_minis.helper.forms import load_form_profile

    if no_input:
        raise typer.BadParameter(
            "auth requires browser sign-in; use saved .env credentials for unattended submissions"
        )
    output = output.expanduser()
    try:
        if output.is_symlink() or (output.exists() and not force):
            raise MiniError("Output already exists or is a symlink; choose another path or --force")
        profile = load_form_profile(form_profile)
        values = capture(profile, browser=browser, timeout=timeout)
        _write_env(output, values, force=force)
    except (MiniError, OSError, ValueError) as exc:
        Console(stderr=True).print(f"auth: {exc}", style="red", markup=False)
        raise typer.Exit(2) from exc
    CONSOLE.print(f"Saved Forms credentials to {output}", style="green", markup=False)


def main(argv: list[str] | None = None) -> None:
    """Run the auth mini"""
    app(args=argv, prog_name="mini --tool auth")


if __name__ == "__main__":
    main()
