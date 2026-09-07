"""Extract course catalogue data without a parser dependency."""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import closing
from html.parser import HTMLParser
from itertools import islice
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import ClassVar
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx

from uq_minis.helper.common import MiniError
from uq_minis.minis.scrappy.http import BASE_URL, CODE, CatalogueUnavailable, catalogue_url, fetch

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


def _offering(row: dict) -> dict[str, str]:
    code = (row.get("course_code") or "").strip().upper()
    name = (row.get("course_name") or "").strip()
    url = catalogue_url(row.get("offering_link") or "", course=True)
    if (
        not CODE.fullmatch(code)
        or not name
        or parse_qs(urlsplit(url).query)["course_code"] != [code]
    ):
        raise MiniError(f"Course code and link must match; invalid offering for {code!r}")
    return dict(course_code=code, course_name=name, offering_link=url)


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
        self.next_url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "h2":
            self.course = {}
            self.in_heading = "trigger" in values.get("class", "").split()
        elif tag == "a":
            self.anchor_class = values.get("class", "")
            self.anchor_href = values.get("href", "")
            self.anchor_text = []
            if "next" in values.get("rel", "").split():
                self.next_url = urljoin(self.base_url, self.anchor_href)

    def handle_data(self, data: str) -> None:
        if self.anchor_class is not None:
            self.anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.anchor_class is not None:
            label = _text(self.anchor_text)
            if self.in_heading and "code" in self.anchor_class.split():
                self.course["course_code"] = label.upper()
            elif self.in_heading and "title" in self.anchor_class.split():
                self.course["course_name"] = label
            elif label == "View all previous offerings" and set(self.course) == {
                "course_code",
                "course_name",
            }:
                self.course["offering_link"] = catalogue_url(
                    urljoin(self.base_url, self.anchor_href), course=True
                )
                self.rows.append(_offering(self.course))
                self.course = {}
            elif label.casefold() in {"next", "next page", "next ›", "next »"}:
                self.next_url = urljoin(self.base_url, self.anchor_href)
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
        "course-studyabroad": "Study Abroad",
        "course-summary": "Description",
    }

    def __init__(self) -> None:
        """Initialise empty field collectors."""
        super().__init__()
        self.values: dict[str, list[str]] = {}
        self.active: list[tuple[int, str]] = []
        self.stack: list[str] = []
        self.title: list[str] = []
        self.profiles: list[str] = []
        self.profile_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag in {"br", "p", "div", "li", "tr"}:
            self.handle_data(" ")
        if tag in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            return
        self.stack.append(tag)
        key = self.ids.get(values.get("id", ""))
        if key:
            self.active.append((len(self.stack), key))
            self.values.setdefault(key, [])
        if values.get("id") == "course-title":
            self.active.append((len(self.stack), "title"))
        if tag == "a" and "profile-available" in values.get("class", "").split():
            self.profile_href = values.get("href", "")

    def handle_data(self, data: str) -> None:
        for _, key in self.active:
            (self.title if key == "title" else self.values[key]).append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.profile_href:
            self.profiles.append(self.profile_href)
            self.profile_href = ""
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index] == tag:
                del self.stack[index:]
                self.active = [(depth, key) for depth, key in self.active if depth <= index]
                break
        if tag in {"p", "div", "li", "tr"}:
            self.handle_data(" ")


def _search_page(html: str, base_url: str) -> _Links:
    parser = _Links(base_url)
    parser.feed(html)
    parser.close()
    if not parser.rows:
        raise MiniError("No course offerings found; the UQ catalogue page may have changed")
    return parser


def parse_offerings(html: str, *, base_url: str = BASE_URL) -> list[dict[str, str]]:
    """Parse offering rows from one UQ catalogue search page."""
    parser = _search_page(html, base_url)
    return list({row["offering_link"]: row for row in parser.rows}.values())


def parse_course(html: str) -> dict[str, str]:
    """Parse one UQ catalogue course detail page."""
    parser = _Details()
    parser.feed(html)
    parser.close()
    title = _text(parser.title)
    match = re.fullmatch(rf"(.+?)\s+\(({CODE.pattern})\)", title)
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


def write_csv(path: Path, fields: Iterable[str], rows: Iterable[dict[str, str]]) -> None:
    """Atomically replace a CSV export after every row has been written."""
    path = path.expanduser()
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
    """Read saved HTML, or follow the live search result's next-page links."""
    if html is not None:
        return parse_offerings(html)
    rows, visited = {}, set()
    url = catalogue_url(SEARCH_URL)
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        while url:
            if url in visited or len(visited) >= 100:
                raise MiniError("UQ search pagination loops or exceeds 100 pages")
            visited.add(url)
            parser = _search_page(fetch(url, client=client), url)
            for row in parser.rows:
                rows[row["offering_link"]] = row
            url = catalogue_url(parser.next_url) if parser.next_url else ""
            if url and urlsplit(url).path != "/search.html":
                raise MiniError("UQ search pagination points outside search results")
    return list(rows.values())


