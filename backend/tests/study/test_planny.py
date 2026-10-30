import json
from collections.abc import Iterator
from email.message import Message
from os.path import relpath
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from urllib.request import Request

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from uq_minis import cli
from uq_minis.app import create
from uq_minis.cli.planny import imported
from uq_minis.core.common import MiniError
from uq_minis.minis import buzzy as calendar
from uq_minis.minis.planny import marks, plan, profile, sources


@pytest.fixture
def document() -> dict[str, Any]:
    return plan.validate({
        "courses": [{"id": "course", "code": "COMP3400", "name": "Logic", "verified": True}],
        "assessments": [
            {
                "id": "task1",
                "course": "course",
                "title": "Project",
                "weight": 50,
                "due": "2026-10-25T18:00:00+10:00",
                "score": 80,
            },
            {
                "id": "task2",
                "course": "course",
                "title": "Exam",
                "weight": 50,
                "due": "2026-11-12T09:00:00+10:00",
            },
        ],
    })


def test_private_revisioned_saves(tmp_path: Path, document: dict[str, Any]) -> None:
    path = tmp_path / "planny" / "plan.json"
    saved = plan.save(path, document)
    assert saved["revision"] == 1
    assert path.stat().st_mode & 0o777 == 0o600
    assert plan.load(path) == saved
    with pytest.raises(MiniError, match="Another tab"):
        plan.save(path, document)
    assert plan.load(path) == saved
    saved["settings"]["buffer"] = 5
    assert plan.save(path, saved)["revision"] == 2


@pytest.mark.parametrize("home_path", [False, True])
@pytest.mark.parametrize("force", [False, True])
def test_import_preserves_existing_plan(
    tmp_path: Path,
    document: dict[str, Any],
    runner: CliRunner,
    home_path: bool,
    force: bool,
) -> None:
    state, source = tmp_path / "plan.json", tmp_path / "reviewed.json"
    plan.save(state, document)
    previous = state.read_bytes()
    document["settings"]["buffer"] = 7
    source.write_text(json.dumps(document))
    destination = "~/" + relpath(state, Path.home()) if home_path else str(state)
    result = runner.invoke(
        cli.app,
        [
            "planny",
            "import",
            str(source),
            "--state",
            destination,
            *(["--force"] if force else []),
        ],
    )
    if force:
        assert result.exit_code == 0, result.output
        saved = plan.load(state)
        assert saved["revision"] == 2 and saved["settings"]["buffer"] == 7
    else:
        assert result.exit_code == 2 and "--force" in result.output
        assert state.read_bytes() == previous


