"""Bounded Microsoft Translator reads for public university information

Only supported language codes and bounded text reach the configured provider
Completed Unicode runs are cached in memory; failures retain retry timing
without exposing credentials or consuming capacity that never started
"""

from __future__ import annotations

import json
import os
from email.utils import parsedate_to_datetime
from functools import lru_cache
from importlib.resources import files
from math import ceil
from threading import Lock, Semaphore
from time import monotonic, time
from typing import cast

import httpx

from uq_minis.core.common import MiniError

LANGUAGES = cast(
    dict[str, str],
    json.loads(files("uq_minis.assets").joinpath("languages.json").read_text(encoding="utf-8")),
)
_lock = Lock()
_window = monotonic()
_characters = 0
_active = Semaphore(2)
_retry = 0.0


class Unavailable(MiniError):
    """Keep translation failures actionable without exposing provider credentials"""

    def __init__(self, message: str, *, status: int = 503, retry: int = 0) -> None:
        """Describe the failure and the provider's minimum wait before retrying"""
        super().__init__(message)
        self.status = status
        self.retry = retry


def configured() -> bool:
    """Report credentials without exposing their values"""
    return bool(os.getenv("MINIS_TRANSLATE_KEY") and os.getenv("MINIS_TRANSLATE_REGION"))


@lru_cache(maxsize=128)
def text(original: str, target: str, source: str = "auto") -> str:
    """Translate complete Unicode runs and cap uncached provider use per day"""
    global _window, _characters, _retry
    if target not in LANGUAGES or source != "auto" and source not in LANGUAGES:
        raise MiniError("Choose supported source and target languages")
    if not original.strip() or len(original) > 4000:
        raise MiniError("Choose a supported language and at most 4,000 characters")
    if source == target:
        return original
    if not configured():
        raise Unavailable(
            "Server translation is not connected; use on-device translation or see docs/access.md"
        )
    if not _active.acquire(blocking=False):
        raise Unavailable(
            "Translation is busy; the original text is still available", status=429, retry=2
        )
    try:
        with _lock:
            if _retry > monotonic():
                raise Unavailable(
                    "Translation is resting after a provider limit; try again shortly",
                    status=429,
                    retry=max(1, int(_retry - monotonic()) + 1),
                )
            if monotonic() - _window >= 86400:
                _characters, _window = 0, monotonic()
            if _characters + len(original) > 60000:
                raise Unavailable(
                    "Today's translation budget is used; the original text is still available",
                    status=429,
                    retry=max(1, int(86400 - (monotonic() - _window)) + 1),
                )
            _characters += len(original)
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            with client.stream(
                "POST",
                "https://api.cognitive.microsofttranslator.com/translate",
                params={
                    "api-version": "3.0",
                    "to": target,
                    "textType": "plain",
                    **({"from": source} if source != "auto" else {}),
                },
                headers={
                    "Ocp-Apim-Subscription-Key": os.environ["MINIS_TRANSLATE_KEY"],
                    "Ocp-Apim-Subscription-Region": os.environ["MINIS_TRANSLATE_REGION"],
                },
                json=[{"Text": original}],
            ) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    delay = response.headers.get("Retry-After", "")
                    try:
                        seconds = (
                            max(1, int(delay))
                            if delay.isdecimal() and len(delay) <= 9
                            else max(1, ceil(parsedate_to_datetime(delay).timestamp() - time()))
                        )
                    except ValueError, TypeError, OverflowError:
                        seconds = 60
                    with _lock:
                        _retry = max(_retry, monotonic() + seconds)
                    raise Unavailable(
                        "Translation provider is busy; the original text is still available",
                        status=429 if response.status_code == 429 else 503,
                        retry=seconds,
                    )
                if response.status_code in {401, 403}:
                    with _lock:
                        _retry = max(_retry, monotonic() + 60)
                    raise Unavailable(
                        "Translation credentials need attention; the original text is still available",
                        retry=60,
                    )
                if response.status_code != 200:
                    raise Unavailable(
                        f"Translation provider returned HTTP {response.status_code}; original text kept"
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 128 * 1024:
                        raise Unavailable(
                            "Translation response exceeded its size limit", status=502
                        )
        result = json.loads(body)[0]["translations"][0]["text"]
        if not isinstance(result, str) or not result.strip() or len(result) > 12000:
            raise Unavailable("Translation response was invalid; original text kept", status=502)
        return result
    except httpx.HTTPError as exc:
        with _lock:
            _retry = max(_retry, monotonic() + 5)
        raise Unavailable("Translation couldn't connect; original text kept", retry=5) from exc
    except MiniError:
        raise
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise Unavailable(
            "Translation response was invalid; original text kept", status=502
        ) from exc
    finally:
        _active.release()
