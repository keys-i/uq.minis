"""Discover published UNSW teaching links without guessing course or term URLs

Course and term links come from published WebCMS markup and are validated
against their course codes. Collection retains the source’s explicit terms
rather than constructing plausible but unverified teaching URLs
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from uq_minis.core.common import MiniError
from uq_minis.core.web import fetch, trusted

BASE = "https://webcms3.cse.unsw.edu.au/"
HOSTS = ("webcms3.cse.unsw.edu.au",)
TERM = re.compile(r"\d{2}T[0-3]")
PATH = re.compile(r"/([A-Z]{4}\d{4})/(\d{2}T[0-3])/")


def offering(code: str, name: str, url: str) -> dict[str, str]:
    """Validate a published WebCMS course link against its course code"""
    url = trusted(url, HOSTS)
    match = PATH.fullmatch(urlsplit(url).path)
    if not match or match[1] != code or not name:
        raise MiniError("UNSW offering needs a matching course code, name and WebCMS term URL")
    return dict(course_code=code, course_name=name, offering_link=url, term=match[2])


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.href = ""
        self.parts: list[str] = []
        self.rows: dict[str, dict[str, str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.href = dict(attrs).get("href") or ""
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.href:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self.href:
            return
        url = urljoin(BASE, self.href)
        match = PATH.fullmatch(urlsplit(url).path)
        label = " ".join("".join(self.parts).split())
        if match and label.startswith(match[1]):
            name = label[len(match[1]) :].lstrip(" -–—")
            row = offering(match[1], name, url)
            self.rows[row["offering_link"]] = row
        self.href = ""


def scrape_offerings(*, html: str | None = None, term: str = "") -> list[dict[str, str]]:
    """Read current published courses, optionally selecting an explicitly listed term"""
    term = term.strip().upper()
    if term and not TERM.fullmatch(term):
        raise MiniError("UNSW term must look like 26T3")
    if html is None:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            html = fetch(BASE, client=client, hosts=HOSTS)
    parser = _Links()
    parser.feed(html)
    parser.close()
    if not parser.rows:
        raise MiniError("No UNSW course links found; WebCMS markup may have changed")
    rows = [row for row in parser.rows.values() if not term or row["term"] == term]
    if not rows:
        raise MiniError(f"No published UNSW courses found for {term}")
    return rows
