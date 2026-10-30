"""Attributed public course research, reviews and official SECaT chart imports

Saved snapshots combine distinct public observations with explicit evidence
weighting. Official requirements and SECaT retain provenance and sample
counts, while incomplete refreshes leave existing research available
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from html import unescape
from math import sqrt
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from uq_minis.core.cache import locked
from uq_minis.core.common import MiniError, atomic_json
from uq_minis.core.web import fetch
from uq_minis.minis.planny import feedback, plan, readiness
from uq_minis.minis.scrappy.http import CODE
from uq_minis.minis.scrappy.scraper import scrape_offerings

WALL = "https://uq.talkwalll.com"
API = "https://api-go8.talkwalll.com"
SECAT = "https://www.pbi.uq.edu.au/clientservices/SECaT/embedChart.aspx"
FACULTIES = {
    "bel": "Business, Economics and Law",
    "eait": "Engineering, Architecture and IT",
    "hmbs": "Health, Medicine and Behavioural Sciences",
    "hss": "Humanities, Arts and Social Sciences",
    "sci": "Science",
    "grad": "Graduate School",
    "college": "UQ College",
    "uni": "University-wide",
    "uqcol": "UQ College",
    "uqwide": "University-wide",
    "unknown": "Not listed",
}
METRICS = {"overall", "usefulness", "fun", "difficulty", "secat"}


def _code(value: Any) -> str:
    code = plan.text(value, 20).upper()
    if not CODE.fullmatch(code):
        raise MiniError("Choose a valid UQ course code")
    return code


def _plain(value: Any, limit: int = 12000) -> str:
    return unescape(re.sub(r"<[^>]*>", " ", plan.text(value or "", limit)))


def _score(value: Any) -> float | None:
    return None if value is None else plan.number(value, high=5)


@lru_cache(maxsize=2)
def _read(path: str, modified: int, size: int) -> dict[str, Any]:
    if size > 24 * 1024**2:
        raise MiniError("Research snapshot exceeds 24 MiB")
    data: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MiniError("Research snapshot is invalid; previous output kept")
    result = cast(dict[str, Any], data)
    for key, maximum in (("courses", 12000), ("reviews", 12000), ("secat", 30000)):
        rows: Any = result.get(key)
        if not isinstance(rows, list) or len(cast(list[Any], rows)) > maximum:
            raise MiniError("Research snapshot is invalid; previous output kept")
    for row in result["courses"]:
        row["faculty"] = FACULTIES.get(row.get("faculty_id"), row["faculty"])
    return result


def load(path: Path) -> dict[str, Any]:
    """Reuse one bounded snapshot rather than refetching sources for every search"""
    if path.is_symlink() or path.parent.is_symlink():
        raise MiniError("Research snapshots must not be symlinks")
    if not path.exists():
        return {
            "courses": [],
            "reviews": [],
            "secat": [],
            "feedback": {},
            "updated": "",
            "catalogue_date": "",
        }
    info = path.stat()
    return _read(str(path.resolve()), info.st_mtime_ns, info.st_size)


def _rows(client: httpx.Client, table: str, columns: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in range(0, 12000, 1000):
        query = urlencode({"select": columns, "order": "id", "limit": 1000, "offset": offset})
        raw: Any = json.loads(
            fetch(f"{API}/rest/v1/{table}?{query}", client=client, hosts=("api-go8.talkwalll.com",))
        )
        if not isinstance(raw, list) or len(cast(list[Any], raw)) > 1000:
            raise MiniError("Unexpected public review response; previous snapshot kept")
        if any(not isinstance(row, dict) for row in cast(list[Any], raw)):
            raise MiniError("Invalid public review record; previous snapshot kept")
        rows.extend(cast(list[dict[str, Any]], raw))
        if len(cast(list[Any], raw)) < 1000:
            return rows
    raise MiniError("Public catalogue exceeds the bounded import; previous snapshot kept")


def refresh(path: Path) -> dict[str, Any]:
    """Refresh public data at most daily and publish only a complete valid snapshot"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path.with_suffix(".lock")):
        previous = load(path)
        if previous["updated"] and datetime.fromisoformat(previous["updated"]) > datetime.now(
            UTC
        ) - timedelta(days=1):
            return previous
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            config = fetch(
                f"{WALL}/src/config/supabasePublic.js", client=client, hosts=("uq.talkwalll.com",)
            )
            match = re.search(r'\buq:\s*"(sb_publishable_[A-Za-z0-9_-]+)"', config)
            if not match:
                raise MiniError(
                    "Talkwall changed its public data configuration; previous snapshot kept"
                )
            client.headers.update({"apikey": match[1], "Accept-Profile": "uq"})
            subjects = _rows(
                client, "subjects", "code,name,description,faculty_id,offered_text,year"
            )
            raw_reviews = _rows(
                client,
                "reviews",
                "id,target_type,subject_code,professor_name,professor_id,faculty_id,quality,difficulty,liked,body,created_at",
            )
            client.headers.pop("apikey")
            client.headers.pop("Accept-Profile")
            summaries = fetch(f"{WALL}/llms.txt", client=client, hosts=("uq.talkwalll.com",))
        courses: dict[str, dict[str, Any]] = {}
        remembered = {row["code"]: row for row in previous["courses"] if row.get("requirements")}
        for row in subjects:
            code = _code(row.get("code"))
            year = int(plan.number(row.get("year", 2026), 2000, 2100))
            if code in courses and year < courses[code]["year"]:
                continue
            faculty = plan.text(row.get("faculty_id") or "", 100)
            courses[code] = {
                "code": code,
                "name": _plain(row.get("name"), 500),
                "description": _plain(row.get("description"), 60000)[:6000],
                "faculty": FACULTIES.get(faculty, faculty or "Not listed"),
                "faculty_id": faculty,
                "offered": _plain(row.get("offered_text"), 1000),
                "year": year,
                "url": f"https://programs-courses.uq.edu.au/course.html?course_code={code}",
                "wall": f"{WALL}/courses/{code.lower()}",
            }
            if code in remembered:
                courses[code].update({
                    key: remembered[code][key]
                    for key in ("requirements", "checked")
                    if key in remembered[code]
                })
        for match in re.finditer(
            r"\[([A-Z]{4}\d{4}[A-Z]?) .+?\]\(https://uq\.talkwalll\.com/courses/[^)]+\): (\d+) 条评价，综合 ([\d.]+)",
            summaries,
        ):
            if match[1] in courses:
                courses[match[1]]["blended"] = {
                    "mean": plan.number(float(match[3]), high=5),
                    "count": int(match[2]),
                }
        reviews: list[dict[str, Any]] = []
        for row in raw_reviews:
            target = row.get("target_type")
            if target not in {"course", "professor"}:
                continue
            code = _code(row["subject_code"]) if row.get("subject_code") else ""
            reviews.append({
                "id": plan.text(row["id"], 100),
                "target": target,
                "code": code,
                "professor": _plain(row.get("professor_name"), 300),
                "professor_id": plan.text(row.get("professor_id") or "", 100),
                "faculty": FACULTIES.get(
                    str(row.get("faculty_id")), str(row.get("faculty_id") or "Not listed")
                ),
                "usefulness": _score(row.get("quality")),
                "difficulty": _score(row.get("difficulty")),
                "fun": _score(row.get("liked")),
                "text": plan.text(row.get("body") or "", 12000),
                "date": plan.moment(row.get("created_at") or ""),
                "source": "Talkwall student review",
                "url": f"{WALL}/courses/{code.lower()}" if code else f"{WALL}/courses",
            })
        if previous.get("catalogue_updated"):
            courses = {
                row["code"]: {**courses.get(row["code"], {}), **row} for row in previous["courses"]
            }
        data = {
            "courses": list(courses.values()),
            "reviews": reviews,
            "secat": previous["secat"],
            "feedback": previous.get("feedback", {}),
            "feedback_updated": previous.get("feedback_updated", ""),
            "updated": datetime.now(UTC).isoformat(),
            "catalogue_date": previous["catalogue_date"]
            if previous.get("catalogue_updated")
            else "Saved catalogue; verify the current official offering",
            "catalogue_updated": previous.get("catalogue_updated", ""),
        }
        atomic_json(path, data, private=True)
        return data


