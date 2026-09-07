"""Build and optionally submit Microsoft Forms payloads from event TOML"""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from uq_minis.helper.common import MiniError, table, text
from uq_minis.helper.risk_docx import EventConfig

_FORM_HOST = "forms.cloud.microsoft"
_ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*\Z")
_VALUE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_REQUIRED_FORM_VALUES = (
    "affiliated",
    "date_flexibility",
    "under_18",
    "non_uq",
    "venue_capacity",
    "option_28",
    "food",
    "option_30",
    "option_31",
    "option_32",
    "terms",
)


@dataclass(frozen=True, slots=True)
class AnswerSpec:
    """Map one Microsoft Forms question to a template value"""

    question_id: str
    value: str


@dataclass(frozen=True, slots=True)
class FormProfile:
    """Describe one Microsoft Forms request and its answer map"""

    path: Path
    endpoint: str
    referer: str
    origin: str
    ring: str
    language: str
    email_receipt_consent: bool
    answers: tuple[AnswerSpec, ...]
    cookie_env: str
    verification_token_env: str
    session_id_env: str
    muid_env: str


def default_profile_path() -> Path:
    """Return the bundled UQ event-booking form profile"""
    return Path(__file__).resolve().parent / "uq-event-booking.toml"


def _required(mapping: Mapping[str, Any], key: str, *, section: str) -> str:
    """Read a required text value from a TOML table"""
    return text(mapping.get(key), field=f"[{section}].{key}", required=True)


def _forms_url(value: str, *, field: str) -> str:
    """Validate an HTTPS URL for the Forms host"""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != _FORM_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise MiniError(f"{field} must use https://{_FORM_HOST}")
    return value


def _env_name(mapping: Mapping[str, Any], key: str, default: str) -> str:
    """Read a valid environment-variable name"""
    value = text(mapping.get(key, default), field=f"[auth].{key}")
    if not _ENV_NAME.fullmatch(value):
        raise MiniError(f"[auth].{key} must be an environment-variable name")
    return value


def load_form_profile(path: Path | None = None) -> FormProfile:
    """Load the request endpoint, answer map and secret names"""
    resolved = (path or default_profile_path()).expanduser().resolve(strict=False)
    try:
        with resolved.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise MiniError(f"Cannot read form profile {resolved}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise MiniError(f"Invalid form profile TOML in {resolved}: {exc}") from exc

    request = table(data, "request")
    auth = table(data, "auth")
    consent = request.get("email_receipt_consent", False)
    if not isinstance(consent, bool):
        raise MiniError("[request].email_receipt_consent must be true or false")

    raw_answers = data.get("answers")
    if not isinstance(raw_answers, Sequence) or isinstance(raw_answers, (str, bytes)):
        raise MiniError("The form profile needs [[answers]] entries")
    answers: list[AnswerSpec] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_answers, start=1):
        if not isinstance(item, Mapping):
            raise MiniError(f"[[answers]] entry {index} must be a table")
        question_id = _required(item, "question_id", section=f"answers #{index}")
        if question_id in seen:
            raise MiniError(f"Duplicate form question ID: {question_id}")
        seen.add(question_id)
        answers.append(
            AnswerSpec(question_id, text(item.get("value"), field=f"answers #{index}.value"))
        )
    if not answers:
        raise MiniError("The form profile needs at least one [[answers]] entry")

    endpoint = _forms_url(
        _required(request, "endpoint", section="request"), field="[request].endpoint"
    )
    referer = _forms_url(
        _required(request, "referer", section="request"), field="[request].referer"
    )
    origin = _forms_url(
        text(request.get("origin"), field="[request].origin") or f"https://{_FORM_HOST}",
        field="[request].origin",
    )
    return FormProfile(
        path=resolved,
        endpoint=endpoint,
        referer=referer,
        origin=origin,
        ring=text(request.get("ring"), field="[request].ring") or "business",
        language=text(request.get("language"), field="[request].language") or "en-AU,en;q=0.9",
        email_receipt_consent=consent,
        answers=tuple(answers),
        cookie_env=_env_name(auth, "cookie_env", "UQ_FORMS_COOKIE"),
        verification_token_env=_env_name(
            auth, "verification_token_env", "UQ_FORMS_VERIFICATION_TOKEN"
        ),
        session_id_env=_env_name(auth, "session_id_env", "UQ_FORMS_SESSION_ID"),
        muid_env=_env_name(auth, "muid_env", "UQ_FORMS_MUID"),
    )


def _event_date_iso(value: Any) -> str:
    """Convert an event date to ISO format"""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    candidate = text(value, field="[event].date", required=True)
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(candidate, pattern).date().isoformat()
        except ValueError:
            continue
    raise MiniError("[event].date must be YYYY-MM-DD or DD/MM/YYYY")


def _required_schedule(config: EventConfig) -> dict[str, str]:
    """Return every schedule value required by the form"""
    schedule = {
        "setup_start": config.schedule.setup_start,
        "setup_end": config.schedule.setup_end,
        "event_start": config.schedule.event_start,
        "event_end": config.schedule.event_end,
        "pack_up_start": config.schedule.pack_up_start,
        "pack_up_end": config.schedule.pack_up_end,
    }
    missing = [f"[schedule].{key}" for key, value in schedule.items() if not value]
    if missing:
        raise MiniError("Microsoft Form output requires " + ", ".join(missing))
    return schedule