def test_import_rejects_concurrent_edit(
    tmp_path: Path, document: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    state, source = tmp_path / "plan.json", tmp_path / "reviewed.json"
    plan.save(state, document)
    source.write_text(json.dumps(document))
    read = Path.read_text

    def read_and_edit(path: Path, *args: Any, **kwargs: Any) -> str:
        content = read(path, *args, **kwargs)
        if path == source:
            current = plan.load(state)
            current["settings"]["buffer"] = 9
            plan.save(state, current)
        return content

    monkeypatch.setattr(Path, "read_text", read_and_edit)
    with pytest.raises(MiniError, match="Another tab"):
        imported(source, state=state, force=True)
    assert plan.load(state)["settings"]["buffer"] == 9


@pytest.mark.parametrize(
    "change",
    [
        {"due": "2026-10-25"},
        {"weight": float("nan")},
        {"factor": -1},
        {"url": "javascript:alert(1)"},
        {"course": "not-enrolled"},
        {"maximum": 0},
        {"start": "2027-01-01T00:00:00Z"},
        {"title": ""},
    ],
)
def test_invalid_tasks(document: dict[str, Any], change: dict[str, Any]) -> None:
    document["assessments"][0].update(change)
    with pytest.raises(MiniError):
        plan.validate(document)


def test_corrupt_state_and_links(tmp_path: Path, document: dict[str, Any]) -> None:
    path = tmp_path / "plan.json"
    path.write_text("corrupt data")
    with pytest.raises(MiniError, match="invalid"):
        plan.save(path, document)
    assert path.read_text() == "corrupt data"
    alias = tmp_path / "alias.json"
    alias.symlink_to(path)
    with pytest.raises(MiniError, match="symlink"):
        plan.load(alias)
    document["assessments"][1]["id"] = "task1"
    with pytest.raises(MiniError, match="unique"):
        plan.validate(document)


def test_rubric_card_artwork(monkeypatch: pytest.MonkeyPatch) -> None:
    banner = "https://resources.hellorubric.com/event.png"
    logo = "https://resources.getqpay.com/club.png"
    monkeypatch.setattr(
        sources,
        "records",
        Mock(
            return_value=[
                {
                    "title": "Movie night",
                    "destination": "?eid=123",
                    "sortindex": 1793005200,
                    "societyname": "Film club",
                    "societyid": "456",
                    "image": banner,
                    "societylogo": logo,
                }
            ]
        ),
    )
    rows = sources.rubric()
    validated = plan.validate({"announcements": rows})["announcements"][0]
    assert validated["banner"] == banner and validated["logo"] == logo
    rows[0]["banner"] = "javascript:alert(1)"
    with pytest.raises(MiniError, match="Links"):
        plan.validate({"announcements": rows})


def test_paf_penalty_and_required_mark(document: dict[str, Any]) -> None:
    first, last = document["assessments"]
    first.update(team=True, factor=0.8, penalty=10)
    result = marks.calculate(
        document["courses"][0], document["assessments"], target=70, estimate=90
    )
    assert result["projection"] == 72
    assert result["required"] == 86
    assert result["low"] == 27 and result["high"] == 77
    last.update(score=90)
    assert (
        marks.calculate(document["courses"][0], document["assessments"], target=80)["required"]
        is None
    )


def test_paf_is_limited_to_group_projects_and_old_plans_migrate(
    document: dict[str, Any],
) -> None:
    item = document["assessments"][0]
    item.update(team=False, factor=0.8)
    assert plan.validate(document)["assessments"][0]["factor"] == 1
    item["team"] = True
    assert plan.validate(document)["assessments"][0]["factor"] == 0.8
    item.pop("team")
    migrated = plan.validate(document)["assessments"][0]
    assert migrated["team"] is True and migrated["factor"] == 0.8


def test_hurdles_and_drop_lowest(document: dict[str, Any]) -> None:
    course = document["courses"][0]
    document["assessments"][1].update(score=40, hurdle=50)
    result = marks.calculate(course, document["assessments"], target=50)
    assert result["projection"] == 49 and result["required"] is None
    quizzes = [
        {
            **document["assessments"][0],
            "id": f"quiz{i}",
            "group": "quizzes",
            "weight": 10,
            "score": mark,
        }
        for i, mark in enumerate((40, 60, 80))
    ]
    exam = {
        **document["assessments"][1],
        "id": "exam",
        "weight": 70,
        "score": 100,
        "hurdle": None,
    }
    course.update(drop_group="quizzes", drop_count=1)
    result = marks.calculate(course, [*quizzes, exam], target=85)
    assert result["projection"] == 91
    quizzes[0]["weight"] = 5
    assert marks.calculate(course, [*quizzes, exam], target=85)["projection"] is None


def test_missing_rule_evidence(document: dict[str, Any]) -> None:
    course = document["courses"][0]
    course["verified"] = False
    document["assessments"].pop()
    result = marks.calculate(course, document["assessments"], target=75)
    assert len(result["warnings"]) == 2


def test_calendar_keeps_real_dates_and_folds_unicode(document: dict[str, Any]) -> None:
    document["assessments"][0]["title"] = "☕ Study, then finish; breathe\n" * 8
    first = calendar.render(document)
    document["settings"]["buffer"] = 5
    second = calendar.render(document)
    assert first.count("BEGIN:VEVENT") == 4
    assert "DTSTART:20261025T080000Z" in first and "DTSTART:20261025T080000Z" in second
    assert "DTSTART:20261023T080000Z" in first and "DTSTART:20261020T080000Z" in second
    assert "UID:task1-official@uq-minis" in first and "UID:task1-official@uq-minis" in second
    assert all(len(line.encode()) <= 75 for line in first.split("\r\n"))
    assert "\\," in first and "\\;" in first and "\\n" in first


def test_only_selected_clubs_enter_calendar(document: dict[str, Any]) -> None:
    document["announcements"] = [
        {
            "id": "post",
            "title": "Event",
            "start": "2026-10-20T00:00:00Z",
            "source": "Rubric",
            "club_url": "https://campus.hellorubric.com/?s=1",
            "saved": False,
        }
    ]
    document = plan.validate(document)
    assert "UID:post@" not in calendar.render(document)
    document["settings"]["following"] = ["https://campus.hellorubric.com/?s=1"]
    assert "UID:post@" in calendar.render(document)


def test_profile_proposals_preserve_source() -> None:
    result = profile.parse("""<script>steal secrets</script><p>A PAF may apply; check section 5</p>
    <table><tr><th>Assessment task</th><th>Weighting</th><th>Due date</th></tr>
    <tr><td>Group project</td><td>40%</td><td>25/10/2026 2:00pm</td></tr>
    <tr><td>Exam</td><td>60%</td><td>Exam period, date to be confirmed</td></tr></table>""")
    assert result["assessments"][0]["due"] == "2026-10-25T14:00:00+10:00"
    assert result["assessments"][1]["due"] == ""
    assert result["assessments"][1]["due_text"].startswith("Exam period")
    assert "PAF" in result["rules"] and "steal" not in result["rules"]
    with pytest.raises(MiniError, match="unsupported assessment layout"):
        profile.parse("<p>Login required</p>")


def test_profile_details_and_date_ranges() -> None:
    result = profile.parse("""
    <table><tr><th>Assessment task</th><th>Weight</th><th>Due</th></tr>
    <tr><td><a href="#assessment-detail-0">Project</a></td><td>40%</td>
    <td>20/10/2026 - 25/10/2026</td></tr></table>
    <h2>Assessment details</h2><h3 id="assessment-detail-0">Project</h3>
    <h4>Task description</h4><div><p>Build and explain a small program</p>
    <button>Read full task description</button></div>
    <h4>Submission guidelines</h4><p>Upload elsewhere</p>
    """)
    item = result["assessments"][0]
    assert item["due"] == "" and item["due_text"] == "20–25 Oct 2026"
    assert item["notes"] == "Build and explain a small program"


def test_profile_read_uses_bounded_native_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Request] = []

    class Response:
        headers = Message()

        def read(self, limit: int) -> bytes:
            assert limit == 8 * 1024**2 + 1
            return b"<html>published profile</html>"

        def close(self) -> None:
            pass

    class Opener:
        def open(self, request: Request, *, timeout: int) -> Response:
            requests.append(request)
            assert timeout == 30
            return Response()

    def opener(*_handlers: object) -> Opener:
        return Opener()

    monkeypatch.setattr("uq_minis.core.web.build_opener", opener)
    url = "https://course-profiles.uq.edu.au/course-profiles/CSSE1001-60765-7660"
    assert profile.read(url) == "<html>published profile</html>"
    assert requests[0].full_url == url
    assert requests[0].get_header("Cookie") is None


