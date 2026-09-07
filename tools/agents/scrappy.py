"""Course exports that return paths and counts instead of whole catalogues."""

from pathlib import Path


def scrappy_links(
    output: Path = Path("courses_offerings.csv"), html: Path | None = None
) -> dict[str, object]:
    """Export course offering links to CSV, replacing output. Optional HTML avoids a web request."""
    from uq_minis.minis.scrappy import export_links

    return {"path": str(output.resolve()), "count": export_links(output, html=html)}


def scrappy_details(offerings: Path, output: Path = Path("courses.csv")) -> dict[str, object]:
    """Fetch unique UQ URLs from an offering CSV and export course details, replacing output."""
    from uq_minis.minis.scrappy import export_details

    return {"path": str(output.resolve()), "count": export_details(offerings, output)}
