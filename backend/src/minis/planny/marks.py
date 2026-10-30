"""Transparent weighted-mark scenarios with explicit PAF, penalties and hurdles

Calculations use reviewed weights and scores, including explicit penalties
and hurdle caps. Results expose incomplete or unsupported rules instead of
claiming to reproduce every course’s official grade calculation
"""

from __future__ import annotations

from typing import Any


def calculate(
    course: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    target: float,
    estimate: float = 75,
) -> dict[str, Any]:
    """Estimate marks from reviewed inputs without evaluating arbitrary course rules

    PAF multiplies a group-project percentage before a percentage-point penalty
    Adjusted marks are bounded to 0–100; drop-lowest only supports equal-weight groups
    Unsupported policy wording must remain unverified rather than becoming a formula
    """
    warnings: list[str] = []
    weight = sum(item["weight"] for item in items)
    if abs(weight - 100) > 0.001:
        warnings.append(
            f"Assessment weights total {weight:g}%; complete the profile before relying on this estimate"
        )
    if not course["verified"]:
        warnings.append("Profile rules need review; this is a planning estimate")
    group = (
        [item for item in items if item["group"] == course["drop_group"]]
        if course["drop_group"]
        else []
    )
    drop = int(course["drop_count"])
    group_ids = {item["id"] for item in group}
    if drop and (not group or drop >= len(group) or len({item["weight"] for item in group}) != 1):
        return {
            "warnings": [
                *warnings,
                "Drop-lowest requires a named group of equal-weight assessments and at least one retained result",
            ],
            "projection": None,
            "low": None,
            "high": None,
            "required": None,
            "completed": 0,
            "count": len(items),
        }

    def total(fallback: float) -> float:
        percentages = {
            item["id"]: max(
                0.0,
                min(
                    100.0,
                    (fallback if item["score"] is None else item["score"] / item["maximum"] * 100)
                    * item["factor"]
                    - item["penalty"],
                ),
            )
            for item in items
        }
        omitted = {
            item["id"] for item in sorted(group, key=lambda item: percentages[item["id"]])[:drop]
        }
        multiplier = len(group) / (len(group) - drop) if drop else 1
        score = sum(
            percentages[item["id"]]
            * item["weight"]
            / 100
            * (multiplier if drop and item["id"] in group_ids else 1)
            for item in items
            if item["id"] not in omitted
        )
        if any(
            item["hurdle"] is not None and percentages[item["id"]] < item["hurdle"]
            for item in items
        ):
            score = min(score, course["hurdle_cap"])
        return min(100.0, score)

    low, high = total(0), total(100)
    required: float | None = None
    if high + 1e-8 >= target:
        left, right = 0.0, 100.0
        for _ in range(40):
            midpoint = (left + right) / 2
            if total(midpoint) + 1e-8 >= target:
                right = midpoint
            else:
                left = midpoint
        required = round(right, 2)
    return {
        "projection": round(total(estimate), 2),
        "low": round(low, 2),
        "high": round(high, 2),
        "required": required,
        "warnings": warnings,
        "completed": sum(item["score"] is not None for item in items),
        "count": len(items),
        "pass_mark": course["pass_mark"],
    }
