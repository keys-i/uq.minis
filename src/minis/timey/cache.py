"""Media identities and coverage rules for Timey's shared file cache"""

import hashlib
import re
from pathlib import Path

from uq_minis.core import cache


def identity(url: str, height: int, audio: bool) -> str:
    """Keep quality, audio and canonical video identity separate"""
    return hashlib.sha256(f"v1:{url}:{0 if audio else height}:{audio}".encode()).hexdigest()[:16]


def find(root: Path, key: str, start: int, seconds: int | None, work: Path):
    """Reuse a complete clip or a covering range from the same starting timestamp"""
    for data, path in cache.entries(root, key):
        try:
            if (
                not re.fullmatch(r"media\.(mp4|webm|mkv|m4a|mp3|opus|ogg|wav|aac)", path.name)
                or data["start"] != start
                or type(data["start"]) is not int
                or not isinstance(data["title"], str)
                or type(data["complete"]) is not bool
                or not data["complete"]
                and (seconds is None or data["seconds"] < seconds)
            ):
                continue
            target = work / f"source{path.suffix}"
            cache.reuse(path, target)
            return target, data["title"]
        except OSError, ValueError, KeyError, TypeError:
            continue
    return None


def save(
    root: Path,
    key: str,
    source: Path,
    title: str,
    start: int,
    seconds: int | None,
    complete: bool,
):
    """Describe a completed clip for atomic storage under the shared cache budgets"""
    suffix = hashlib.sha256(f"{start}:{seconds}".encode()).hexdigest()[:16]
    cache.save(
        root,
        f"{key}-{suffix}",
        source,
        {
            "file": f"media{source.suffix}",
            "title": title[:500],
            "start": start,
            "seconds": seconds,
            "complete": complete,
        },
    )
