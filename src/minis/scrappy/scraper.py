"""Extract course catalogue data without a parser dependency."""

from __future__ import annotations

import csv
import os
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import ClassVar
from urllib.parse import urljoin, urlsplit

import httpx

from uq_minis.helper.common import MiniError

BASE_URL = "https://programs-courses.uq.edu.au"
SEARCH_URL = f"{BASE_URL}/search.html?keywords=*&searchType=all"
OFFERING_FIELDS = ("course_code", "course_name", "offering_link")
DETAIL_FIELDS = (
    "Course Code",
    "Course Name",
    "Course Level",
    "Faculty",
    "School",
    "Units",
    "Duration",
    "Attendance Mode",
    "Incompatibles",
    "Pre-Requisites",
    "Restricted",
    "Class Hours",
    "Assessment Methods",
    "Course Coordinator",
    "Study Abroad",
    "Course Profile1",
    "Course Profile2",
    "Course Profile3",
    "Description",
)


def _text(parts: list[str]) -> str:
    """Collapse HTML text into one space-separated value."""
    return " ".join("".join(parts).split())


class _Links(HTMLParser):
    """Read course rows from the catalogue search result markup."""

    def __init__(self, base_url: str) -> None:
        """Configure a parser for links relative to the catalogue host."""
        super().__init__()
        self.base_url = base_url
        self.in_heading = False
        self.anchor_class: str | None = None
        self.anchor_href = ""
        self.anchor_text: list[str] = []
        self.course: dict[str, str] = {}
        self.rows: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "h2":
            self.course = {}
            self.in_heading = "trigger" in values.get("class", "").split()
        elif tag == "a":
            self.anchor_class = values.get("class", "")
            self.anchor_href = values.get("href", "")
            self.anchor_text = []

    def handle_data(self, data: str) -> None:
        if self.anchor_class is not None:
            self.anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.anchor_class is not None:
            label = _text(self.anchor_text)
            if self.in_heading and self.anchor_class == "code":
                self.course["course_code"] = label
            elif self.in_heading and self.anchor_class == "title":
                self.course["course_name"] = label
            elif label == "View all previous offerings" and set(self.course) == {
                "course_code",
                "course_name",
            }:
                self.course["offering_link"] = urljoin(self.base_url, self.anchor_href)
                self.rows.append(self.course)
                self.course = {}
            self.anchor_class = None
            self.anchor_href = ""
        elif tag == "h2":
            self.in_heading = False


class _Details(HTMLParser):
    """Read a course detail page's stable IDs and profile links."""

    ids: ClassVar[dict[str, str]] = {
        "course-level": "Course Level",
        "course-faculty": "Faculty",
        "course-school": "School",
        "course-units": "Units",
        "course-duration": "Duration",
        "course-mode": "Attendance Mode",
        "course-incompatible": "Incompatibles",
        "course-prerequisite": "Pre-Requisites",
        "course-restricted": "Restricted",
        "course-contact": "Class Hours",
        "course-assessment-methods": "Assessment Methods",
        "course-coordinator": "Course Coordinator",
        "course-studyabroard": "Study Abroad",
        "course-summary": "Description",
    }

    def __init__(self) -> None:
        """Initialise empty field collectors."""
        super().__init__()
        self.values: dict[str, list[str]] = {}
        self.active: list[tuple[str, str]] = []
        self.title: list[str] = []
        self.profiles: list[str] = []
        self.profile_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        key = self.ids.get(values.get("id", ""))
        if key:
            self.active.append((tag, key))
            self.values.setdefault(key, [])
        if values.get("id") == "course-title":
            self.active.append((tag, "title"))
        if tag == "a" and "profile-available" in values.get("class", ""):
            self.profile_href = values.get("href", "")

    def handle_data(self, data: str) -> None:
        for _, key in self.active:
            (self.title if key == "title" else self.values[key]).append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.profile_href:
            self.profiles.append(self.profile_href)
            self.profile_href = ""
        for index in range(len(self.active) - 1, -1, -1):
            if self.active[index][0] == tag:
                del self.active[index]
                break


def parse_offerings(html: str, *, base_url: str = BASE_URL) -> list[dict[str, str]]:
    """Parse offering rows from one UQ catalogue search page."""
    parser = _Links(base_url)
    parser.feed(html)
    if not parser.rows:
        raise MiniError("No course offerings found; the UQ catalogue page may have changed")
    return parser.rows


def parse_course(html: str) -> dict[str, str]:
    """Parse one UQ catalogue course detail page."""
    parser = _Details()
    parser.feed(html)
    title = _text(parser.title)
    match = re.fullmatch(r"(.+?)\s+\(([^()]+)\)", title)
    if not match:
        raise MiniError("No course title found; the UQ catalogue page may have changed")
    values = {field: "" for field in DETAIL_FIELDS}
    values["Course Name"] = match.group(1) if match else ""
    values["Course Code"] = match.group(2) if match else ""
    for key, parts in parser.values.items():
        values[key] = _text(parts)
    for index, profile in enumerate(parser.profiles[:3], 1):
        values[f"Course Profile{index}"] = profile
    return values


def fetch(url: str, *, client: httpx.Client | None = None) -> str:
    """Fetch one trusted catalogue page with a concise error."""
    try:
        response = (
            client.get(url)
            if client is not None
            else httpx.get(url, follow_redirects=True, timeout=30)
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MiniError(f"Cannot fetch {url}: {exc}") from exc
    return response.text


def write_csv(path: Path, fields: Iterable[str], rows: Iterable[dict[str, str]]) -> None:
    """Atomically replace a CSV export after every row has been written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def scrape_offerings(*, html: str | None = None) -> list[dict[str, str]]:
    """Fetch and parse the UQ catalogue search page."""
    return parse_offerings(html if html is not None else fetch(SEARCH_URL))


def scrape_details(
    urls: Iterable[str], *, pages: dict[str, str] | None = None
) -> list[dict[str, str]]:
    """Fetch and parse each unique trusted UQ course offering URL."""
    unique: list[str] = []
    seen: set[str] = set()
    for url in urls:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "programs-courses.uq.edu.au"
            or parsed.username
            or parsed.password
            or parsed.path != "/course.html"
        ):
            raise MiniError("Offering URLs must be https://programs-courses.uq.edu.au/course.html")
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    if pages is not None:
        try:
            return [parse_course(pages[url]) for url in unique]
        except KeyError as exc:
            raise MiniError(f"No supplied page for {exc.args[0]}") from exc
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        return [parse_course(fetch(url, client=client)) for url in unique]


def export_links(output: Path, *, html: Path | None = None) -> int:
    """Write offering links from saved HTML or the live catalogue and return the count."""
    rows = scrape_offerings(html=html.read_text(encoding="utf-8") if html else None)
    write_csv(output, OFFERING_FIELDS, rows)
    return len(rows)


def export_details(offerings: Path, output: Path) -> int:
    """Write course details for the links in an offering CSV and return the count."""
    with offerings.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if "offering_link" not in (reader.fieldnames or []):
            raise MiniError("Offering CSV must contain an offering_link column")
        rows = scrape_details(row["offering_link"] for row in reader if row.get("offering_link"))
    write_csv(output, DETAIL_FIELDS, rows)
    return len(rows)