def build_form_context(raw: Mapping[str, Any], config: EventConfig) -> dict[str, str]:
    """Build placeholder values for the bundled answer map"""
    event = table(raw, "event")
    form = table(raw, "form")
    values = form.get("values")
    if not isinstance(values, Mapping):
        raise MiniError("Microsoft Form output requires a [form.values] table")
    missing = [key for key in _REQUIRED_FORM_VALUES if key not in values]
    if missing:
        raise MiniError("Missing [form.values] keys: " + ", ".join(missing))

    campus = text(event.get("campus"), field="[event].campus", required=True)
    room = text(event.get("room"), field="[event].room", required=True)
    required_contact = {
        "coordinator_role": config.coordinator_role,
        "coordinator_email": config.coordinator_email,
        "coordinator_phone": config.coordinator_phone,
    }
    absent = [name for name, value in required_contact.items() if not value]
    if absent:
        raise MiniError("Microsoft Form output requires " + ", ".join(absent))

    context = dict(config.context)
    context.update(
        event_title=config.title,
        event_date_iso=_event_date_iso(event.get("date")),
        summary=config.summary,
        campus=campus,
        room=room,
        **_required_schedule(config),
    )
    for key, value in values.items():
        name = str(key).strip()
        if not _VALUE_NAME.fullmatch(name):
            raise MiniError(f"Invalid [form.values] key: {name!r}")
        context[f"form_{name}"] = text(value, field=f"[form.values].{name}")
    return context


class _StrictContext(dict[str, str]):
    """Reject missing form-profile placeholders"""

    def __missing__(self, key: str) -> str:
        """Raise a helpful error for an unknown placeholder"""
        raise MiniError(f"Unknown form-profile placeholder {{{key}}}")


def _answer_overrides(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return optional answer overrides from event TOML"""
    overrides = table(raw, "form").get("answer_overrides", {})
    if not isinstance(overrides, Mapping):
        raise MiniError("[form.answer_overrides] must be a TOML table")
    return overrides


def build_answers(
    profile: FormProfile,
    context: Mapping[str, str],
    overrides: Mapping[str, Any] | None = None,
) -> list[dict[str, str | None]]:
    """Render profile answers with event values and overrides"""
    overrides = overrides or {}
    known = {answer.question_id for answer in profile.answers}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise MiniError(f"Unknown form answer override(s): {', '.join(unknown)}")

    strict = _StrictContext(context)
    rendered: list[dict[str, str | None]] = []
    for answer in profile.answers:
        raw_value = overrides.get(answer.question_id, answer.value)
        value = text(raw_value, field=f"form answer {answer.question_id}")
        value = value.format_map(strict) if value else ""
        rendered.append({"questionId": answer.question_id, "answer1": value or None})
    return rendered


def _timestamp(value: datetime) -> str:
    """Format a date-time as a millisecond UTC timestamp"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _configured_datetime(raw: Mapping[str, Any], key: str) -> datetime | None:
    """Read an optional ISO date-time from the form section"""
    value = table(raw, "form").get(key)
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (date, time)):
        raise MiniError(f"[form].{key} must be an ISO date-time")
    candidate = text(value, field=f"[form].{key}").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise MiniError(f"[form].{key} must be an ISO date-time") from exc


def build_payload(
    profile: FormProfile,
    answers: Sequence[Mapping[str, str | None]],
    *,
    started_at: datetime | None = None,
    submitted_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the Microsoft Forms request body"""
    submitted = submitted_at or datetime.now(UTC)
    started = started_at or submitted
    if submitted.timestamp() < started.timestamp():
        raise MiniError("[form].submitted_at cannot be earlier than [form].started_at")
    return {
        "startDate": _timestamp(started),
        "submitDate": _timestamp(submitted),
        "answers": json.dumps(list(answers), ensure_ascii=False, separators=(",", ":")),
        "emailReceiptConsent": profile.email_receipt_consent,
    }


def create_payload(
    raw: Mapping[str, Any], config: EventConfig, profile: FormProfile
) -> dict[str, Any]:
    """Create a complete Forms payload from event TOML"""
    answers = build_answers(profile, build_form_context(raw, config), _answer_overrides(raw))
    return build_payload(
        profile,
        answers,
        started_at=_configured_datetime(raw, "started_at"),
        submitted_at=_configured_datetime(raw, "submitted_at"),
    )


def _secret(name: str) -> str:
    """Read one single-line secret from the environment"""
    value = os.environ.get(name, "")
    if not value:
        raise MiniError(f"Missing required environment variable: {name}")
    if "\r" in value or "\n" in value:
        raise MiniError(f"{name} contains a newline")
    return value


def submit_payload(profile: FormProfile, payload: Mapping[str, Any]) -> int:
    """Submit with short-lived browser-session values from the environment"""
    load_dotenv(Path.cwd() / ".env", override=False, interpolate=False)
    headers = {
        "Accept": "application/json",
        "Accept-Language": profile.language,
        "Content-Type": "application/json",
        "Cookie": _secret(profile.cookie_env),
        "Origin": profile.origin,
        "Referer": profile.referer,
        "__requestverificationtoken": _secret(profile.verification_token_env),
        "odata-version": "4.0",
        "odata-maxversion": "4.0",
        "x-correlationid": str(uuid4()),
        "x-ms-form-muid": _secret(profile.muid_env),
        "x-ms-form-request-ring": profile.ring,
        "x-ms-form-request-source": "ms-formweb",
        "x-usersessionid": _secret(profile.session_id_env),
    }
    timeout = httpx.Timeout(20.0, connect=10.0, read=20.0, write=20.0, pool=5.0)
    limits = httpx.Limits(max_connections=2, max_keepalive_connections=1)
    with httpx.Client(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.post(profile.endpoint, headers=headers, json=dict(payload))
        response.raise_for_status()
        return response.status_code
