"""Read recent posts from explicitly authorised club social accounts

Supported platform calls require explicit account configuration and return
a bounded recent page. Normalisation preserves source links without guessing
event dates or treating an incomplete recent feed as a deletion snapshot
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import httpx
from dotenv import dotenv_values

from uq_minis.core.cache import writing
from uq_minis.core.common import MiniError
from uq_minis.core.paths import STATE
from uq_minis.core.web import fetch, trusted

PROVIDERS = {"facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn"}


def _text(value: Any, limit: int = 12000) -> str:
    """Keep external post text bounded and reject unexpected structures"""
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise MiniError("Social source returned invalid or oversized post text")
    return value.strip()


def collect(provider: str, account: str, *, club: str = "") -> list[dict[str, str]]:
    """Read one recent page of up to 100 posts without inferring event dates

    Tokens and supported API versions come from backend environment or private
    Clubby state, and are never copied into requests' URLs or exported records
    """
    if provider not in PROVIDERS or not re.fullmatch(r"[1-9]\d{0,31}", account):
        raise MiniError("Choose Facebook, Instagram or LinkedIn and a numeric account ID")
    club = _text(club, 300) or account
    values = dotenv_values(STATE / "clubby" / ".env")
    token_key = provider.upper() + "_ACCESS_TOKEN"
    token = (os.environ.get(token_key, values.get(token_key)) or "").strip()
    if not token or len(token) > 4096 or any(char.isspace() for char in token):
        raise MiniError(f"Set {token_key} using authorised read access for this account")
    headers = {"Authorization": f"Bearer {token}"}
    if provider == "linkedin":
        key = "LINKEDIN_VERSION"
        version = os.environ.get(key, values.get(key)) or ""
        if not re.fullmatch(r"20\d{2}(?:0[1-9]|1[0-2])", version):
            raise MiniError("Set LINKEDIN_VERSION to a supported YYYYMM API version")
        host, field = "api.linkedin.com", "elements"
        headers.update({
            "LinkedIn-Version": version,
            "X-Restli-Protocol-Version": "2.0.0",
            "X-RestLi-Method": "FINDER",
        })
        url = f"https://{host}/rest/posts?" + urlencode({
            "author": f"urn:li:organization:{account}",
            "q": "author",
            "count": 100,
            "sortBy": "LAST_MODIFIED",
        })
    else:
        key = "META_API_VERSION"
        version = os.environ.get(key, values.get(key)) or ""
        if not re.fullmatch(r"v\d{1,3}\.\d{1,2}", version):
            raise MiniError("Set META_API_VERSION to a supported version from your Meta app")
        host, field = "graph.facebook.com", "data"
        endpoint = "posts" if provider == "facebook" else "media"
        fields = "id,message,permalink_url" if provider == "facebook" else "id,caption,permalink"
        url = f"https://{host}/{version}/{account}/{endpoint}?" + urlencode({
            "fields": fields,
            "limit": 100,
        })
    with httpx.Client(timeout=30, follow_redirects=False, headers=headers) as client:
        body = fetch(url, client=client, hosts=(host,))
    try:
        payload: Any = json.loads(body)
    except ValueError as exc:
        raise MiniError("Social source returned invalid JSON; existing data kept") from exc
    if not isinstance(payload, dict):
        raise MiniError("Social source returned an invalid post collection")
    raw: Any = cast(dict[str, Any], payload).get(field)
    if not isinstance(raw, list) or len(cast(list[Any], raw)) > 100:
        raise MiniError("Social source must return a page of at most 100 posts")
    rows: dict[str, dict[str, str]] = {}
    for item in cast(list[Any], raw):
        if not isinstance(item, dict):
            raise MiniError("Each social post must be an object")
        post = cast(dict[str, Any], item)
        identity = _text(post.get("id"), 100)
        if provider == "linkedin":
            if post.get("author") != f"urn:li:organization:{account}":
                raise MiniError("LinkedIn returned a post for a different organisation")
            if not re.fullmatch(r"urn:li:(?:share|ugcPost):[1-9]\d{0,31}", identity):
                raise MiniError("LinkedIn returned an invalid post ID")
            if post.get("lifecycleState") != "PUBLISHED":
                continue
            text = _text(post.get("commentary"))
            link = f"https://www.linkedin.com/feed/update/{identity}/"
        elif provider == "facebook":
            if not re.fullmatch(re.escape(account) + r"_[1-9]\d{0,31}", identity):
                raise MiniError("Facebook returned an invalid post ID for this Page")
            text = _text(post.get("message"))
            link = trusted(
                _text(post.get("permalink_url"), 4000), ("www.facebook.com", "facebook.com")
            )
        else:
            if not re.fullmatch(r"[1-9]\d{0,31}", identity):
                raise MiniError("Instagram returned an invalid media ID")
            text = _text(post.get("caption"))
            link = trusted(
                _text(post.get("permalink"), 4000), ("www.instagram.com", "instagram.com")
            )
        rows[link] = {
            "title": (text.split("\n", 1)[0] or f"{PROVIDERS[provider]} post")[:300],
            "source": PROVIDERS[provider],
            "club": club,
            "url": link,
            "notes": text,
            "start": "",
            "end": "",
        }
    return list(rows.values())


def export(output: Path, provider: str, account: str, *, club: str = "") -> int:
    """Publish a private JSON export that Buzzy can import without conversion"""
    rows = collect(provider, account, club=club)
    with writing(output.expanduser()) as temporary:
        temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.chmod(0o600)
    return len(rows)
