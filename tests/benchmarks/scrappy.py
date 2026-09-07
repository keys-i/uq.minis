"""Compare sequential and concurrent scraping with a local HTTP transport."""

import json
import statistics
import time
from unittest.mock import patch

import httpx

from uq_minis.minis.scrappy import scrape_details


def main() -> None:
    """Measure five runs of 32 courses with 10 ms simulated network latency per request."""
    real_client = httpx.Client
    urls = [
        f"https://programs-courses.uq.edu.au/course.html?course_code=TEST{n:04}" for n in range(32)
    ]

    def respond(request):
        time.sleep(0.01)
        return httpx.Response(
            200, text=f'<h1 id="course-title">Example ({request.url.params["course_code"]})</h1>'
        )

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    timings = {}
    expected = [url[-8:] for url in urls]
    with patch("uq_minis.minis.scrappy.scraper.httpx.Client", side_effect=client):
        for jobs in (1, 4):
            samples = []
            for _ in range(5):
                start = time.perf_counter()
                rows = scrape_details([*urls, urls[0]], jobs=jobs)
                samples.append((time.perf_counter() - start) * 1000)
                assert [row["Course Code"] for row in rows] == expected
            timings[f"jobs_{jobs}"] = {
                "median_ms": round(statistics.median(samples), 2),
                "samples_ms": [round(sample, 2) for sample in samples],
            }
    print(json.dumps(timings, indent=2))


if __name__ == "__main__":
    main()