def _results(urls: list[str], jobs: int) -> Iterator[tuple[str, dict[str, str] | None, str]]:
    if not 1 <= jobs <= 8:
        raise MiniError("Jobs must be between 1 and 8")
    if not urls:
        return

    def read(url):
        row = parse_course(fetch(url, client=client))
        if row["Course Code"] != parse_qs(urlsplit(url).query)["course_code"][0]:
            raise MiniError("UQ returned a different course than requested")
        return row

    with (
        httpx.Client(
            timeout=30, follow_redirects=False, limits=httpx.Limits(max_connections=jobs)
        ) as client,
        ThreadPoolExecutor(max_workers=jobs) as pool,
    ):
        pending = iter(urls)
        futures = {pool.submit(read, url): url for url in islice(pending, jobs)}
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                url = futures.pop(future)
                try:
                    row, error = future.result(), ""
                except CatalogueUnavailable:
                    raise
                except MiniError as exc:
                    row, error = None, str(exc)
                next_url = next(pending, None)
                if next_url is not None:
                    futures[pool.submit(read, next_url)] = next_url
                yield url, row, error


def scrape_details(
    urls: Iterable[str], *, pages: dict[str, str] | None = None, jobs: int = 4
) -> list[dict[str, str]]:
    """Fetch and parse each unique trusted UQ course offering URL."""
    unique = list(dict.fromkeys(catalogue_url(url, course=True) for url in urls))
    if pages is not None:
        try:
            return [parse_course(pages[url]) for url in unique]
        except KeyError as exc:
            raise MiniError(f"No supplied page for {exc.args[0]}") from exc
    rows = {}
    for url, row, error in _results(unique, jobs):
        if error:
            raise MiniError(f"{url}: {error}")
        rows[url] = row
    return [rows[url] for url in unique]


def export_links(output: Path, *, html: Path | None = None) -> int:
    """Write offering links from saved HTML or the live catalogue and return the count."""
    if html and html.expanduser().resolve() == output.expanduser().resolve():
        raise MiniError("Choose different files for saved HTML and offering CSV")
    rows = scrape_offerings(html=html.expanduser().read_text(encoding="utf-8") if html else None)
    write_csv(output, OFFERING_FIELDS, rows)
    return len(rows)


def load_offerings(offerings: Path) -> list[dict[str, str]]:
    """Read and validate an offering CSV before any network requests."""
    rows = {}
    try:
        with offerings.expanduser().open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            fields = reader.fieldnames or []
            if not set(OFFERING_FIELDS) <= set(fields) or len(fields) != len(set(fields)):
                raise MiniError(
                    "Offering CSV needs unique course_code, course_name and offering_link columns"
                )
            for number, row in enumerate(reader, 2):
                if None in row:
                    raise MiniError(f"Extra values on CSV line {number}")
                value = _offering(row)
                rows[value["offering_link"]] = value
    except csv.Error as exc:
        raise MiniError(f"Malformed offering CSV: {exc}") from exc
    if not rows:
        raise MiniError("No courses in offering CSV")
    return list(rows.values())


def list_courses(
    offerings: Path,
    *,
    query: str = "",
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """Search an offering CSV by code or name and return one bounded page."""
    if offset < 0 or not 1 <= limit <= 200:
        raise MiniError("Offset must be nonnegative and limit between 1 and 200")
    query = query.strip().casefold()
    rows = [
        row
        for row in load_offerings(offerings)
        if query in f"{row['course_code']} {row['course_name']}".casefold()
    ]
    return {"courses": rows[offset : offset + limit], "total": len(rows), "offset": offset}


def export_details(
    offerings: Path,
    output: Path,
    *,
    course: str | None = None,
    jobs: int = 4,
    fresh: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
) -> int:
    """Export selected courses, checkpointing successes until the whole CSV is ready."""
    import fcntl

    selected = load_offerings(offerings)
    if course:
        selected = [row for row in selected if row["course_code"] == course.strip().upper()]
        if not selected:
            raise MiniError(f"Course {course!r} is not in the offering CSV")
    if not 1 <= jobs <= 8:
        raise MiniError("Jobs must be between 1 and 8")
    output = output.expanduser()
    if output.resolve() == offerings.expanduser().resolve():
        raise MiniError("Choose a different file for details and offering links")
    output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = output.with_name(f".{output.name}.scrappy.sqlite3")
    lock_path = checkpoint.with_suffix(".lock")
    if checkpoint.is_symlink() or lock_path.is_symlink():
        raise MiniError("Scrappy checkpoint must not be a symlink")
    urls = [row["offering_link"] for row in selected]
    active_urls = set(urls)
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise MiniError("Another Scrappy export is using this output") from exc
        with closing(sqlite3.connect(checkpoint)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS courses (url TEXT PRIMARY KEY, data TEXT NOT NULL)"
            )
            if fresh:
                db.execute("DELETE FROM courses")
                db.commit()
            saved = {
                url: json.loads(data)
                for url, data in db.execute("SELECT url,data FROM courses")
                if url in active_urls
            }
            completed = len(saved)
            errors = []
            if progress:
                progress(completed, len(urls), "Resuming" if saved else "Fetching")
            for url, row, error in _results([url for url in urls if url not in saved], jobs):
                if error:
                    errors.append(f"{url}: {error}")
                else:
                    db.execute(
                        "INSERT OR REPLACE INTO courses VALUES (?,?)", (url, json.dumps(row))
                    )
                    db.commit()
                    saved[url] = row
                completed += 1
                if progress:
                    progress(completed, len(urls), "Failed" if error else row["Course Code"])
            if errors:
                raise MiniError(
                    f"{len(errors)} course(s) failed; existing output kept. Rerun to resume completed work.\n"
                    + "\n".join(errors[:3])
                )
            write_csv(output, DETAIL_FIELDS, (saved[url] for url in urls))
            db.execute("DELETE FROM courses")
            db.commit()
    return len(urls)
