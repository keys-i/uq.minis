from __future__ import annotations

import csv
import threading

import httpx
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

    class Client:
        def __init__(self, **kwargs):
            self.urls = []
            clients.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, **kwargs):
            self.urls.append(url)
            return httpx.Response(
                200, text=COURSE.replace("COMP3400", url[-8:]), request=httpx.Request("GET", url)
            )

    monkeypatch.setattr(scraper.httpx, "Client", Client)
    assert len(scrape_details([first, second, first])) == 2
    assert len(clients) == 1
    assert sorted(clients[0].urls) == [first, second]


def test_changed_pages_and_untrusted_urls_are_rejected(monkeypatch):
    with pytest.raises(MiniError, match="No course offerings"):
        parse_offerings("<h1>Maintenance</h1>")
    with pytest.raises(MiniError, match="No course title"):
        parse_course("<p id=course-level>Undergraduate</p>")
    with pytest.raises(MiniError, match="Offering URLs"):
        scrape_details(["http://localhost/course.html"])
    monkeypatch.setattr(
        scraper.httpx.Client,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(scraper.httpx.ConnectError("offline")),
    )
    monkeypatch.setattr("uq_minis.minis.scrappy.http.time.sleep", lambda _: None)
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


def test_parser_handles_nested_tags_classes_line_breaks_and_duplicates():
    rows = parse_offerings((LISTING + LISTING).replace('class="code"', 'class="code selected"'))
    assert len(rows) == 1
    details = parse_course(
        '<h1 id="course-title">Logic (COMP3400)</h1>'
        '<div id="course-contact">Lecture<div>2 hours</div>Tutorial<br/>1 hour</div><p>Outside</p>'
        '<div id="course-studyabroad">Approved</div>'
    )
    assert details["Class Hours"] == "Lecture 2 hours Tutorial 1 hour"
    assert details["Study Abroad"] == "Approved"


def test_fetch_retries_transient_status_but_rejects_untrusted_redirect(monkeypatch):
    attempts = []

    def respond(request):
        attempts.append(str(request.url))
        return (
            httpx.Response(503, headers={"Retry-After": "0"})
            if len(attempts) == 1
            else httpx.Response(200, text=COURSE)
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert "COMP3400" in scraper.fetch(
            "https://programs-courses.uq.edu.au/course.html?course_code=COMP3400", client=client
        )
    assert len(attempts) == 2
    attempts.clear()

    def redirect(request):
        attempts.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://localhost/private"})

    with httpx.Client(transport=httpx.MockTransport(redirect)) as client:
        with pytest.raises(MiniError, match="UQ"):
            scraper.fetch(
                "https://programs-courses.uq.edu.au/course.html?course_code=COMP3400", client=client
            )
    assert len(attempts) == 1


def test_parallel_scrapes_are_bounded_deduplicated_and_ordered(monkeypatch):
    barrier = threading.Barrier(2)
    urls = [
        f"https://programs-courses.uq.edu.au/course.html?course_code=TEST{n:04}" for n in range(4)
    ]

    def fetch(url, **kwargs):
        barrier.wait(timeout=3)
        return COURSE.replace("COMP3400", url[-8:])

    monkeypatch.setattr(scraper, "fetch", fetch)
    assert [row["Course Code"] for row in scrape_details([*urls, urls[0]], jobs=2)] == [
        url[-8:] for url in urls
    ]


def test_failed_export_resumes_without_refetching_completed_courses(tmp_path, monkeypatch):
    offerings, output = tmp_path / "links.csv", tmp_path / "courses.csv"
    write_csv(
        offerings,
        OFFERING_FIELDS,
        [
            {
                "course_code": code,
                "course_name": code,
                "offering_link": f"https://programs-courses.uq.edu.au/course.html?course_code={code}",
            }
            for code in ("COMP3400", "CSSE2002")
        ],
    )
    output.write_text("existing export\n")
    calls = []

    def first(url, **kwargs):
        calls.append(url[-8:])
        if url.endswith("CSSE2002"):
            raise MiniError("temporary failure")
        return COURSE

    monkeypatch.setattr(scraper, "fetch", first)
    with pytest.raises(MiniError, match="resume"):
        scraper.export_details(offerings, output, jobs=1)
    assert output.read_text() == "existing export\n"
    calls.clear()

    def second(url, **kwargs):
        calls.append(url[-8:])
        return COURSE.replace("COMP3400", "CSSE2002")

    monkeypatch.setattr(scraper, "fetch", second)
    assert scraper.export_details(offerings, output, jobs=1) == 2
    assert calls == ["CSSE2002"]
    with output.open() as file:
        assert [row["Course Code"] for row in csv.DictReader(file)] == ["COMP3400", "CSSE2002"]


def test_uq_suffix_codes_and_mismatched_links_preserve_existing_csv(tmp_path):
    # UQ currently lists courses such as ACCT1101E and AGRC1135D.
    html, output = tmp_path / "search.html", tmp_path / "links.csv"
    html.write_text(LISTING.replace("COMP3400", "ACCT1101E"))
    assert scraper.export_links(output, html=html) == 1
    assert parse_course(COURSE.replace("COMP3400", "ACCT1101E"))["Course Code"] == "ACCT1101E"
    assert scraper.load_offerings(output)[0]["course_code"] == "ACCT1101E"
    saved = output.read_bytes()
    html.write_text(LISTING.replace("course_code=COMP3400", "course_code=CSSE2002"))
    with pytest.raises(MiniError, match="match"):
        scraper.export_links(output, html=html)
    assert output.read_bytes() == saved


def test_live_search_follows_pagination_and_deduplicates(monkeypatch):
    pages = iter(
        [
            LISTING + '<a rel="next" href="/search.html?page=2">Next</a>',
            LISTING + LISTING.replace("COMP3400", "CSSE2002"),
        ]
    )
    monkeypatch.setattr(scraper, "fetch", lambda *args, **kwargs: next(pages))
    assert [row["course_code"] for row in scraper.scrape_offerings()] == ["COMP3400", "CSSE2002"]


def test_concurrent_exports_reject_same_destination(tmp_path, monkeypatch):
    html, offerings, output = tmp_path / "search.html", tmp_path / "links.csv", tmp_path / "out.csv"
    html.write_text(LISTING)
    scraper.export_links(offerings, html=html)
    entered, release = threading.Event(), threading.Event()

    def fetch(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return COURSE

    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(scraper, "fetch", fetch)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(scraper.export_details, offerings, output)
        try:
            assert entered.wait(timeout=3)
            with pytest.raises(MiniError, match="Another"):
                scraper.export_details(offerings, output)
        finally:
            release.set()
        assert pending.result() == 1


def test_access_denial_stops_batch_without_retrying_every_course(tmp_path, monkeypatch):
    offerings = tmp_path / "links.csv"
    rows = [
        {
            "course_code": code,
            "course_name": code,
            "offering_link": f"https://programs-courses.uq.edu.au/course.html?course_code={code}",
        }
        for code in ("COMP3400", "CSSE2002", "MATH1061")
    ]
    write_csv(offerings, OFFERING_FIELDS, rows)
    attempts = []

    def denied(self, url, **kwargs):
        attempts.append(url)
        return httpx.Response(403, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", denied)
    with pytest.raises(MiniError, match="403"):
        scraper.export_details(offerings, tmp_path / "out.csv", jobs=1)
    assert len(attempts) == 1