def test_feed_merge_and_imports() -> None:
    old = [
        {"id": "one", "source": "Rubric", "saved": True},
        {"id": "gone", "source": "Rubric"},
        {"id": "manual", "source": "Instagram"},
    ]
    merged = sources.merge(
        old,
        [{"id": "one", "source": "Rubric", "saved": False}],
        replace_source="Rubric",
    )
    assert len(merged) == 2 and next(item for item in merged if item["id"] == "one")["saved"]
    imported = sources.imported(
        json.dumps([
            {
                "title": "Game night",
                "url": "https://www.instagram.com/p/example/",
                "source": "Instagram",
            }
        ]),
        "social",
    )
    assert imported[0]["start"] == "" and imported[0]["source"] == "Instagram"
    with pytest.raises(MiniError, match="HTTP"):
        sources.imported('[{"title":"Bad", "url":"javascript:alert(1)"}]', "social")


@pytest.mark.parametrize("date", ["20/10/2026 to 25/10/2026 2:00pm", "25/10/2026 14:00pm"])
def test_ambiguous_profile_dates_stay_unset(date: str) -> None:
    result = profile.parse(
        f"<table><tr><th>Assessment task</th><th>Weight</th><th>Due</th></tr><tr><td>Project</td><td>100%</td><td>{date}</td></tr></table>"
    )
    assert result["assessments"][0]["due"] == ""


def test_profile_fields_survive_plan_validation(document: dict[str, Any]) -> None:
    document["assessments"][0].update(
        source="profile",
        due_text="20–25 Oct 2026",
        url="https://course-profiles.uq.edu.au/current",
    )
    item = plan.validate(document)["assessments"][0]
    assert item["source"] == "profile" and item["due_text"] == "20–25 Oct 2026"


@pytest.fixture
def service(tmp_path: Path) -> Iterator[tuple[httpx.Client, str]]:
    app = create(
        state=tmp_path / "state" / "plan.json",
        courses=tmp_path / "courses.csv",
        clubs=tmp_path / "clubs.csv",
    )
    origin = "http://127.0.0.1:8765"
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        yield client, origin


def test_server_state_and_csrf(service: tuple[httpx.Client, str], document: dict[str, Any]) -> None:
    client, _ = service
    assert client.get("/").status_code == 200
    assert "frame-ancestors 'none'" in client.get("/").headers["Content-Security-Policy"]
    assert client.get("/api/minis/scrappy").status_code == 200
    assert (
        client.post(
            "/api/plan", json=document, headers={"Origin": "https://evil.example"}
        ).status_code
        == 400
    )
    saved = client.post("/api/plan", json=document)
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert client.post("/api/plan", json=document).status_code == 409
    assert client.get("/api/plan").json()["revision"] == 1
    assert "BEGIN:VCALENDAR" in client.get("/calendar.ics").text
    assert client.get("/api/plan", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/../../pyproject.toml").status_code == 404


def test_server_marks_and_import(
    service: tuple[httpx.Client, str], document: dict[str, Any]
) -> None:
    client, _ = service
    response = client.post("/api/marks", json={"plan": document, "estimate": 80})
    assert response.status_code == 200 and response.json()["course"]["projection"] == 80
    response = client.post(
        "/api/import",
        json={
            "kind": "social",
            "text": '[{"title":"Meetup", "url":"https://example.org/event"}]',
        },
    )
    assert response.status_code == 200 and len(response.json()["announcements"]) == 1
    assert client.get("/api/search?kind=unknown").status_code == 400
