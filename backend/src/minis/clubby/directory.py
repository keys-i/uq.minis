"""Searchable club records from UQU's public directory and historical CSV exports

UQU’s published directory determines current club membership; historical
imports and selected public profiles supply descriptive details. Refreshes
publish complete snapshots and preserve an existing catalogue after failure
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from hashlib import blake2b
from html import unescape
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from typing import Any, cast
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx

from uq_minis.core import cache
from uq_minis.core.common import MiniError, atomic_json, write_csv
from uq_minis.core.search import matches, terms
from uq_minis.core.web import fetch, trusted

BASE = "https://campus.hellorubric.com/"
UNION = "https://uqu.com.au/clubs-and-societies/"
FIELDS = (
    "name",
    "university",
    "interests",
    "description",
    "directory_url",
    "website",
    "facebook",
    "instagram",
    "discord",
    "membership",
    "logo",
    "banner",
    "contact",
    "sources",
    "profiled",
)
ALIASES = {
    "name": "Name",
    "interests": "Interests",
    "description": "Description",
    "directory_url": "Link",
    "website": "Website",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "discord": "Discord",
    "membership": "Pay link",
}


def _key(name: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", name).replace("’", "'").casefold().split())


def _row(source: dict[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    for field in FIELDS:
        value = source.get(field, source.get(ALIASES.get(field, field), ""))
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise MiniError(f"Club {field} must be text")
        value = value.strip()
        row[field] = "" if value.casefold() in {"no content found", "n/a"} else value
    if not row["name"]:
        raise MiniError("Every club needs a name")
    row["description"] = re.sub(
        r"[^\S\r\n]+", " ", re.sub(r"</?[A-Za-z][^>]*>", " ", unescape(row["description"]))
    ).strip()
    if row["profiled"]:
        try:
            if not 0 < float(row["profiled"]) <= time() + 300:
                raise ValueError
        except ValueError as exc:
            raise MiniError("The club profile date is invalid") from exc
    row["university"] = row["university"] or "UQ"
    for field in FIELDS[4:12]:
        value = row[field]
        if not value:
            continue
        if re.fullmatch(r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}(?:[/?#][^\s]*)?", value):
            value = row[field] = "https://" + value
        try:
            parsed = urlsplit(value)
            if parsed.scheme.casefold() == "wechat":
                row["contact"] = "\n".join(filter(None, (row["contact"], value)))
                row[field] = ""
                continue
            valid = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname
                and parsed.port in (None, 80, 443)
                and parsed.username is None
                and parsed.password is None
                and not any(ord(char) < 32 for char in value)
            )
        except ValueError:
            valid = False
        if not valid:
            raise MiniError(f"Club {field} must be an HTTP or HTTPS link: {row['name']}")
    return row


def load(path: Path) -> list[dict[str, str]]:
    """Read current or historical club CSV columns without losing descriptive text"""
    try:
        with path.expanduser().open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            fields = reader.fieldnames or []
            if not {"name", "Name"}.intersection(fields) or len(fields) != len(set(fields)):
                raise MiniError("Club CSV needs a unique name or Name column")
            rows: list[dict[str, str]] = []
            for number, source in enumerate(reader, 2):
                if None in source or any(value is None for value in source.values()):
                    raise MiniError(f"Invalid club CSV row {number}")
                if source.get("Name") == "No content found" and source.get("", "").isdecimal():
                    source["Name"] = f"Unnamed club (historical row {number})"
                for short, full in (("FB", "Facebook"), ("Wb", "Website"), ("IG", "Instagram")):
                    source.setdefault(full, source.get(short, ""))
                if "Description" not in source and "description" not in source:
                    source["Description"] = "\n\n".join(
                        source[field].strip()
                        for field in ("Info 1", "Info 2")
                        if source.get(field) and source[field].casefold() != "no content found"
                    )
                rows.append(_row(source))
    except csv.Error as exc:
        raise MiniError(f"Malformed club CSV: {exc}") from exc
    if not rows:
        raise MiniError("No clubs in CSV")
    return rows


def import_csv(source: Path, output: Path, *, details: Path | None = None) -> int:
    """Join old directory and detail exports by name and publish one atomic catalogue"""
    inputs = [source, *([details] if details else [])]
    if output.expanduser().resolve() in {path.expanduser().resolve() for path in inputs}:
        raise MiniError("Choose a different output file from the imported club CSVs")
    rows: dict[str, dict[str, str]] = {}
    for path in inputs:
        for row in load(path):
            key = _key(row["name"])
            if key in rows:
                rows[key].update({field: value for field, value in row.items() if value})
            else:
                rows[key] = row
    write_csv(output, FIELDS, sorted(rows.values(), key=lambda row: _key(row["name"])))
    return len(rows)


def records(kind: str = "societies") -> list[dict[str, Any]]:
    """Read a complete public UQU club or event snapshot with bounded pagination"""
    if kind not in {"societies", "events"}:
        raise MiniError("Rubric source must be societies or events")
    rows: dict[str, dict[str, Any]] = {}
    offset = 0
    total: int | None = None
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        for _ in range(100):
            query = {
                "firstCall": offset == 0,
                "sortType": "itemName" if kind == "societies" else "date",
                "sortDirection": "asc",
                "desiredType": kind,
                "limit": 100,
                "offset": offset,
                "searchQuery": "",
                "iframe": True,
                "showall": True,
                "countryCode": "AU",
                "state": "Queensland",
                "selectedUniversityId": "12",
                "device": "web_portal",
                "version": 4,
            }
            text = fetch(
                "https://api.hellorubric.com",
                client=client,
                hosts=("api.hellorubric.com",),
                data={"endpoint": "getUnifiedSearch", "details": json.dumps(query)},
            )
            try:
                decoded: Any = json.loads(text)
            except ValueError as exc:
                raise MiniError("UQU directory returned invalid JSON") from exc
            if not isinstance(decoded, dict):
                raise MiniError("UQU directory response must be an object")
            page = cast(dict[str, Any], decoded)
            if (
                page.get("success") is not True
                or str(page.get("selectedUniversityId")) != "12"
                or type(page.get("totalItemCount")) is not int
                or not 0 <= page["totalItemCount"] <= 10000
                or not isinstance(page.get("results"), list)
            ):
                raise MiniError(
                    "Unrecognised or empty UQU directory response; existing output kept"
                )
            if total is not None and page["totalItemCount"] != total:
                raise MiniError(
                    "Club directory changed during export; rerun for a complete snapshot"
                )
            total = cast(int, page["totalItemCount"])
            items = cast(list[Any], page["results"])
            if not items and offset < total:
                raise MiniError("Incomplete UQU directory page; existing output kept")
            for value in items:
                if not isinstance(value, dict):
                    raise MiniError("Invalid club directory record")
                item = cast(dict[str, Any], value)
                hosts = ("campus.hellorubric.com",)
                if kind == "events":
                    # Source links are displayed, never fetched with account credentials
                    hosts += (
                        "clubs.getqpay.com",
                        "www.facebook.com",
                        "facebook.com",
                        "www.instagram.com",
                        "instagram.com",
                    )
                destination = trusted(urljoin(BASE, str(item.get("destination", ""))), hosts)
                if not item.get("destination"):
                    raise MiniError("Club directory record has no source link")
                if destination in rows:
                    raise MiniError("Club directory repeats records; existing output kept")
                rows[destination] = item
            offset += len(items)
            if offset == total:
                return list(rows.values())
            if offset > total:
                raise MiniError("Club directory returned inconsistent page counts")
    raise MiniError("Club directory exceeds 100 pages; existing output kept")


def refresh(output: Path) -> int:
    """Save the complete current club directory without replacing it on failure"""
    previous = {row["directory_url"]: row for row in load(output)} if output.is_file() else {}
    rows: list[dict[str, str]] = []
    for item in records():
        url = urljoin(BASE, item["destination"])
        old = previous.get(url, {})
        row: dict[str, Any] = dict(old) if old.get("sources", "").startswith("UQU") else {}
        row.update(name=item.get("title"), directory_url=url, sources="UQU · " + UNION)
        for field, key in (
            ("facebook", "facebookurl"),
            ("instagram", "instagramurl"),
            ("discord", "discordurl"),
            ("logo", "image"),
        ):
            if item.get(key):
                row[field] = item[key]
        rows.append(_row(row))
    if not rows:
        raise MiniError("UQU returned an empty club directory; existing output kept")
    write_csv(output, FIELDS, rows)
    return len(rows)


def enrich(output: Path) -> int:
    """Complete the union's own profiles and atomically publish the enriched directory"""
    if not output.is_file():
        refresh(output)
    rows = load(output)
    for index, row in enumerate(rows):
        if row["profiled"] and time() - float(row["profiled"]) < 7 * 86400:
            continue
        details = profile(output, row["directory_url"])
        rows[index] = _row({**details["club"], "profiled": str(details["updated"] or time())})
    write_csv(output, FIELDS, rows)
    return len(rows)


