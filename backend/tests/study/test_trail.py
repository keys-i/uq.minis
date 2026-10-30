import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from uq_minis.core.common import MiniError
from uq_minis.minis.planny import readiness, research
from uq_minis.minis.scrappy import scraper, trail
from uq_minis.minis.scrappy.http import CatalogueUnavailable


def test_branches_and_cycles() -> None:
    requirements = {
        "CSSE3000": "CSSE2002 or ENGG2000",
        "CSSE2002": "CSSE1001",
        "ENGG2000": "CSSE1001",
        "CSSE1001": "CSSE2002",
    }

    def details(code: str) -> dict[str, dict[str, str]]:
        return {"details": {"Pre-Requisites": requirements[code]}}

    read = Mock(side_effect=details)
    graph = trail.build("CSSE3000", [], read)
    assert len(graph["nodes"]) == read.call_count == 4
    assert graph["nodes"][0]["wording"] == "CSSE2002 or ENGG2000"
    assert graph["nodes"][-1]["required"] == ["CSSE2002"]
    assert not graph["limited"]


def test_saved_tree_and_denial() -> None:
    read = Mock(side_effect=CatalogueUnavailable("UQ is unavailable"))
    graph = trail.build(
        "CSSE3000",
        [{"code": "CSSE3000", "requirements": {"Pre-Requisites": "CSSE2002 and MATH2001"}}],
        read,
    )
    assert read.call_count == 1
    assert len(graph["nodes"]) == 3
    assert graph["limited"]
    assert graph["nodes"][1]["error"] == "UQ is unavailable"
    assert not graph["nodes"][2]["loaded"]
    with pytest.raises(MiniError):
        trail.build("invalid", [], read)


def test_large_trees_have_a_fixed_read_budget() -> None:
    def details(code: str) -> dict[str, dict[str, str]]:
        return {
            "details": {
                "Pre-Requisites": f"CSSE{int(code[4:]) + 1:04} and MATH{int(code[4:]) + 1:04}"
            }
        }

    read = Mock(side_effect=details)
    graph = trail.build("CSSE1000", [], read)
    assert read.call_count <= 16
    assert len(graph["nodes"]) <= 80
    assert graph["limited"]


def test_knowledge_evidence() -> None:
    parsed = scraper.parse_course(
        '<h1 id="course-title">Software (CSSE2002)</h1>'
        '<p id="course-prerequisite">CSSE1001</p>'
        '<p id="course-assumed-background">Python and basic statistics</p>'
    )
    result = readiness.check(parsed, [], "Python")
    assert result["assumed"] == "Python and basic statistics"
    assert result["status"] == "missing"
    assert result["topics"] == ["Python", "Statistics"]
    assert "Java" not in result["topics"]


def test_crawl_preserves_research(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "research.json"
    previous = {
        **research.load(path),
        "reviews": [{"id": "review"}],
        "courses": [
            {
                "code": "CSSE2002",
                "name": "Old name",
                "faculty": "IT",
                "requirements": {"Pre-Requisites": "CSSE1001"},
            }
        ],
    }
    path.write_text(json.dumps(previous))
    crawl = Mock(
        return_value=[
            {
                "course_code": "CSSE2002",
                "course_name": "Official name",
                "offering_link": "https://programs-courses.uq.edu.au/course.html?course_code=CSSE2002",
            }
        ]
    )
    monkeypatch.setattr(research, "scrape_offerings", crawl)
    data = research.catalogue(path)
    assert data["courses"][0]["name"] == "Official name"
    assert data["courses"][0]["requirements"] == previous["courses"][0]["requirements"]
    assert data["reviews"] == previous["reviews"]
    research.catalogue(path)
    assert crawl.call_count == 1
    before = path.read_bytes()
    # A later failed crawl must not replace a useful snapshot
    saved = json.loads(before)
    saved["catalogue_updated"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(saved))
    before = path.read_bytes()
    crawl.return_value = []
    with pytest.raises(MiniError):
        research.catalogue(path)
    assert path.read_bytes() == before
