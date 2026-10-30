"""Conservative prerequisite checks and plain-language course search

Prerequisites are evaluated only when their course-code expression is
unambiguous. Official wording, assumed knowledge and skill evidence remain
visible when readiness cannot be determined from completed courses alone
"""

from __future__ import annotations

import re
from typing import Any

from uq_minis.minis.scrappy.http import CODE

STOP = set(
    "i me my want would like find show courses course a an the about for to in of can do take study with and that are is some please now right".split()
)
SYNONYMS = {
    "coding": "programming software",
    "compsci": "computer science computing software programming",
    "ai": "artificial intelligence",
    "stats": "statistics statistical",
    "psych": "psychology psychological",
    "business": "business management commerce",
    "maths": "mathematics mathematical",
}
SUBJECTS = {
    "compsci": {"CSSE": 8, "COMP": 8, "INFS": 5, "DECO": 3},
}
TOPICS = {
    "Programming": r"\b(programming|coding)\b",
    "Python": r"\bpython\b",
    "Java": r"\bjava\b",
    "Calculus": r"\bcalculus\b",
    "Linear algebra": r"\blinear algebra\b",
    "Statistics": r"\b(statistics|statistical)\b",
    "Probability": r"\bprobability\b",
    "Academic writing": r"\b(academic writing|essay[s]?|writing skills)\b",
    "Research methods": r"\bresearch (methods|design)\b",
    "Data analysis": r"\bdata (analysis|analytics)\b",
    "Communication": r"\b(communication|presentation skills)\b",
    "Chemistry": r"\bchemistry\b",
    "Biology": r"\b(biology|biological)\b",
    "Physics": r"\bphysics\b",
    "Economics": r"\b(economics|economic)\b",
    "Accounting": r"\baccounting\b",
    "Critical thinking": r"\bcritical (thinking|analysis)\b",
    "Design": r"\bdesign\b",
}


def check(details: dict[str, Any], completed: list[str], skills: str = "") -> dict[str, Any]:
    """Evaluate only unambiguous code expressions and preserve the official wording"""
    wording = str(details.get("Pre-Requisites", "")).strip()
    known = set(completed)
    required = list(dict.fromkeys(CODE.findall(wording.upper())))
    blocked = sorted(
        known.intersection(CODE.findall(str(details.get("Incompatibles", "")).upper()))
    )
    result: dict[str, Any] = {
        "wording": wording,
        "assumed": str(details.get("Assumed Background", "")),
        "required": required,
        "completed": sorted(known.intersection(required)),
        "known": sorted(known),
        "missing": [],
        "status": "review",
        "notice": "This checks published prerequisites, not enrolment permission",
        "restrictions": str(details.get("Restricted", "")),
        "incompatible": blocked,
    }
    if blocked:
        result["status"] = "incompatible"
    elif wording.casefold() in {"none", "nil", "no prerequisites", "no prerequisites."}:
        result["status"] = "ready"
    elif required:
        expression = re.sub(r"\bAND\b", "&", wording.upper())
        expression = re.sub(r"\bOR\b", "|", expression)
        expression = expression.replace(",", "&").replace("/", "|")
        tokens = re.findall(r"[A-Z]{4}\d{4}[A-Z]?|[&|()]", expression)
        # Non-code conditions stay manual rather than becoming an enrolment promise
        if (
            len(tokens) > 200
            or expression.count("(") > 20
            or re.sub(r"[A-Z]{4}\d{4}[A-Z]?|[&|()\s.]", "", expression)
        ):
            tokens = []
        position = 0

        def atom() -> bool:
            nonlocal position
            if position >= len(tokens):
                raise ValueError
            token = tokens[position]
            position += 1
            if token == "(":
                value = either()
                if position >= len(tokens) or tokens[position] != ")":
                    raise ValueError
                position += 1
                return value
            if not CODE.fullmatch(token):
                raise ValueError
            return token in known

        def both() -> bool:
            nonlocal position
            value = atom()
            while position < len(tokens) and tokens[position] == "&":
                position += 1
                other = atom()
                value = value and other
            return value

        def either() -> bool:
            nonlocal position
            value = both()
            while position < len(tokens) and tokens[position] == "|":
                position += 1
                other = both()
                value = value or other
            return value

        try:
            satisfied = either()
            if position != len(tokens):
                raise ValueError
            result["status"] = "ready" if satisfied else "missing"
            result["missing"] = (
                [] if satisfied else [code for code in required if code not in known]
            )
        except ValueError:
            pass
    if result["restrictions"] and result["status"] == "ready":
        result["status"] = "review"
    words = set(re.findall(r"[\w-]{3,}", skills.casefold()))
    description = str(details.get("Description", "")).casefold()
    result["skills"] = sorted(word for word in words if word in description)[:15]
    background = " ".join((description, result["assumed"].casefold(), wording.casefold()))
    result["topics"] = [name for name, pattern in TOPICS.items() if re.search(pattern, background)]
    return result


def intent(query: str) -> dict[str, Any]:
    """Extract transparent search terms and supported filters without a remote model"""
    clean = query.casefold()
    clean = re.sub(r"\b(?:comp(?:uter)?\s+sci(?:ence)?|comp[- ]?sci)\b", "compsci", clean)
    metric, order = "code", "asc"
    if re.search(r"\b(easy|easiest|hard|hardest|difficult|difficulty)\b", clean):
        metric = "difficulty"
        order = "desc" if re.search(r"\b(hard|hardest|difficult)\b", clean) else "asc"
    elif re.search(r"\b(fun|funniest|enjoyable)\b", clean):
        metric, order = "fun", "desc"
    elif re.search(r"\b(useful|usefulness|practical)\b", clean):
        metric, order = "usefulness", "desc"
    elif re.search(r"\b(best|highest|worst|lowest|rated|rating)\b", clean):
        metric = "overall"
        order = "asc" if re.search(r"\b(worst|lowest)\b", clean) else "desc"
    level = next(
        (
            index
            for index, word in enumerate(("first", "second", "third", "fourth"), 1)
            if re.search(rf"\b{word}[- ]year\b", clean)
        ),
        None,
    )
    clean = re.sub(r"\b(first|second|third|fourth)\s*[- ]?year\b", "", clean)
    semester = re.search(r"\b(?:semester|sem)\s*([12])\b", clean)
    clean = re.sub(r"\b(?:semester|sem)\s*[12]\b", "", clean)
    modifiers = set(
        "easy easiest hard hardest difficult difficulty fun funniest enjoyable useful usefulness practical best highest worst lowest rated rating ready eligible".split()
    )
    words = [word for word in re.findall(r"[\w-]+", clean) if word not in STOP | modifiers]
    codes = CODE.findall(query.upper())
    return {
        "terms": words,
        "codes": codes,
        "level": level,
        "semester": semester[1] if semester else "",
        "metric": metric,
        "order": order,
    }


def relevance(row: dict[str, Any], words: list[str]) -> float:
    """Require every topic while allowing common subject-language synonyms"""
    code = str(row.get("code", "")).upper()
    title = f"{code} {row.get('name', '')}".casefold()
    body = f"{title} {row.get('description', '')} {row.get('faculty', '')}".casefold()
    score = 0.0
    for word in words:
        alternatives = [word, *SYNONYMS.get(word, "").split()]
        subject = next(
            (
                weight
                for prefix, weight in SUBJECTS.get(word, {}).items()
                if code.startswith(prefix)
            ),
            0,
        )
        if not subject and not any(term in body for term in alternatives):
            return -1
        score += subject or (2 if any(term in title for term in alternatives) else 1)
    return score
