"""Public StudentVIP rating observations without republishing written reviews

Collect only bounded public rating observations and fingerprints needed to
deduplicate evidence. Written reviews are not republished and an access
denial stops collection rather than triggering a bypass or repeated crawl
"""

from __future__ import annotations

import re
from collections import defaultdict
from hashlib import sha256
from html import unescape
from typing import Any

import httpx

from uq_minis.core.common import MiniError
from uq_minis.core.web import fetch
from uq_minis.minis.scrappy.http import CODE

BASE = "https://studentvip.com.au/uq/subjects"


def parse(html: str) -> tuple[list[tuple[str, float, str]], str]:
    """Read actual star observations and retain only a fingerprint of review text"""
    rows: list[tuple[str, float, str]] = []
    for block in re.findall(r'<div class="subject-rating">(.*?)</div>', html, re.S)[:30]:
        match = re.search(r'href="https://studentvip\.com\.au/uq/subjects/([A-Za-z0-9-]+)"', block)
        if not match:
            raise MiniError("A course rating changed format; saved feedback is still safe")
        if not CODE.fullmatch(match[1].upper()):
            continue
        icons = re.findall(r'<i\s+class="([^"]+)"', block)
        if len(icons) != 5 or any(
            icon not in {"fas fa-star", "far fa-star", "fas fa-star-half-alt"} for icon in icons
        ):
            raise MiniError("A course rating has an incomplete star scale")
        score = sum(
            1.0 if "fas fa-star" == icon else 0.5 if "fa-star-half" in icon else 0.0
            for icon in icons
        )
        if not 1 <= score <= 5:
            raise MiniError("A course rating falls outside its published scale")
        fingerprint = sha256(
            " ".join(unescape(re.sub(r"<[^>]*>", " ", block)).split()).encode()
        ).hexdigest()
        rows.append((match[1].upper(), score, fingerprint))
    next_page = re.search(r'<a\s+href="([^"]+)"\s+rel="next"', html)
    if not rows:
        raise MiniError("More course feedback couldn't be read; saved results are still available")
    return rows, unescape(next_page[1]) if next_page else ""


def collect() -> dict[str, dict[str, Any]]:
    """Collect a complete bounded public index and stop at access denial or changed pagination"""
    scores: dict[str, list[float]] = defaultdict(list)
    seen: set[str] = set()
    url = BASE
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        for page in range(1, 101):
            rows, following = parse(fetch(url, client=client, hosts=("studentvip.com.au",)))
            added = 0
            for code, score, identity in rows:
                if identity not in seen:
                    scores[code].append(score)
                    seen.add(identity)
                    added += 1
            if not added:
                raise MiniError("The feedback index repeated a page; previous results kept")
            if not following:
                return {
                    code: {
                        "mean": round(sum(values) / len(values), 3),
                        "count": len(values),
                        "url": f"{BASE}/{code.lower()}",
                        "source": "StudentVIP",
                    }
                    for code, values in scores.items()
                }
            if following != f"{BASE}?page={page + 1}":
                raise MiniError("The feedback index changed its next page; previous results kept")
            url = following
    raise MiniError("Course feedback exceeds the bounded import; previous results kept")
