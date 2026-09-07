from types import SimpleNamespace

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from typer.testing import CliRunner

from uq_minis import cli
from uq_minis.cli import commands
from uq_minis.minis.scrappy import scraper

LISTING = '<h2 class="trigger"><a class="code">COMP3400</a><a class="title">Logic</a></h2><a href="/course.html?course_code=COMP3400">View all previous offerings</a>'
COURSE = '<h1 id="course-title">Software (CSSE2002)</h1><p id="course-level">Undergraduate</p>'
runner = CliRunner()


def test_scrappy_noninteractive_help_and_search(tmp_path):
    result = runner.invoke(cli.app, ["scrappy", "--no-input"])
    assert result.exit_code == 0 and "details" in result.output
    assert "Neo4j" not in result.output
    html, offerings = tmp_path / "search.html", tmp_path / "links.csv"
    html.write_text(LISTING)
    scraper.export_links(offerings, html=html)
    found = runner.invoke(cli.app, ["scrappy", "list", str(offerings), "--query", "logic"])
    assert found.exit_code == 0 and "COMP3400" in found.output
    absent = runner.invoke(cli.app, ["scrappy", "list", str(offerings), "--query", "CSSE"])
    assert absent.exit_code == 0 and "COMP3400" not in absent.output


def test_menu_browses_refreshes_and_exports_one_and_all(tmp_path, monkeypatch):
    html, offerings, output = tmp_path / "search.html", tmp_path / "links.csv", tmp_path / "courses"
    html.write_text(LISTING)
    scraper.export_links(offerings, html=html)
    html.write_text(LISTING.replace("COMP3400", "CSSE2002").replace("Logic", "Software"))
    monkeypatch.setattr(
        commands, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
    )
    monkeypatch.setattr(scraper, "fetch", lambda *args, **kwargs: COURSE)
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        pipe.send_text("1\nback\n2\n3\nCSSE2002\n4\n5\n")
        result = runner.invoke(
            cli.app,
            [
                "scrappy",
                "--offerings",
                str(offerings),
                "--html",
                str(html),
                "--output-dir",
                str(output),
            ],
        )
    assert result.exit_code == 0, result.output
    assert "COMP3400" in result.output
    assert "CSSE2002" in (output / "CSSE2002.csv").read_text()
    assert "CSSE2002" in (output / "courses.csv").read_text()
    assert "COMP3400" not in offerings.read_text()


def test_cli_selects_one_course_and_rejects_unknown_code(tmp_path, monkeypatch):
    html, offerings, output = tmp_path / "search.html", tmp_path / "links.csv", tmp_path / "one.csv"
    html.write_text(LISTING + LISTING.replace("COMP3400", "CSSE2002"))
    scraper.export_links(offerings, html=html)
    monkeypatch.setattr(scraper, "fetch", lambda *args, **kwargs: COURSE)
    result = runner.invoke(
        cli.app,
        [
            "scrappy",
            "details",
            str(offerings),
            "--course",
            "csse2002",
            "--jobs",
            "2",
            "-o",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(output.read_text().splitlines()) == 2
    invalid = runner.invoke(
        cli.app, ["scrappy", "details", str(offerings), "--course", "NONE0000", "-o", str(output)]
    )
    assert (
        invalid.exit_code == 2 and "not in" in invalid.output and "Traceback" not in invalid.output
    )