def catalogue(path: Path) -> dict[str, Any]:
    """Publish an official course index while retaining saved details and review evidence"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path.with_suffix(".lock")):
        previous = load(path)
        if previous.get("catalogue_updated") and datetime.fromisoformat(
            previous["catalogue_updated"]
        ) > datetime.now(UTC) - timedelta(days=1):
            return previous
        rows = scrape_offerings()
        if not rows or len(rows) > 12000:
            raise MiniError("The official UQ index is empty or too large; saved catalogue kept")
        known = {row["code"]: row for row in previous["courses"]}
        courses: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = _code(row["course_code"])
            courses[code] = {
                **known.get(code, {"description": "", "faculty": "Not listed", "offered": ""}),
                "code": code,
                "name": _plain(row["course_name"], 500),
                "url": row["offering_link"],
            }
        data = {
            **previous,
            "courses": list(courses.values()),
            "catalogue_updated": datetime.now(UTC).isoformat(),
            "catalogue_date": "Official UQ programs and courses index",
        }
        atomic_json(path, data, private=True)
        return data


def expand(path: Path) -> dict[str, Any]:
    """Fill review gaps from an independent public index without replacing other feedback"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path.with_suffix(".lock")):
        previous = load(path)
        if previous.get("feedback_updated") and datetime.fromisoformat(
            previous["feedback_updated"]
        ) > datetime.now(UTC) - timedelta(days=7):
            return previous
        data = {
            **previous,
            "feedback": feedback.collect(),
            "feedback_updated": datetime.now(UTC).isoformat(),
        }
        atomic_json(path, data, private=True)
        return data


