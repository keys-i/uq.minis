"""Bounded reads from explicitly trusted public web sources

Every redirect is checked before it is followed and response bytes are
bounded while reading. Callers supply the trusted hosts and parse the
returned content within their own mini-specific trust rules
"""

from __future__ import annotations

from http.client import HTTPMessage
from typing import IO, Protocol, cast, override
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import httpx

from uq_minis.core.common import MiniError

LIMIT = 8 * 1024**2


class _Response(Protocol):
    headers: HTTPMessage

    def read(self, amount: int | None = None) -> bytes: ...

    def close(self) -> None: ...


class _TrustedRedirect(HTTPRedirectHandler):
    def __init__(self, hosts: tuple[str, ...]) -> None:
        self.hosts: tuple[str, ...] = hosts

    @override
    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        return super().redirect_request(req, fp, code, msg, headers, trusted(newurl, self.hosts))


def trusted(url: str, hosts: tuple[str, ...]) -> str:
    """Require HTTPS, an allowed host and no embedded credentials or unusual port"""
    try:
        parsed = urlsplit(url.strip())
        if (
            parsed.scheme == "https"
            and parsed.hostname in hosts
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
            and not any(ord(char) < 32 for char in url)
        ):
            return urlunsplit(("https", parsed.hostname, parsed.path, parsed.query, ""))
    except ValueError:
        pass
    raise MiniError("Source URL must use HTTPS on " + ", ".join(hosts))


def fetch(
    url: str,
    *,
    hosts: tuple[str, ...],
    client: httpx.Client | None = None,
    data: dict[str, str] | None = None,
) -> str:
    """Read up to 8 MiB and check each redirect before following it

    POST is only for public search APIs and is never redirected or retried
    Access denial and rate limits fail immediately without publishing partial data
    """
    url = trusted(url, hosts)
    if client is None:
        if data is not None:
            raise MiniError("Public POST requests require an HTTP client")
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "UQMinis/0.33 https://uni.keysi.dev/mini/",
            },
        )
        try:
            response = cast(
                _Response,
                build_opener(_TrustedRedirect(hosts)).open(request, timeout=30),
            )
            try:
                body = response.read(LIMIT + 1)
                encoding = response.headers.get_content_charset() or "utf-8"
            finally:
                response.close()
        except HTTPError as exc:
            raise MiniError(
                f"{urlsplit(url).hostname} returned HTTP {exc.code}; "
                "existing output kept. Check access or try again later"
            ) from exc
        except URLError as exc:
            raise MiniError(
                f"Cannot read {urlsplit(url).hostname}: {type(exc.reason).__name__}"
            ) from exc
        if len(body) > LIMIT:
            raise MiniError("Source response exceeds the 8 MiB limit")
        return body.decode(encoding, errors="replace")
    try:
        for _ in range(6):
            with client.stream(
                "POST" if data is not None else "GET",
                url,
                data=data,
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("Location")
                    if data is not None or not location:
                        raise MiniError("Source returned an unsupported redirect")
                    url = trusted(urljoin(url, location), hosts)
                    continue
                if not 200 <= response.status_code < 300:
                    raise MiniError(
                        f"{urlsplit(url).hostname} returned HTTP {response.status_code}; "
                        "existing output kept. Check access or try again later"
                    )
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    if len(body) + len(chunk) > LIMIT:
                        raise MiniError("Source response exceeds the 8 MiB limit")
                    body.extend(chunk)
                return body.decode(response.encoding or "utf-8", errors="replace")
    except httpx.HTTPError as exc:
        raise MiniError(f"Cannot read {urlsplit(url).hostname}: {type(exc).__name__}") from exc
    raise MiniError("Too many source redirects")
