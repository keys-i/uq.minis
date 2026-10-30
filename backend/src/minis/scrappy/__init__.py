"""Explore course offerings, requirements and assessment, then export a shortlist

Export the course parser and catalogue operations as lazy public values
CLI presentation remains in cli.scrappy, and importing the mini does not
fetch a catalogue or load optional browser dependencies
"""

lazy from uq_minis.minis.scrappy.scraper import (
    export_details,
    export_links,
    list_courses,
    load_offerings,
    parse_course,
    parse_offerings,
    scrape_details,
    scrape_offerings,
)

__all__ = [
    "export_details",
    "export_links",
    "list_courses",
    "load_offerings",
    "parse_course",
    "parse_offerings",
    "scrape_details",
    "scrape_offerings",
]
