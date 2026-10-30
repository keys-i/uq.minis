"""Render UQ sign-in and verify access without retaining portal credentials

The web application presents its own credential form and forwards submitted
values to UQ's live controls in a private browser. Duo and other interactive
steps retain their original pixels and semantic controls

Only UQ authentication and Duo HTTPS destinations are reachable from this
window. Successful access comes from the protected UQ session page, never
from a value supplied by the frontend
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from html.parser import HTMLParser
from time import monotonic
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

from uq_minis.core.common import MiniError
from uq_minis.core.window import Window as Transport
from uq_minis.core.window import window as transport

if TYPE_CHECKING:
    from playwright.async_api import Page

PORTAL = "https://auth.uq.edu.au/idp/module.php/core/authenticate.php?as=uq"


def allowed(url: str) -> bool:
    """Restrict the remote window to HTTPS UQ authentication and Duo"""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        return (
            parsed.scheme == "https"
            and parsed.port in {None, 443}
            and not parsed.username
            and not parsed.password
            and (host == "auth.uq.edu.au" or host.endswith(".duosecurity.com"))
        )
    except ValueError:
        return False


def account(url: str, attributes: str, logout: bool = False) -> str:
    """Accept identity only from UQ's protected session confirmation

    Args:
        url: Final URL of a response fetched through the private portal context
        attributes: Visible text from that response, limited to 64 KiB
        logout: Whether its parsed HTML includes a protected-session logout link

    Returns:
        Normalised UQ email when URL and confirmation agree, otherwise empty text

    The caller must fetch this page itself rather than accept frontend claims
    """
    if not allowed(url):
        return ""
    parsed = urlsplit(url)
    confirmed = "you have successfully signed into the uq authenticate system" in " ".join(
        attributes.casefold().split()
    )
    if (
        parsed.hostname != "auth.uq.edu.au"
        or parsed.path != "/idp/module.php/core/authenticate.php"
        or parse_qs(parsed.query).get("as") != ["uq"]
        or not (confirmed or logout)
        or len(attributes) > 65536
    ):
        return ""
    match = re.search(
        r"(?<![\w@.+-])([a-z0-9][a-z0-9._+-]{0,63}@(?:student\.uq\.edu\.au|uq\.edu\.au|uqconnect\.edu\.au))(?![\w.-])",
        attributes,
        re.IGNORECASE,
    )
    return match[1].casefold() if match else ""


class _Status(HTMLParser):
    """Read confirmation text without accepting scripts or a password form"""

    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.hidden = 0
        self.password = False
        self.logout = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Inspect only sign-in markers; never collect input values"""
        values = dict(attrs)
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "input" and values.get("type") == "password":
            self.password = True
        if tag == "a" and "logout" in (values.get("href") or ""):
            self.logout = True

    def handle_endtag(self, tag: str) -> None:
        """Resume visible text after non-content elements"""
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        """Keep text nodes separate so adjacent labels do not merge"""
        if not self.hidden:
            self.text.append(data)

    def user(self, url: str, html: str) -> str:
        """Reject oversized pages and login forms before reading their text"""
        if len(html) > 65536:
            return ""
        self.feed(html)
        return "" if self.password else account(url, "\n".join(self.text), self.logout)


class Window(Transport):
    """Verify UQ access while retaining the shared bounded browser transport"""

    def __init__(self, page: Page) -> None:
        """Restrict this window to UQ and Duo without storing credentials"""
        super().__init__(page, allowed, "UQ", "auth.uq.edu.au")
        self.checked = 0.0

    async def user(self) -> str:
        """Check shared portal cookies independently of MFA redirects or markup layout"""
        if monotonic() < self.checked:
            return ""
        self.checked = monotonic() + 2
        response = await self.page.context.request.get(PORTAL, max_redirects=0, timeout=5000)
        try:
            if response.status == 200:
                return _Status().user(response.url, await response.text())
            if response.status == 429 or response.status >= 500:
                raise MiniError("UQ's sign-in service is busy; cancel and try again shortly")
            return ""
        finally:
            await response.dispose()


@asynccontextmanager
async def window() -> AsyncGenerator[Window]:
    """Close the isolated UQ browser after confirmation, cancellation or failure"""
    async with transport(PORTAL, allowed, "UQ") as browser:
        yield Window(browser.page)