def remember(
    path: Path, code: str, details: dict[str, Any], offerings: list[dict[str, str]] | None = None
) -> None:
    """Keep checked course requirements available on discovery cards"""
    code = _code(code)
    if str(details.get("Course Code", "")).upper() != code:
        return
    with locked(path.with_suffix(".lock")):
        previous = load(path)
        old = next((row for row in previous["courses"] if row["code"] == code), None)
        if old is None or old.get("requirements") == details and offerings is None:
            return
        updated = {
            **old,
            "name": details.get("Course Name") or old["name"],
            "description": details.get("Description") or old.get("description", ""),
            "faculty": details.get("Faculty") or old["faculty"],
            "requirements": details,
            "checked": datetime.now(UTC).isoformat(),
        }
        if details.get("Faculty"):
            updated.pop("faculty_id", None)
        if offerings is not None:
            updated["offerings"] = offerings
            updated["offered"] = " / ".join(
                " · ".join(
                    filter(
                        None, (item["period"], item["campus"], details.get("Attendance Mode", ""))
                    )
                )
                for item in offerings
            )
        if all(old.get(key) == value for key, value in updated.items() if key != "checked"):
            return
        rows = [updated if row["code"] == code else row for row in previous["courses"]]
        atomic_json(path, {**previous, "courses": rows}, private=True)


