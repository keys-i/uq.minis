"""Course exports that return paths and counts instead of whole catalogues."""

from pathlib import Path


def scrappy_links(
    output: Path = Path("courses_offerings.csv"), html: Path | None = None
) -> dict[str, object]:
    """Export course offering links to CSV, replacing output. Optional HTML avoids a web request."""
    from uq_minis.minis.scrappy import export_links

    return {"path": str(output.expanduser().resolve()), "count": export_links(output, html=html)}


def scrappy_details(
    offerings: Path,
    output: Path = Path("courses.csv"),
    course: str | None = None,
    jobs: int = 4,
    fresh: bool = False,
) -> dict[str, object]:
    """Export all courses or one code using 1–8 concurrent requests.

    Failed batches keep the old output and checkpoint successes; repeat to resume.
    Fresh discards the checkpoint. A complete batch replaces the output CSV.
    """
    from uq_minis.minis.scrappy import export_details

    return {
        "path": str(output.expanduser().resolve()),
        "count": export_details(offerings, output, course=course, jobs=jobs, fresh=fresh),
    }


def scrappy_list(
    offerings: Path = Path("courses_offerings.csv"),
    query: str = "",
    offset: int = 0,
    limit: int = 50,
) -> dict[str, object]:
    """Search saved course codes and names; return up to 200 offerings and total match count."""
    from uq_minis.minis.scrappy import list_courses

    return list_courses(offerings, query=query, offset=offset, limit=limit)
