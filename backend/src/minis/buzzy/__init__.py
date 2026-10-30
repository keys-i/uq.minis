"""Portable UTC calendar subscriptions with separate official and personal dates

Calendar events derive from the shared validated student plan and selected
announcements. Stable identities, escaping and UTF-8-safe line folding make
repeated subscriptions usable without duplicating or moving official dates
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def personal(item: dict[str, Any], buffer: float) -> str:
    """Keep the official deadline intact while deriving an earlier personal target"""
    if not item["due"]:
        return ""
    due = datetime.fromisoformat(item["due"])
    return (due - timedelta(days=buffer if item["buffer"] is None else item["buffer"])).isoformat()


def _escape(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _date(value: str) -> str:
    return datetime.fromisoformat(value).strftime("%Y%m%dT%H%M%SZ")


def render(plan: dict[str, Any]) -> str:
    """Produce stable event IDs, useful instructions and UTF-8-safe RFC 5545 folding"""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UQ minis//Buzzy//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Buzzy",
    ]
    courses = {course["id"]: course for course in plan["courses"]}

    def event(
        key: str, title: str, start: str, end: str, notes: str, url: str, status: str = ""
    ) -> None:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{key}@uq-minis",
            "DTSTAMP:" + _date(plan["updated"]),
            "DTSTART:" + _date(start),
            "SUMMARY:" + _escape(title),
            "DESCRIPTION:" + _escape(notes),
        ])
        if end:
            lines.append("DTEND:" + _date(end))
        if url:
            lines.append("URL:" + _escape(url))
        if status == "cancelled":
            lines.append("STATUS:CANCELLED")
        lines.append("END:VEVENT")

    for item in plan["assessments"]:
        if not item["due"]:
            continue
        course = courses[item["course"]]
        notes = f"{course['code']} · {item['weight']:g}% of course\nOfficial deadline: {item['due']}\n{item['notes']}"
        url = item["url"] or course["profile"]
        event(
            item["id"] + "-official",
            f"Due: {course['code']} {item['title']}",
            item["due"],
            "",
            notes,
            url,
        )
        target = personal(item, plan["settings"]["buffer"])
        if target != item["due"] and not item["done"]:
            event(
                item["id"] + "-personal",
                f"Personal target: {course['code']} {item['title']}",
                target,
                "",
                "Your earlier planning target; the official deadline is unchanged\n" + notes,
                url,
            )
    for item in plan["announcements"]:
        if item["start"] and (
            item["saved"] or item["club_url"] in plan["settings"].get("following", [])
        ):
            event(
                item["id"],
                item["title"],
                item["start"],
                item["end"],
                f"{item['source']} · {item['club']}\n{item['notes']}",
                item["url"],
                item["status"],
            )
    lines.append("END:VCALENDAR")
    folded: list[str] = []
    for line in lines:
        part = ""
        for char in line:
            if len((part + char).encode("utf-8")) > 75:
                folded.append(part)
                part = " "
            part += char
        folded.append(part)
    return "\r\n".join(folded) + "\r\n"