def rating(
    row: dict[str, Any],
    reviews: list[dict[str, Any]],
    official: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Blend distinct feedback with capped evidence weight and a conservative small-sample prior"""
    components: list[tuple[str, float, int, float]] = []
    direct: list[float] = []
    for review in reviews:
        values = [review[key] for key in ("usefulness", "fun") if review.get(key) is not None]
        if values:
            direct.append(sum(values) / len(values))
    if direct:
        components.append(("student", sum(direct) / len(direct), len(direct), 0.7))
    if official.get("count") and official.get("mean") is not None:
        components.append(("secat", official["mean"], official["count"], 1.0))
    if extra.get("count") and extra.get("mean") is not None:
        components.append(("studentvip", extra["mean"], extra["count"], 0.65))
    elif not direct and row.get("blended", {}).get("count"):
        # The mixed aggregate overlaps StudentVIP, so it cannot be counted alongside it
        components.append(("mixed", row["blended"]["mean"], row["blended"]["count"], 0.15))
    if not components:
        return {"mean": None, "count": 0, "confidence": "none", "components": []}
    weights = [reliability * sqrt(min(count, 100)) for _, _, count, reliability in components]
    weight = sum(weights)
    return {
        "mean": round(
            (6 + sum(value * item[1] for value, item in zip(weights, components, strict=True)))
            / (2 + weight),
            1,
        ),
        "count": sum(item[2] for item in components),
        "confidence": "strong" if weight >= 5 else "building" if weight >= 2 else "early",
        "components": [
            {"kind": kind, "mean": mean, "count": count, "reliability": reliability}
            for kind, mean, count, reliability in components
        ],
    }


def secat(html: str) -> list[dict[str, Any]]:
    """Read the official chart's JSON array without executing its JavaScript"""
    match = re.search(
        r"\bvar\s+courseSECATData\s*=\s*(\[.*?\])\s*;", plan.text(html, 8 * 1024**2), re.S
    )
    if not match:
        raise MiniError("Choose saved HTML from UQ's SECaT chart; no chart data found")
    raw: Any = json.loads(match[1])
    if not isinstance(raw, list) or len(cast(list[Any], raw)) > 30000:
        raise MiniError("SECaT chart data is too large or invalid")
    groups: dict[tuple[str, str, str], dict[int, tuple[int, int]]] = defaultdict(dict)
    for value in cast(list[Any], raw):
        if not isinstance(value, dict):
            raise MiniError("Invalid SECaT record; original file kept")
        row = cast(dict[str, Any], value)
        if not {
            "COURSE_CD",
            "SEMESTER_DESCR",
            "QUESTION_NAME",
            "ANSWER",
            "VALUE",
            "ANSWERED_QUESTION",
        }.issubset(row):
            raise MiniError("Incomplete SECaT record; original file kept")
        code = _code(row["COURSE_CD"])
        key = (code, plan.text(row["SEMESTER_DESCR"], 100), plan.text(row["QUESTION_NAME"], 300))
        answer = re.match(r"([1-5])\s", plan.text(row["ANSWER"], 100))
        if not answer:
            raise MiniError("Unrecognised SECaT answer scale; original file kept")
        count = int(plan.number(row["VALUE"], high=100000))
        total = int(plan.number(row["ANSWERED_QUESTION"], high=100000))
        rank = int(answer[1])
        if rank in groups[key]:
            raise MiniError("Duplicate SECaT answer bucket")
        groups[key][rank] = (count, total)
    results: list[dict[str, Any]] = []
    for (code, period, question), buckets in groups.items():
        count = sum(item[0] for item in buckets.values())
        if set(buckets) != {1, 2, 3, 4, 5} or any(total != count for _, total in buckets.values()):
            raise MiniError("Incomplete SECaT distribution; original file kept")
        if count < 5:
            continue
        results.append({
            "code": code,
            "period": period,
            "question": question,
            "count": count,
            "mean": round(sum((6 - rank) * value[0] for rank, value in buckets.items()) / count, 2),
            "url": SECAT,
            "source": "UQ SECaT saved chart",
            "scale": "1–5 · 5 = strongly agree",
        })
    if not results:
        raise MiniError("No reportable SECaT results with at least five responses")
    return results


def import_secat(path: Path, html: str) -> int:
    """Merge official question/period results without mixing them into student scores"""
    incoming = secat(html)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path.with_suffix(".lock")):
        data = dict(load(path))
        rows = {(row["code"], row["period"], row["question"]): row for row in data["secat"]}
        rows.update({(row["code"], row["period"], row["question"]): row for row in incoming})
        if len(rows) > 30000:
            raise MiniError("Keep at most 30,000 SECaT question results")
        data["secat"] = list(rows.values())
        atomic_json(path, data, private=True)
    return len(incoming)


def metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep zero scores and use each dimension's actual response count"""
    result: dict[str, dict[str, Any]] = {}
    for name in ("usefulness", "fun", "difficulty"):
        scores = [row[name] for row in rows if row.get(name) is not None]
        result[name] = {
            "mean": round(sum(scores) / len(scores), 2) if scores else None,
            "count": len(scores),
        }
    return result


def _period(value: str) -> tuple[int, int]:
    year = re.search(r"\b(20\d{2})\b", value)
    semester = re.search(r"Semester ([12])", value)
    return (int(year[1]) if year else 0, int(semester[1]) if semester else 3)


