"""Bounded GET retries and validation for UQ catalogue URLs."""

import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from uq_minis.helper.common import MiniError

BASE_URL = "https://programs-courses.uq.edu.au"
CODE = re.compile(r"[A-Z]{4}\d{4}[A-Z]?")


class CatalogueUnavailable(MiniError):
    """Stop a batch when UQ denies access or requests a longer pause."""


def catalogue_url(url: str, *, course: bool = False) -> str:
    """Reject foreign hosts, credentials, ports and paths before making a request."""
    try:
        parsed = urlsplit(url.strip())
        valid = (
            parsed.scheme == "https"
            and parsed.hostname == "programs-courses.uq.edu.au"
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and parsed.path in (("/course.html",) if course else ("/course.html", "/search.html"))
        )
        query = parse_qsl(parsed.query, keep_blank_values=True)
        if parsed.path == "/course.html":
            codes = [value.upper() for key, value in query if key == "course_code"]
            valid = valid and len(codes) == 1 and bool(CODE.fullmatch(codes[0]))
            query = [
                (key, value.upper() if key == "course_code" else value) for key, value in query
            ]
        if valid:
            return urlunsplit(
                ("https", "programs-courses.uq.edu.au", parsed.path, urlencode(sorted(query)), "")
            )
    except ValueError:
        pass
    raise MiniError(
        "Offering URLs must be trusted UQ HTTPS catalogue URLs with a valid course code"
    )


def _delay(value: str, attempt: int) -> float:
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            seconds = 0.5 * 2**attempt
    if not seconds <= 60:
        raise CatalogueUnavailable("UQ requested a longer pause; try again later")
    return max(0, seconds)


def fetch(url: str, *, client: httpx.Client | None = None) -> str:
    """Retry transient GET failures twice and validate every redirect before following it."""
    url = catalogue_url(url)
    if client is None:
        with httpx.Client(timeout=30, follow_redirects=False) as connection:
            return fetch(url, client=connection)
    for _ in range(6):
        for attempt in range(3):
            try:
                response = client.get(url, follow_redirects=False)
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise MiniError(f"Cannot fetch {url}: {type(exc).__name__}") from exc
                time.sleep(0.5 * 2**attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(_delay(response.headers.get("Retry-After", ""), attempt))
                continue
            break
        if response.is_redirect:
            target = response.headers.get("Location")
            if not target:
                raise MiniError(f"UQ returned a redirect without a location: {url}")
            url = catalogue_url(urljoin(url, target))
            continue
        if response.status_code in (401, 403, 429):
            raise CatalogueUnavailable(
                f"UQ returned HTTP {response.status_code}; stopped the batch. Try again later"
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MiniError(f"Cannot fetch {url}: HTTP {response.status_code}") from exc
        return response.text
    raise MiniError("Too many UQ catalogue redirects")
