"""Keep a remembered YouTube browser connection private to its workspace

Only provider cookies are retained, never form values or screenshots
The connection may still be rejected by Google or YouTube's download checks
"""

from __future__ import annotations

import math
import os
from http.cookiejar import Cookie, MozillaCookieJar
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import urlsplit

from uq_minis.core.common import MiniError
from uq_minis.core.paths import STATE

ROOT = STATE / "timey/youtube"
COOKIES = ROOT / "cookies.txt"
LOGIN = "https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fwww.youtube.com%2F"
HOSTS = frozenset({
    "accounts.google.com",
    "www.youtube.com",
    "youtube.com",
    "consent.youtube.com",
    "consent.google.com",
    "www.google.com",
    "ssl.gstatic.com",
    "www.gstatic.com",
    "fonts.gstatic.com",
    "fonts.googleapis.com",
    "lh3.googleusercontent.com",
    "yt3.ggpht.com",
    "www.recaptcha.net",
    "recaptcha.net",
})


def allowed(url: str) -> bool:
    """Permit only the fixed HTTPS destinations needed by Google's real sign-in"""
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in HOSTS
            and parsed.port in {None, 443}
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def _safe() -> None:
    """Reject links anywhere above the owned provider state"""
    if any(path.is_symlink() for path in (COOKIES, *COOKIES.parents)):
        raise MiniError("The YouTube connection must use private files rather than links")


def cookiefile() -> Path | None:
    """Return only a bounded private regular cookie file with an unexpired session"""
    _safe()
    if not COOKIES.exists():
        return None
    if (
        not COOKIES.is_file()
        or COOKIES.stat().st_size > 262144
        or os.name == "posix"
        and COOKIES.stat().st_mode & 0o077
    ):
        raise MiniError("Reconnect YouTube to repair its private connection file")
    try:
        jar = MozillaCookieJar(str(COOKIES))
        jar.load(ignore_discard=True)
    except (OSError, ValueError) as exc:
        raise MiniError("Reconnect YouTube; the saved connection could not be read") from exc
    return (
        COOKIES
        if any(
            cookie.name in {"SID", "__Secure-1PSID", "LOGIN_INFO"}
            and cookie.domain.lstrip(".") in {"google.com", "youtube.com"}
            for cookie in jar
        )
        else None
    )


def require() -> Path:
    """Require the workspace's saved Google session for a YouTube action"""
    path = cookiefile()
    if path is None:
        raise MiniError("Connect Google before searching or using YouTube in Timey")
    return path


def authenticated(cookies: list[dict[str, Any]]) -> bool:
    """Recognise only the provider session cookies used by saved connections"""
    return any(
        item.get("name") in {"SID", "__Secure-1PSID", "LOGIN_INFO"}
        and str(item.get("domain", "")).lstrip(".") in {"google.com", "youtube.com"}
        for item in cookies
    )


def save(cookies: list[dict[str, Any]]) -> None:
    """Atomically retain only bounded provider cookies, with owner-only permissions"""
    _safe()
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if len(cookies) > 256:
        raise MiniError("The YouTube session is too large; cancel and try again")
    jar = MozillaCookieJar()
    for item in cookies:
        domain = str(item.get("domain", ""))
        expires = item.get("expires", -1)
        if domain.lstrip(".") not in {
            "google.com",
            "youtube.com",
            "accounts.google.com",
            "www.youtube.com",
        }:
            continue
        if (
            not item.get("secure")
            or type(expires) not in {int, float}
            or not math.isfinite(expires)
        ):
            continue
        name, value = item.get("name"), item.get("value")
        if (
            not isinstance(name, str)
            or not isinstance(value, str)
            or len(name) + len(value) > 8192
            or any(c in name + value + domain for c in "\r\n\t")
        ):
            raise MiniError("YouTube returned an unsupported session cookie")
        jar.set_cookie(
            Cookie(
                0,
                name,
                value,
                None,
                False,
                domain,
                True,
                domain.startswith("."),
                "/",
                True,
                True,
                int(expires) if expires > 0 else None,
                expires <= 0,
                None,
                None,
                {"HttpOnly": ""} if item.get("httpOnly") else {},
            )
        )
    jar.clear_expired_cookies()
    if not any(
        cookie.name in {"SID", "__Secure-1PSID", "LOGIN_INFO"}
        and cookie.domain.lstrip(".") in {"google.com", "youtube.com"}
        for cookie in jar
    ):
        raise MiniError("Finish Google's sign-in before saving the connection")
    with NamedTemporaryFile(prefix=".cookies-", dir=ROOT, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        jar.save(str(temporary), ignore_discard=True, ignore_expires=True)
        temporary.chmod(0o600)
        temporary.replace(COOKIES)
    finally:
        temporary.unlink(missing_ok=True)


def disconnect() -> None:
    """Forget only this workspace's remembered provider connection"""
    _safe()
    COOKIES.unlink(missing_ok=True)