def search(
    data: dict[str, Any],
    query: str = "",
    *,
    faculty: str = "",
    metric: str = "",
    order: str = "",
    minimum: int = 1,
    offset: int = 0,
    target: str = "course",
    semester: str = "all",
    completed: list[str] | None = None,
    skills: str = "",
) -> dict[str, Any]:
    """Rank attributed scores and page course or teacher results from the same snapshot"""
    if (
        metric
        and metric not in METRICS
        or order not in {"", "asc", "desc"}
        or target not in {"course", "professor"}
    ):
        raise MiniError("Choose a supported review category, order and target")
    if not 0 <= offset <= 12000 or not 1 <= minimum <= 10000:
        raise MiniError("Choose a valid page and response count")
    parsed = readiness.intent(plan.text(query, 500))
    if semester not in {"all", "auto", "1", "2", "summer"}:
        raise MiniError("Choose a listed study period")
    active = semester
    today = datetime.now(UTC).astimezone(ZoneInfo("Australia/Brisbane"))
    if semester == "auto":
        # shortcut: month-based teaching windows, use official dates when a calendar feed is available
        active = "2" if 6 <= today.month <= 11 else "1"
    selected_period = str(parsed["semester"] or (active if active != "all" else ""))
    dimension = metric or parsed["metric"]
    if order and dimension == "code":
        dimension = "overall"
    direction = order or parsed["order"]
    if metric and not order and parsed["metric"] != metric:
        direction = "asc" if metric == "difficulty" else "desc"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in data["reviews"]:
        if review["target"] == target:
            key = (
                review["code"]
                if target == "course"
                else review["professor_id"] or review["professor"]
            )
            if key:
                grouped[key].append(review)
    rows: list[dict[str, Any]] = []
    pool: list[dict[str, Any]] = (
        data["courses"]
        if target == "course"
        else [
            {
                "code": key,
                "name": items[0]["professor"],
                "faculty": items[0]["faculty"],
                "description": "",
                "wall": items[0]["url"],
            }
            for key, items in grouped.items()
        ]
    )
    official: dict[str, dict[str, Any]] = {}
    for row in data["secat"]:
        if row["question"].startswith("Q8") and _period(row["period"]) >= _period(
            official.get(row["code"], {}).get("period", "")
        ):
            official[row["code"]] = row

    def summarise(row: dict[str, Any]) -> dict[str, Any]:
        scores = metrics(grouped.get(row["code"], []))
        scores["secat"] = official.get(row["code"], {"mean": None, "count": 0})
        scores["overall"] = (
            rating(
                row,
                grouped.get(row["code"], []),
                scores["secat"],
                data.get("feedback", {}).get(row["code"], {}),
            )
            if target == "course"
            else scores["usefulness"]
        )
        return scores

    for row in pool:
        if faculty and row["faculty"] != faculty:
            continue
        if parsed["codes"] and row["code"] not in parsed["codes"]:
            continue
        if (
            not parsed["codes"]
            and parsed["terms"]
            and readiness.relevance(row, parsed["terms"]) < 0
        ):
            continue
        if target == "course" and parsed["level"] and row["code"][4] != str(parsed["level"]):
            continue
        if (
            target == "course"
            and selected_period
            and not parsed["codes"]
            and row.get("offered")
            and ("Summer" if selected_period == "summer" else f"Semester {selected_period}")
            not in row.get("offered", "")
        ):
            continue
        if dimension == "code":
            rows.append(row)
            continue
        scores = summarise(row)
        if scores[dimension]["mean"] is None or scores[dimension]["count"] < minimum:
            continue
        rows.append({**row, "metrics": scores})
    if dimension == "code":
        if parsed["terms"]:
            rows.sort(key=lambda row: (-readiness.relevance(row, parsed["terms"]), row["code"]))
        else:
            rows.sort(key=lambda row: row["code"])
    else:
        rows.sort(
            key=lambda row: (row["metrics"][dimension]["mean"], row["metrics"][dimension]["count"]),
            reverse=direction == "desc",
        )
    return {
        "rows": [
            {
                **row,
                "description": row.get("description", "")[:300],
                "metrics": row["metrics"] if dimension != "code" else summarise(row),
                "readiness": readiness.check(row.get("requirements", {}), completed or [], skills)
                if target == "course"
                else {},
            }
            for row in rows[offset : offset + 30]
        ],
        "total": len(rows),
        "faculties": sorted({row["faculty"] for row in pool}),
        "intent": {**parsed, "metric": dimension, "order": direction},
        "updated": data.get("catalogue_updated") or data["updated"],
        "semester": selected_period,
        "study_year": today.year + (today.month == 12 and selected_period == "1"),
    }


def course(data: dict[str, Any], code: str) -> dict[str, Any]:
    """Read one course's independent review sources without a network request"""
    code = _code(code)
    return {
        "course": next((row for row in data["courses"] if row["code"] == code), None),
        "reviews": [row for row in data["reviews"] if row["code"] == code][:200],
        "secat": [row for row in data["secat"] if row["code"] == code],
        "feedback": data.get("feedback", {}).get(code, {}),
    }
