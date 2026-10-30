"""Read official UQ offerings and their published assessment facts

Fetch only the selected published course and profile links, retaining their
period and campus. Exact deadlines use Brisbane time, while published exam
windows remain ranges and task descriptions retain their source wording
"""

from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from uq_minis.core.common import MiniError
from uq_minis.core.web import fetch, trusted
from uq_minis.minis.scrappy.http import BASE_URL, CODE
from uq_minis.minis.scrappy.http import fetch as catalogue
from uq_minis.minis.scrappy.scraper import parse_course

HOSTS = ("course-profiles.uq.edu.au", "archive.course-profiles.uq.edu.au")


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[list[str], list[str]]] = []
        self.cells: list[str] = []
        self.parts: list[str] = []
        self.links: list[str] = []
        self.in_cell = False
        self.hidden = 0
        self.text: list[str] = []
        self.detail = ""
        self.heading: list[str] | None = None
        self.description = False
        self.descriptions: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript", "button"}:
            self.hidden += 1
        if tag == "tr":
            self.cells, self.links = [], []
        elif tag in {"td", "th"}:
            self.in_cell, self.parts = True, []
        elif tag in {"br", "p", "li"}:
            self.handle_data(" ")
        elif tag == "h2":
            self.detail, self.description = "", False
        elif tag == "h3":
            identity = attributes.get("id") or ""
            self.detail = identity if identity.startswith("assessment-detail-") else ""
            self.description = False
        elif tag == "h4" and self.detail:
            self.heading, self.description = [], False
        if tag == "a" and self.in_cell:
            self.links.append(attributes.get("href") or "")

    def handle_data(self, data: str) -> None:
        if self.hidden:
            return
        if self.in_cell:
            self.parts.append(data)
        if self.heading is not None:
            self.heading.append(data)
        elif self.description and self.detail:
            self.descriptions.setdefault(self.detail, []).append(data)
        if data.strip():
            self.text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "button"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "h4" and self.heading is not None:
            self.description = (
                " ".join("".join(self.heading).split()).casefold() == "task description"
            )
            self.heading = None
        if tag in {"td", "th"} and self.in_cell:
            self.cells.append(" ".join("".join(self.parts).split()))
            self.in_cell = False
        elif tag == "tr" and self.cells:
            self.rows.append((self.cells, self.links))

    def task(self, links: list[str]) -> str:
        """Return the published task description linked by one summary row"""
        key = next((link[1:] for link in links if link.startswith("#assessment-detail-")), "")
        return " ".join("".join(self.descriptions.get(key, [])).split())[:12000]


def offerings(code: str) -> dict[str, Any]:
    """Fetch one selected course and retain each profile's period and campus"""
    code = code.strip().upper()
    if not CODE.fullmatch(code):
        raise MiniError("Choose a valid UQ course code")
    url = f"{BASE_URL}/course.html?course_code={code}"
    html = catalogue(url)
    details = parse_course(html)
    if details["Course Code"].strip().upper() != code:
        raise MiniError("The catalogue returned a different course; check the official course page")
    parser = _Tables()
    parser.feed(html)
    rows: list[dict[str, str]] = []
    for cells, links in parser.rows:
        if not cells or not re.match(
            r"(?:Semester|Summer|Trimester|Teaching Period)", cells[0], re.I
        ):
            continue
        profiles = [
            urljoin(BASE_URL, value) for value in links if any(host in value for host in HOSTS)
        ]
        profile = trusted(profiles[0], HOSTS) if profiles else ""
        rows.append({
            "period": cells[0],
            "campus": cells[1] if len(cells) > 1 else "",
            "profile": profile,
        })
    return {"details": details, "offerings": rows, "url": url}


def read(url: str) -> str:
    """Try the official profile without bypassing access restrictions"""
    return fetch(url, hosts=HOSTS)


def _range(value: str) -> str:
    """Condense a published date window without inventing one exact deadline"""
    matches = list(re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", value))
    if len(matches) != 2 or not re.fullmatch(
        r"\s*(?:-|–|—|to)\s*", value[matches[0].end() : matches[1].start()], re.IGNORECASE
    ):
        return value
    try:
        first, last = (datetime(int(match[3]), int(match[2]), int(match[1])) for match in matches)
    except ValueError:
        return value
    months = (
        "",
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    if first.year == last.year and first.month == last.month:
        return f"{first.day}–{last.day} {months[first.month]} {first.year}"
    if first.year == last.year:
        return f"{first.day} {months[first.month]}–{last.day} {months[last.month]} {first.year}"
    return (
        f"{first.day} {months[first.month]} {first.year}–"
        f"{last.day} {months[last.month]} {last.year}"
    )


def parse(html: str) -> dict[str, Any]:
    """Extract assessment facts and their linked task descriptions

    Only complete day/month/year plus time values become Brisbane timestamps
    Published date windows remain display text instead of invented deadlines
    """
    if len(html.encode("utf-8")) > 8 * 1024**2:
        raise MiniError("Saved profile exceeds 8 MiB")
    parser = _Tables()
    parser.feed(html)
    parser.close()
    headers: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for cells, links in parser.rows:
        labels = [cell.casefold() for cell in cells]
        if any("weight" in label for label in labels) and any("due" in label for label in labels):
            headers = {}
            for index, label in enumerate(labels):
                if "weight" in label:
                    headers["weight"] = index
                elif "due" in label:
                    headers["date"] = index
                elif "task" in label or "assessment" in label or label == "title":
                    headers["title"] = index
            continue
        if not {"title", "weight", "date"} <= headers.keys() or max(headers.values()) >= len(cells):
            continue
        title = cells[headers["title"]]
        weighting, date = cells[headers["weight"]], cells[headers["date"]]
        weight = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%\s*", weighting)
        if not title or not weight:
            continue
        due = ""
        dates = re.findall(
            r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\s*(am|pm)?\b", date, re.I
        )
        if len(dates) == 1 and len(re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", date)) == 1:
            day, month, year, hour, minute, meridiem = dates[0]
            clock = int(hour)
            if meridiem:
                clock = clock % 12 + (12 if meridiem.casefold() == "pm" else 0)
            try:
                if meridiem and not 1 <= int(hour) <= 12:
                    raise ValueError("Invalid 12-hour time")
                due = datetime(
                    int(year),
                    int(month),
                    int(day),
                    clock,
                    int(minute),
                    tzinfo=ZoneInfo("Australia/Brisbane"),
                ).isoformat()
            except ValueError:
                pass
        rows.append({
            "title": title[:300],
            "weight": float(weight[1]),
            "due": due,
            "due_text": _range(date),
            "notes": parser.task(links),
        })
    if not rows:
        raise MiniError("This published profile uses an unsupported assessment layout")
    rules = "\n".join(
        part
        for part in parser.text
        if re.search(
            r"hurdle|peer|\bPAF\b|penalt|must pass|late|round|minimum|lowest|assessment", part, re.I
        )
    )
    return {
        "assessments": rows,
        "rules": rules[:12000],
        "notice": "Synced from the published UQ course profile",
    }
