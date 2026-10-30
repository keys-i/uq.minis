"""Interpret everyday search wording against existing catalogue text

Matching stays local and bounded, supports topic alternatives and exclusions,
and never makes a network request or changes private state
"""

from __future__ import annotations

import re
import tomllib
import unicodedata
from importlib.resources import files

from uq_minis.core.common import MiniError

LANGUAGE = tomllib.loads(files("uq_minis.assets").joinpath("search.toml").read_text())


def terms(query: str, domain: str = "") -> list[tuple[list[str], bool]]:
    """Compile positive topics and explicitly excluded topics once per search"""
    if len(query) > 500:
        raise MiniError("Keep your search within 500 characters")
    stop = set((LANGUAGE["stop"] + " " + LANGUAGE["domains"].get(domain, "")).split())
    result: list[tuple[list[str], bool]] = []
    excluded = either = False
    for word in re.findall(r"[\w]+", unicodedata.normalize("NFKC", query).casefold()):
        if word in {"not", "without", "except", "excluding"}:
            excluded = True
        elif word == "or":
            either = True
        elif word in {"but", "with"}:
            excluded = False
        elif word not in stop:
            alternatives = next(
                (values for values in LANGUAGE["synonyms"].values() if word in values), [word]
            )
            if either and result and result[-1][1] == excluded:
                result[-1] = ([*result[-1][0], *alternatives], excluded)
            else:
                result.append((alternatives, excluded))
            either = False
    return result


def matches(text: str, topics: list[tuple[list[str], bool]]) -> bool:
    """Require each requested topic and reject explicitly excluded topics"""
    normal = unicodedata.normalize("NFKC", text).casefold()
    return all(any(word in normal for word in words) != excluded for words, excluded in topics)
