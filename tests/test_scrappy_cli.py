import pytest

from uq_minis import cli
from uq_minis.cli import scrappy
from uq_minis.minis.scrappy import scraper

pytestmark = pytest.mark.usefixtures("courses")


LISTING = '<h2 class="trigger"><a class="code">COMP3400</a><a class="title">Logic</a></h2><a href="/course.html?course_code=COMP3400">View all previous offerings</a>'
COURSE = '<h1 id="course-title">Software (CSSE2002)</h1><p id="course-level">Undergraduate</p>'


class TestCLI:
    def test_help(self, runner):
        result = runner.invoke(cli.app, ["scrappy", "--no-input"])
        assert result.exit_code == 0 and "details" in result.output
        assert "Neo4j" not in result.output

    @pytest.mark.parametrize("query,matches", [("logic", True), ("MATH", False)])
    def test_search(self, offerings, query, matches, runner):
        result = runner.invoke(cli.app, ["scrappy", "list", str(offerings), "--query", query])
        assert result.exit_code == 0, result.output
        assert ("COMP3400" in result.output) is matches

    def test_menu(self, tmp_path, monkeypatch, pipe, runner, tty):
        html, offerings, output = (
            tmp_path / "search.html",
            tmp_path / "links.csv",
            tmp_path / "courses",
        )
        html.write_text(LISTING)
        scraper.export_links(offerings, html=html)
        html.write_text(LISTING.replace("COMP3400", "CSSE2002").replace("Logic", "Software"))
        monkeypatch.setattr(scrappy, "sys", tty)
        monkeypatch.setattr(scraper, "fetch", lambda *args, **kwargs: COURSE)
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

    @pytest.mark.parametrize("course,exit_code", [("csse2002", 0), ("NONE0000", 2)])
    def test_export(self, tmp_path, monkeypatch, offerings, course, exit_code, runner):
        output = tmp_path / "one.csv"
        monkeypatch.setattr(scraper, "fetch", lambda *args, **kwargs: COURSE)
        result = runner.invoke(
            cli.app,
            [
                "scrappy",
                "details",
                str(offerings),
                "--course",
                course,
                "--jobs",
                "2",
                "-o",
                str(output),
            ],
        )
        assert result.exit_code == exit_code, result.output
        assert "Traceback" not in result.output
        if exit_code == 0:
            assert len(output.read_text().splitlines()) == 2
        else:
            assert "not in" in result.output and not output.exists()
