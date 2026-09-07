from __future__ import annotations

import pytest

from uq_minis.helper.common import MiniError
from uq_minis.minis.scrappy import scraper
from uq_minis.minis.scrappy.scraper import (
    OFFERING_FIELDS,
    parse_course,
    parse_offerings,
    scrape_details,
    write_csv,
)

LISTING = """
<h2 class="item trigger"><a class="code">COMP3400</a><a class="title">Functional Logic</a></h2>
<a href="/course.html?course_code=COMP3400">View all previous offerings</a>
<h2 class="trigger campus-container"><a class="code">SKIP1000</a></h2>
"""
COURSE = """
<h1 id="course-title">Functional Logic (COMP3400)</h1><p id="course-level">Undergraduate</p>
<p id="course-prerequisite">MATH1061 or CSSE2002</p><p id="course-contact">Lecture 2 Hours/ Week<br> Tutorial 1 Hour/ Week</p>
<p id="course-summary">An introduction to logic.</p><a class="profile-available" href="https://profile.example/1">Course Profile</a>
"""


def test_parsers_preserve_course_data_and_skip_non_course_headers():
    assert parse_offerings(LISTING) == [
        {
            "course_code": "COMP3400",
            "course_name": "Functional Logic",
            "offering_link": "https://programs-courses.uq.edu.au/course.html?course_code=COMP3400",
        }
    ]
    course = parse_course(COURSE)
    assert course["Course Code"] == "COMP3400"
    assert course["Pre-Requisites"] == "MATH1061 or CSSE2002"
    assert course["Course Profile1"] == "https://profile.example/1"


def test_details_deduplicates_urls_and_does_not_fetch_injected_pages(monkeypatch):
    url = "https://programs-courses.uq.edu.au/course.html?course_code=COMP3400"
    assert len(scrape_details([url, url], pages={url: COURSE})) == 1
    monkeypatch.setattr(scraper.httpx, "Client", lambda **kwargs: pytest.fail("must not connect"))
    with pytest.raises(MiniError, match="No supplied page"):
        scrape_details([url], pages={})


def test_details_reuses_one_client_for_unique_urls(monkeypatch):
    first = "https://programs-courses.uq.edu.au/course.html?course_code=COMP3400"
    second = "https://programs-courses.uq.edu.au/course.html?course_code=CSSE2002"
    clients = []

    class Response:
        text = COURSE

        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, **kwargs):
            self.urls = []
            clients.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            self.urls.append(url)
            return Response()

    monkeypatch.setattr(scraper.httpx, "Client", Client)
    assert len(scrape_details([first, second, first])) == 2
    assert len(clients) == 1
    assert clients[0].urls == [first, second]


def test_changed_pages_and_untrusted_urls_are_rejected(monkeypatch):
    with pytest.raises(MiniError, match="No course offerings"):
        parse_offerings("<h1>Maintenance</h1>")
    with pytest.raises(MiniError, match="No course title"):
        parse_course("<p id=course-level>Undergraduate</p>")
    with pytest.raises(MiniError, match="Offering URLs"):
        scrape_details(["http://localhost/course.html"])
    monkeypatch.setattr(
        scraper.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(scraper.httpx.ConnectError("offline")),
    )
    with pytest.raises(MiniError, match="Cannot fetch"):
        scraper.fetch("https://programs-courses.uq.edu.au/course.html?course_code=COMP3400")


def test_nested_fields_do_not_absorb_following_content():
    course = parse_course(
        "<h1 id=course-title>Logic (COMP3400)</h1>"
        "<div id=course-level>Undergraduate <span>course</span></div><p>Outside</p>"
    )
    assert course["Course Level"] == "Undergraduate course"


def test_offering_export_writes_csv(tmp_path):
    output = tmp_path / "offerings.csv"
    write_csv(output, OFFERING_FIELDS, parse_offerings(LISTING))
    assert output.read_text(encoding="utf-8").splitlines()[1].startswith("COMP3400,")


def test_csv_failure_preserves_existing_export(tmp_path):
    output = tmp_path / "offerings.csv"
    output.write_text("old\n", encoding="utf-8")

    def broken_rows():
        yield {"course_code": "COMP3400"}
        raise RuntimeError("stop")

    with pytest.raises(RuntimeError, match="stop"):
        write_csv(output, OFFERING_FIELDS, broken_rows())
    assert output.read_text(encoding="utf-8") == "old\n"
    assert not list(tmp_path.glob(".offerings.csv.*"))


def test_shared_exports_validate_input_and_return_counts(tmp_path, monkeypatch):
    html, offerings, output = (
        tmp_path / name for name in ("search.html", "links.csv", "courses.csv")
    )
    html.write_text(LISTING)
    assert scraper.export_links(offerings, html=html) == 1
    monkeypatch.setattr(scraper, "fetch", lambda *args, **kwargs: COURSE)
    assert scraper.export_details(offerings, output) == 1
    saved = output.read_bytes()
    offerings.write_text("wrong_column\nvalue\n")
    with pytest.raises(MiniError, match="offering_link"):
        scraper.export_details(offerings, output)
    assert output.read_bytes() == saved