def ensure(output: Path) -> str:
    """Populate the public directory automatically and keep a failed refresh reversible"""
    if output.is_file() and time() - output.stat().st_mtime < 86400:
        return ""
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with cache.locked(output.with_suffix(".lock")):
            if output.is_file() and time() - output.stat().st_mtime < 86400:
                return ""
            refresh(output)
    except MiniError as exc:
        if output.is_file():
            return str(exc)
        raise
    return ""


def profile(path: Path, url: str) -> dict[str, Any]:
    """Read only a listed club's public profile, using the shared bounded cache"""
    club = next((row for row in load(path) if row["directory_url"] == url), None)
    if club is None:
        raise MiniError("Choose a club from the saved union directory")
    parsed = urlsplit(url)
    society = parse_qs(parsed.query).get("s", [""])[0]
    if parsed.hostname != "campus.hellorubric.com" or not re.fullmatch(r"[1-9]\d{0,9}", society):
        return {
            "club": club,
            "events": [],
            "updated": "",
            "note": "Open this club's official site for its full profile",
        }
    root = path.parent / "cache"
    key = (
        blake2b(url.encode(), digest_size=8).hexdigest()
        + "-"
        + blake2b(b"club-profile-v1", digest_size=8).hexdigest()
    )
    cached = root / key / "profile.json"
    saved = cache.read(cached)
    if saved:
        result = cast(dict[str, Any], json.loads(saved))
        return {**result, "club": _row(result["club"])}
    root.mkdir(parents=True, exist_ok=True)
    with cache.locked(root / ".lock"):
        saved = cache.read(cached)
        if saved:
            result = cast(dict[str, Any], json.loads(saved))
            return {**result, "club": _row(result["club"])}
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            text = fetch(
                "https://api.hellorubric.com",
                client=client,
                hosts=("api.hellorubric.com",),
                data={
                    "endpoint": "getSocietyLandingPage",
                    "details": json.dumps({
                        "societyid": society,
                        "domain": "campus.hellorubric.com",
                    }),
                },
            )
        try:
            raw: Any = json.loads(text)
        except ValueError as exc:
            raise MiniError("The club profile returned invalid JSON") from exc
        if not isinstance(raw, dict):
            raise MiniError("The club profile returned an invalid response")
        data = cast(dict[str, Any], raw)
        if data.get("success") is not True or str(data.get("societyid")) != society:
            raise MiniError("The source didn't return the selected club")
        description = data.get("description") or club["description"]
        if not isinstance(description, str) or len(description) > 60000:
            raise MiniError("The club description is invalid or too large")
        details = _row({
            **club,
            "description": description,
            "interests": data.get("club_type") or club["interests"],
            "contact": data.get("societyemail") or club["contact"],
            "logo": data.get("logo_uploaded") or club["logo"],
            "banner": data.get("society_banner_image") or club["banner"],
            **{
                field: data.get(field + "url") or club[field]
                for field in ("facebook", "instagram", "discord", "website")
            },
        })
        events: list[dict[str, str]] = []
        sections = data.get("sections", [])
        if not isinstance(sections, list):
            raise MiniError("The club profile returned invalid sections")
        for value in cast(list[Any], sections)[:100]:
            if not isinstance(value, dict):
                raise MiniError("The club profile returned an invalid section")
            section = cast(dict[str, Any], value)
            if not isinstance(section.get("array", []), list):
                raise MiniError("The club profile returned invalid section items")
            for value in cast(list[Any], section.get("array", []))[:100]:
                if not isinstance(value, dict):
                    raise MiniError("The club profile returned an invalid event")
                item = cast(dict[str, Any], value)
                if item.get("eventid") and item.get("upcoming") == 1:
                    if not item.get("destination"):
                        raise MiniError("A club event is missing its source link")
                    events.append({
                        "title": str(item.get("title", ""))[:300],
                        "when": str(item.get("formatteddate", ""))[:300],
                        "url": trusted(
                            urljoin(BASE, str(item.get("destination", ""))),
                            ("campus.hellorubric.com",),
                        ),
                    })
        result = {
            "club": details,
            "events": events[:50],
            "updated": time(),
            "note": "Public Rubric profile · social feeds still require the account owner's authorisation",
        }
        with TemporaryDirectory(prefix=".profile-", dir=root) as temporary:
            source = Path(temporary) / "profile.json"
            atomic_json(source, result)
            cache.save(root, key, source, {"file": "profile.json", "url": url})
        return result


def search(
    path: Path, *, query: str = "", offset: int = 0, limit: int = 20
) -> tuple[list[dict[str, str]], int]:
    """Find clubs by name, interest or description and return a bounded page"""
    if offset < 0 or not 1 <= limit <= 200:
        raise MiniError("Offset must be nonnegative and limit between 1 and 200")
    topics = terms(query, "clubs")
    rows = [
        row for row in load(path) if matches(" ".join(row[field] for field in FIELDS[:4]), topics)
    ]
    return rows[offset : offset + limit], len(rows)
