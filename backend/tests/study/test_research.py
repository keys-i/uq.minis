import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from uq_minis.core.common import MiniError
from uq_minis.minis.planny import plan, readiness, research


@pytest.mark.parametrize(
    ("wording", "completed", "status"),
    [
        ("CSSE1001 or ENGG1001", ["ENGG1001"], "ready"),
        ("(CSSE1001 or ENGG1001) and MATH1051", ["CSSE1001"], "missing"),
        ("CSSE1001 and (MATH1051 or MATH1071)", ["CSSE1001", "MATH1071"], "ready"),
        ("CSSE1001 or equivalent experience", ["CSSE1001"], "review"),
        ("CSSE1001 (may be taken concurrently)", [], "review"),
        ("CSSE1001 or", ["CSSE1001"], "review"),
        ("None", [], "ready"),
        ("", [], "review"),
    ],
)
def test_prerequisites(wording: str, completed: list[str], status: str) -> None:
    result = readiness.check({"Pre-Requisites": wording}, completed, "Python")
    assert result["status"] == status
    if status == "ready":
        assert result["missing"] == []
    if wording == "CSSE1001 or ENGG1001":
        assert result["completed"] == ["ENGG1001"]


def test_restrictions_and_skills_do_not_waive_requirements() -> None:
    result = readiness.check(
        {"Pre-Requisites": "CSSE1001", "Description": "Python programming"}, [], "Python"
    )
    assert result["status"] == "missing" and result["skills"] == ["python"]
    assert (
        readiness.check({"Pre-Requisites": "None", "Restricted": "Permission required"}, [])[
            "status"
        ]
        == "review"
    )
    assert (
        readiness.check({"Pre-Requisites": "None", "Incompatibles": "CSSE1001"}, ["CSSE1001"])[
            "status"
        ]
        == "incompatible"
    )


def test_student_profile_survives_atomic_saves(tmp_path: Path) -> None:
    data = plan.empty()
    data["settings"].update(completed=["csse1001", "CSSE1001"], skills="Python and calculus")
    path = tmp_path / "plan.json"
    saved = plan.save(path, data)
    assert plan.load(path)["settings"] == saved["settings"]
    assert saved["settings"]["completed"] == ["CSSE1001"]
    data["settings"]["completed"] = ["not-a-course"]
    with pytest.raises(MiniError):
        plan.save(path, data)
    assert plan.load(path) == saved


def chart(counts: list[int]) -> str:
    rows = [
        {
            "COURSE_CD": "CSSE1001",
            "SEMESTER_DESCR": "Semester 1, 2026",
            "QUESTION_NAME": "Q8: Overall Rating",
            "ANSWER": f"{rank} Answer",
            "VALUE": count,
            "ANSWERED_QUESTION": sum(counts),
        }
        for rank, count in enumerate(counts, 1)
    ]
    return "<script>var courseSECATData = " + json.dumps(rows) + ";</script>"


def test_secat_scale(tmp_path: Path) -> None:
    result = research.secat(chart([6, 2, 1, 1, 0]))
    assert result[0]["mean"] == 4.3 and result[0]["count"] == 10
    path = tmp_path / "research.json"
    research.import_secat(path, chart([6, 2, 1, 1, 0]))
    research.import_secat(path, chart([5, 5, 0, 0, 0]))
    assert len(research.load(path)["secat"]) == 1
    before = path.read_bytes()
    with pytest.raises(MiniError):
        research.import_secat(path, chart([1, 1, 1, 1, 0]))
    assert path.read_bytes() == before


def test_scores_keep_zero_and_missing_separate() -> None:
    result = research.metrics([{"fun": 0}, {"fun": None}, {"fun": 4}])
    assert result["fun"] == {"mean": 2, "count": 2}
    assert result["difficulty"] == {"mean": None, "count": 0}


def test_secat_latest_period_uses_year_before_semester() -> None:
    data = {
        "courses": [{"code": "CSSE1001", "name": "Programming", "faculty": "IT"}],
        "reviews": [],
        "updated": "now",
        "secat": [
            {
                "code": "CSSE1001",
                "question": "Q8: Overall Rating",
                "period": period,
                "mean": mean,
                "count": 10,
            }
            for period, mean in (("Summer Semester, 2025", 5), ("Semester 1, 2026", 4))
        ],
    }
    result = research.search(data, metric="secat")
    assert result["rows"][0]["metrics"]["secat"]["mean"] == 4


def test_topic_search() -> None:
    courses = [
        {
            "code": code,
            "name": "Software programming",
            "faculty": "IT",
            "offered": "Semester 1, 2026",
        }
        for code in ("CSSE1001", "CSSE2002", "ENGG1001")
    ]
    reviews = [
        {"target": "course", "code": "CSSE1001", "fun": 3},
        {"target": "course", "code": "ENGG1001", "fun": 5},
    ]
    data = {"courses": courses, "reviews": reviews, "secat": [], "updated": "now"}
    result = research.search(data, "find fun first year coding courses")
    assert [row["code"] for row in result["rows"]] == ["ENGG1001", "CSSE1001"]
    assert research.search(data, metric="fun", order="asc")["rows"][0]["code"] == "CSSE1001"
    assert research.search(data, metric="fun", minimum=5)["total"] == 0
    assert research.search(data, "can I do CSSE2002 right now")["rows"][0]["code"] == "CSSE2002"
    assert readiness.intent("second year coding semester 2")["semester"] == "2"


def test_compsci_search_expands_from_core_subjects_by_relevance() -> None:
    courses = [
        {"code": "ENGG1001", "name": "Software engineering", "faculty": "Engineering"},
        {"code": "DECO1400", "name": "Introduction to design", "faculty": "EAIT"},
        {"code": "INFS1200", "name": "Information systems", "faculty": "EAIT"},
        {"code": "CSSE1001", "name": "Programming", "faculty": "EAIT"},
        {"code": "ACCT1101", "name": "Accounting", "faculty": "Business"},
    ]
    data = {"courses": courses, "reviews": [], "secat": [], "updated": "now"}

    result = research.search(data, "compsci")

    assert [row["code"] for row in result["rows"]] == [
        "CSSE1001",
        "INFS1200",
        "DECO1400",
        "ENGG1001",
    ]
    assert readiness.intent("computer science")["terms"] == ["compsci"]


def test_refresh_preserves_snapshot_after_a_denied_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "research.json"
    path.write_text(json.dumps({"courses": [], "reviews": [], "secat": [], "updated": ""}))
    original = path.read_bytes()
    monkeypatch.setattr(research, "fetch", Mock(side_effect=MiniError("HTTP 403")))
    with pytest.raises(MiniError, match="403"):
        research.refresh(path)
    assert path.read_bytes() == original


def test_public_import_uses_attribution_and_daily_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fetch(url: str, **kwargs: Any) -> str:
        calls.append(url)
        if "supabasePublic" in url:
            return 'uq: "sb_publishable_public-test-key"'
        if "/subjects?" in url:
            return json.dumps([{"code": "CSSE1001", "name": "Programming", "year": 2026}])
        if "/reviews?" in url:
            return json.dumps([
                {
                    "id": "r1",
                    "target_type": "course",
                    "subject_code": "CSSE1001",
                    "quality": None,
                    "liked": 0,
                }
            ])
        return ""

    monkeypatch.setattr(research, "fetch", fetch)
    path = tmp_path / "research.json"
    data = research.refresh(path)
    assert data["reviews"][0]["fun"] == 0
    assert data["reviews"][0]["url"].endswith("/csse1001")
    first = len(calls)
    assert research.refresh(path) == data and len(calls) == first
