"""Shared test inputs, isolated state and terminal setup"""

from __future__ import annotations

from pathlib import Path

import pytest

from uq_minis.minis.scrappy import scraper


@pytest.fixture
def offerings(tmp_path: Path, courses: None):
    html, csv = tmp_path / "search.html", tmp_path / "links.csv"
    listing = '<h2 class="trigger"><a class="code">COMP3400</a><a class="title">Logic</a></h2><a href="/course.html?course_code=COMP3400">View all previous offerings</a>'
    html.write_text(listing + listing.replace("COMP3400", "CSSE2002"))
    scraper.export_links(csv, html=html)
    return csv


@pytest.fixture
def courses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(scraper, "STATE", tmp_path / ".minis")
