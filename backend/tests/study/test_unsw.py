import csv
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from uq_minis import cli
from uq_minis.core.common import MiniError
from uq_minis.minis.scrappy import scraper, unsw

HTML = """<ul class="list-group">
<li><a href="/COMP2521/26T3/"><strong>COMP2521</strong> - Data Structures &amp; Algorithms</a></li>
<li><a href="/COMP1511/26T1/"><strong>COMP1511</strong> - Programming Fundamentals</a></li>
<li><a href="/COMP2521/26T3/"><strong>COMP2521</strong> - Data Structures &amp; Algorithms</a></li>
</ul>"""


def test_export_and_browse(
    tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, output = tmp_path / "webcms.html", tmp_path / "courses.csv"
    source.write_text(HTML)
    network = Mock(side_effect=AssertionError("saved HTML must stay offline"))
    monkeypatch.setattr(unsw, "fetch", network)
    result = runner.invoke(
        cli.app,
        ["scrappy", "links", "--university", "unsw", "--html", str(source), "-o", str(output)],
    )
    assert result.exit_code == 0, result.output
    with output.open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2 and rows[0]["term"] == "26T3"
    assert rows[0]["course_name"] == "Data Structures & Algorithms"
    result = runner.invoke(cli.app, ["scrappy", "list", str(output), "--query", "ALGORITHMS"])
    assert result.exit_code == 0 and "COMP2521" in result.output and "COMP1511" not in result.output
    with pytest.raises(MiniError, match="support UQ"):
        scraper.export_details(output, tmp_path / "details.csv")
    assert not network.called


def test_published_terms() -> None:
    assert len(unsw.scrape_offerings(html=HTML, term="26t3")) == 1
    with pytest.raises(MiniError, match="No published"):
        unsw.scrape_offerings(html=HTML, term="25T3")
    with pytest.raises(MiniError, match="must look"):
        unsw.scrape_offerings(html=HTML, term="../../26T3")
    with pytest.raises(MiniError, match="No UNSW"):
        unsw.scrape_offerings(html="<p>Login required</p>")


def test_foreign_source(tmp_path: Path) -> None:
    with pytest.raises(MiniError, match="HTTPS"):
        unsw.scrape_offerings(html=HTML.replace('href="/COMP', 'href="https://evil.example/COMP'))
    with pytest.raises(MiniError, match="matching course"):
        unsw.offering("COMP1511", "Programming", unsw.BASE + "COMP2521/26T3/")
    source = tmp_path / "webcms.html"
    source.write_text(HTML)
    with pytest.raises(MiniError, match="different files"):
        scraper.export_links(source, html=source, university="unsw")
