import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from uq_minis.core.common import MiniError
from uq_minis.minis.planny import feedback, research, sources


def page(code: str, stars: int, following: str = "") -> str:
    icons = "".join(
        f'<i class="{kind} fa-star"></i>' for kind in ["fas"] * stars + ["far"] * (5 - stars)
    )
    return (
        f'<div class="subject-rating"><h4><a href="{feedback.BASE}/{code.lower()}">{code}</a></h4><p>{icons}</p><p>A student observation</p></div>'
        + (f'<a href="{following}" rel="next">Next</a>' if following else "")
    )


def test_feedback_pagination_and_duplicate_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch = Mock(
        side_effect=[
            page("CSSE1001", 4, feedback.BASE + "?page=2"),
            page("CSSE1001", 4) + page("MATH1051", 2),
        ]
    )
    monkeypatch.setattr(feedback, "fetch", fetch)
    result = feedback.collect()
    assert result["CSSE1001"]["mean"] == 4 and result["CSSE1001"]["count"] == 1
    assert result["MATH1051"]["mean"] == 2
    assert fetch.call_count == 2
    assert "A student observation" not in json.dumps(result)


@pytest.mark.parametrize(
    "html",
    [
        "denied",
        page("CSSE1001", 0),
        page("CSSE1001", 4).replace('class="fas fa-star"', 'class="changed"'),
    ],
)
def test_feedback_rejects_missing_or_changed_ratings(html: str) -> None:
    with pytest.raises(MiniError):
        feedback.parse(html)


def test_feedback_failure_keeps_previous_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "research.json"
    path.write_text(json.dumps(research.load(path)))
    before = path.read_bytes()
    monkeypatch.setattr(
        feedback, "fetch", Mock(return_value=page("CSSE1001", 4, "https://foreign.example/?page=2"))
    )
    with pytest.raises(MiniError, match="next page"):
        research.expand(path)
    assert path.read_bytes() == before


def test_rating_weights() -> None:
    row = {"blended": {"mean": 1, "count": 10000}}
    reviews = [{"usefulness": 5, "fun": 5, "difficulty": 5}]
    extra = {"mean": 4, "count": 10}
    result = research.rating(row, reviews, {"mean": 5, "count": 100}, extra)
    assert result["mean"] > 4
    assert {part["kind"] for part in result["components"]} == {"student", "secat", "studentvip"}
    assert research.rating({}, [], {}, {})["mean"] is None
    assert research.rating({}, reviews, {}, {})["mean"] < 4


def test_course_filters_and_remembered_requirements(tmp_path: Path) -> None:
    path = tmp_path / "research.json"
    data = {
        **research.load(path),
        "courses": [
            {"code": "CSSE2002", "name": "Software", "faculty": "IT", "offered": "Semester 2, 2026"}
        ],
    }
    path.write_text(json.dumps(data))
    research.remember(path, "CSSE2002", {"Course Code": "CSSE2002", "Pre-Requisites": "CSSE1001"})
    data = research.load(path)
    assert research.search(data, semester="1")["total"] == 0
    assert (
        research.search(data, semester="2", completed=["CSSE1001"])["rows"][0]["readiness"][
            "status"
        ]
        == "ready"
    )
    assert research.search(data, semester="2")["rows"][0]["readiness"]["status"] == "missing"


def test_public_feed_reuses_snapshot_and_survives_outage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "feed.json"
    fetch = Mock(return_value=[{"id": "a", "title": "Club night"}])
    monkeypatch.setattr(sources, "rubric", fetch)
    assert sources.feed(path)["rows"][0]["id"] == "a"
    sources.feed(path)
    assert fetch.call_count == 1
    monkeypatch.setattr(sources, "time", lambda: path.stat().st_mtime + 4000)
    fetch.side_effect = MiniError("Try later")
    assert sources.feed(path)["warning"] == "Try later"
    assert sources.feed(path)["rows"][0]["id"] == "a"
    fetch.side_effect = None
    fetch.return_value = [{"id": "bad", "title": {}}]
    assert sources.feed(path)["rows"][0]["id"] == "a"
    assert sources.feed(path)["warning"]


@pytest.mark.parametrize(
    ("month", "semester", "year"),
    [(2, "1", 2026), (6, "2", 2026), (10, "2", 2026), (12, "1", 2027)],
)
def test_auto_semester_follows_current_or_upcoming_teaching(
    month: int, semester: str, year: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    clock = Mock(wraps=datetime)
    clock.now.return_value = datetime(2026, month, 10, tzinfo=UTC)
    monkeypatch.setattr(research, "datetime", clock)
    result = research.search(
        {"courses": [], "reviews": [], "secat": [], "updated": ""}, semester="auto"
    )
    assert result["semester"] == semester and result["study_year"] == year


def test_calendar_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    current: dict[str, Any] = {"settings": {"following": ["club"]}, "announcements": []}
    monkeypatch.setattr(
        sources,
        "feed",
        Mock(return_value={"rows": [{"id": "a", "club_url": "club", "source": "Rubric"}]}),
    )
    result = sources.calendar(current, tmp_path / "feed.json")
    assert result["announcements"][0]["id"] == "a"
    assert current["announcements"] == []
