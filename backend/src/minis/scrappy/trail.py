"""Bounded prerequisite graphs retaining shared branches and official wording

Expand only actual course references, keeping alternative requirements and
shared branches visible. Depth, node and upstream-read limits bound cycles
and a denied request leaves checked requirements intact
"""

from collections.abc import Callable
from typing import Any

from uq_minis.core.common import MiniError
from uq_minis.minis.scrappy.http import CODE, CatalogueUnavailable


def build(
    code: str, courses: list[dict[str, Any]], read: Callable[[str], dict[str, Any]]
) -> dict[str, Any]:
    """Follow actual course references with bounded reads and cycle protection"""
    code = code.strip().upper()
    if not CODE.fullmatch(code):
        raise MiniError("Choose a valid UQ course code")
    known = {row["code"]: row for row in courses}
    pending = [(code, 0)]
    nodes: dict[str, dict[str, Any]] = {}
    reads = 0
    limited = False
    for current, depth in pending:
        if current in nodes:
            continue
        if len(nodes) >= 80:
            limited = True
            break
        saved = known.get(current, {})
        details = saved.get("requirements", {})
        error = ""
        if not details and reads < 16 and depth < 8:
            reads += 1
            try:
                details = read(current)["details"]
            except MiniError as exc:
                error = str(exc)
                if isinstance(exc, CatalogueUnavailable):
                    reads = 16
        wording = str(details.get("Pre-Requisites", ""))
        required = list(dict.fromkeys(CODE.findall(wording.upper())))
        nodes[current] = {
            "code": current,
            "name": details.get("Course Name") or saved.get("name", current),
            "wording": wording,
            "required": required,
            "loaded": bool(details),
            "error": error,
            "depth": depth,
        }
        if depth < 8:
            pending.extend((item, depth + 1) for item in required)
        elif required:
            limited = True
        if not details and not error:
            limited = True
    return {"root": code, "nodes": list(nodes.values()), "limited": limited}
