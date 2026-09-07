"""Persist event-mail progress and resume unfinished work after each restart"""

from __future__ import annotations

import io
import json
import re
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from uq_minis.helper.common import MiniError

from . import helper, run

mail = helper("mail")

DEFAULT_STATE = Path.home() / "Library/Application Support/UQ minis/agent"
_ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}"
_SUBJECT = re.compile(
    rf"^Event Application Update(?P<request> Risk Assessment Request)?\s+"
    rf"\[Event ID:\s*(?P<id>{_ID})\]\s*-\s*(?P<title>.+)$",
    re.IGNORECASE,
)


def now() -> str:
    """Use UTC timestamps that Graph and SQLite can compare"""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    except (TypeError, ValueError) as exc:
        raise MiniError("Microsoft returned an invalid message timestamp") from exc


_db = helper("db")
_setting = _db.setting


@contextmanager
def database(state_dir: Path):
    """Open worker storage and initialize the event workflow tables"""
    with _db.database(state_dir) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
                document BLOB NOT NULL, since TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'waiting_request', request_id TEXT,
                request_time TEXT, draft_id TEXT, send_started TEXT, sent_at TEXT,
                update_id TEXT, update_thread TEXT, update_time TEXT, reply_id TEXT,
                outcome TEXT, details TEXT NOT NULL DEFAULT '', link TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '', last_notice TEXT NOT NULL DEFAULT ''
            );
        """)
        yield db


def _save(db, event_id: str, **values) -> None:
    _db.update(db, "events", "event_id", event_id, **values)


def login(
    *,
    mailbox: str,
    username: str | None = None,
    client_id: str | None = None,
    tenant_id: str | None = None,
    backend: str | None = None,
    state_dir: Path = DEFAULT_STATE,
) -> None:
    """Sign into Outlook web, or Graph when app registration IDs are supplied"""
    backend = backend or ("graph" if client_id or tenant_id else "browser")
    if backend == "graph":
        if username:
            raise MiniError("For Graph, pass the sign-in address as --mailbox")
        if not client_id or not tenant_id:
            raise MiniError("Graph requires both --client-id and --tenant-id")
        config = mail.validate_account(client_id, tenant_id, mailbox)
    elif backend == "browser":
        if client_id or tenant_id:
            raise MiniError("Browser sign-in does not use client or tenant IDs")
        if not all(
            re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", address)
            for address in (mailbox, username or mailbox)
        ):
            raise MiniError("Use email addresses for the mailbox and sign-in username")
        config = {
            "backend": "browser",
            "mailbox": mailbox.casefold(),
            "username": (username or mailbox).casefold(),
        }
    else:
        raise MiniError("Backend must be browser or graph")
    with database(state_dir) as db:
        previous = _setting(db, "account")
        if previous and json.loads(previous) != config:
            if db.execute("SELECT 1 FROM events WHERE state != 'waiting_request'").fetchone():
                raise MiniError("Mail has already been processed; use a separate state directory")
            if _setting(db, "tokens") or json.loads(previous).get("backend") == "browser":
                raise MiniError(
                    "This state belongs to another account; use a separate state directory"
                )
        if backend == "browser":
            from .outlook import Outlook

            with Outlook(db, config["mailbox"], username=config["username"], interactive=True):
                pass
            _setting(db, "account", json.dumps(config))
        else:
            _setting(db, "account", json.dumps(config))
            mail.token(db, interactive=True)
        _setting(db, "error", "")
        _setting(db, "retry_at", "")


def watch(
    source: Path,
    *,
    event_id: str,
    attachment: Path | None = None,
    since: str | None = None,
    state_dir: Path = DEFAULT_STATE,
) -> dict:
    """Register an exact event ID and save a fixed copy of its risk form"""
    from uq_minis.helper.risk_docx import build_form_document, load_event_config

    if not re.fullmatch(_ID, event_id):
        raise MiniError("Event ID must be 1–80 letters, digits, underscores or hyphens")
    config = load_event_config(source)
    if since is None:
        cutoff = datetime.now(UTC) - timedelta(days=30)
    else:
        try:
            cutoff = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError as exc:
            raise MiniError("--since must be YYYY-MM-DD") from exc
    if cutoff > datetime.now(UTC):
        raise MiniError("--since cannot be in the future")
    if attachment:
        attachment = attachment.expanduser()
        if attachment.stat().st_size >= 3_000_000:
            raise MiniError("Risk assessment must be smaller than 3 MB")
        filename = attachment.name
        document = attachment.read_bytes()
    else:
        buffer = io.BytesIO()
        build_form_document(config).save(buffer)
        document, filename = buffer.getvalue(), f"{config.output_name}.docx"
    # ponytail: Graph's simple attachment API requires files under 3 MB; add upload sessions if needed.
    if not document or len(document) >= 3_000_000:
        raise MiniError("Risk assessment must be nonempty and smaller than 3 MB")
    suffix = Path(filename).suffix.casefold()
    if suffix == ".pdf":
        valid = document.startswith(b"%PDF-")
    elif suffix == ".docx":
        try:
            with ZipFile(io.BytesIO(document)) as archive:
                valid = {"[Content_Types].xml", "word/document.xml"} <= set(archive.namelist())
        except BadZipFile:
            valid = False
    else:
        valid = False
    if not valid:
        raise MiniError("Attach a valid DOCX or PDF risk assessment")
    with database(state_dir) as db:
        if db.execute("SELECT 1 FROM events WHERE event_id = ?", (event_id,)).fetchone():
            raise MiniError("That Event ID is already registered; its saved form has not changed")
        db.execute(
            "INSERT INTO events (event_id,title,filename,document,since) VALUES (?,?,?,?,?)",
            (event_id, config.title, filename, document, cutoff.isoformat().replace("+00:00", "Z")),
        )
    return {
        "event_id": event_id,
        "title": config.title,
        "attachment": filename,
        "state": "waiting_request",
    }


def status(*, state_dir: Path = DEFAULT_STATE) -> list[dict]:
    """Return saved progress without credentials or attachment contents"""
    with database(state_dir) as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT event_id,title,filename,state,outcome,details,link,error FROM events ORDER BY event_id"
            )
        ]
        for row in rows:
            row["error"] = row["error"] or _setting(db, "error") or ""
        return rows


def stop(event_id: str, *, state_dir: Path = DEFAULT_STATE) -> None:
    """Stop watching an event without deleting its history or sent mail"""
    with database(state_dir) as db:
        if not db.execute("SELECT 1 FROM events WHERE event_id = ?", (event_id,)).fetchone():
            raise MiniError("Unknown Event ID")
        _save(db, event_id, state="stopped")


def retry_send(
    event_id: str,
    *,
    confirm_not_sent: bool = False,
    state_dir: Path = DEFAULT_STATE,
) -> None:
    """Permit another send only after the user checks Outlook's Sent Items"""
    if not confirm_not_sent:
        raise MiniError("Check Sent Items first, then pass --confirm-not-sent to allow a retry")
    with database(state_dir) as db:
        row = db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None or row["state"] != "sending":
            raise MiniError("Only an uncertain send can be retried")
        _save(db, event_id, state="draft", send_started=None, error="", last_notice="")


def _sender(message: dict) -> str:
    return message.get("from", {}).get("emailAddress", {}).get("address", "").casefold()


def _subject(message: dict):
    subject = re.sub(r"^(?:(?:re|fw|fwd):\s*)+", "", message.get("subject", "").strip(), flags=re.I)
    return _SUBJECT.fullmatch(subject)


def _matches(message: dict, event, *, request: bool) -> bool:
    REQUEST_SENDER = mail.REQUEST_SENDER

    match = _subject(message)
    return bool(
        _sender(message) == REQUEST_SENDER
        and match
        and bool(match["request"]) == request
        and match["id"] == event["event_id"]
        and " ".join(match["title"].casefold().split())
        == " ".join(event["title"].casefold().split())
    )


def booking_outcome(content: str) -> str:
    """Recognize explicit booking statements and leave uncertain wording for review"""
    outcomes = set()
    # ponytail: conservative wording rules; unfamiliar replies stay open for human review.
    for sentence in re.split(r"(?<=[.!?])\s+|\n", content.casefold()):
        if (
            sentence.startswith(">")
            or "?" in sentence
            or re.search(
                r"\b(if|once|pending|awaiting|could|may|might|will|would|please)\b", sentence
            )
            or not re.search(r"\b(room|venue|booking)\b", sentence)
        ):
            continue
        if re.search(
            r"\b(not (?:been )?(?:booked|confirmed|available)|unable to book)\b", sentence
        ):
            outcomes.add("not_booked")
        elif re.search(
            r"\b(not|no|hasn't|haven't|isn't|wasn't|can't|cannot|don't|doesn't|didn't|can|request|requested)\b",
            sentence,
        ):
            continue
        elif re.search(r"\b(unavailable|declined|rejected|cancelled|canceled)\b", sentence):
            outcomes.add("not_booked")
        elif re.search(r"\b(changed|moved|relocated|rescheduled)\b", sentence):
            outcomes.add("changed")
        elif re.search(r"\b(booked|confirmed|secured|approved)\b", sentence):
            outcomes.add("booked")
    return next(iter(outcomes)) if len(outcomes) == 1 else "review"


def _notice(db, event_id: str, key: str, message: str) -> None:
    from .service import notify

    event = db.execute(
        "SELECT title,last_notice FROM events WHERE event_id = ?", (event_id,)
    ).fetchone()
    if event["last_notice"] != key:
        notify(f"UQ event {event_id}: {event['title']}", message)
        _save(db, event_id, last_notice=key)


def _record_sent(db, event, sent: dict) -> None:
    recipients = [
        item.get("emailAddress", {}).get("address", "").casefold()
        for item in sent.get("toRecipients", [])
    ]
    if (
        sent.get("subject") != f"UQU Risk Assessment Return Ref ID: {event['event_id']}"
        or recipients != [mail.RETURN_TO]
        or sent.get("ccRecipients")
        or sent.get("bccRecipients")
    ):
        raise MiniError("The sent draft's subject or recipients changed; inspect it in Outlook")
    _time(sent["sentDateTime"])
    _save(db, event["event_id"], state="waiting_update", sent_at=sent["sentDateTime"], error="")


def _advance(db, event, messages: list[dict], graph) -> None:
    CLUBS_SENDER, GraphError = mail.CLUBS_SENDER, mail.GraphError

    event_id = event["event_id"]
    if event["state"] == "waiting_request":
        requests = [
            message
            for message in messages
            if _matches(message, event, request=True)
            and _time(message["receivedDateTime"]) >= _time(event["since"])
        ]
        if not requests:
            return
        request = min(requests, key=lambda item: _time(item["receivedDateTime"]))
        _save(
            db,
            event_id,
            state="draft",
            request_id=request["id"],
            request_time=request["receivedDateTime"],
        )
    event = db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    if event["state"] == "draft":
        draft_id = event["draft_id"]
        if not draft_id:
            draft_id = graph.create_reply(event["request_id"])
            _save(db, event_id, draft_id=draft_id)
        draft = graph.message(draft_id)
        if draft.get("isDraft") is False and draft.get("sentDateTime"):
            _record_sent(db, event, draft)
        elif draft.get("isDraft") is True:
            graph.prepare(draft_id, event_id, event["filename"], event["document"])
            # Commit before the network call; a lost response must never cause an automatic resend.
            _save(db, event_id, state="sending", send_started=now(), error="")
            try:
                graph.send(draft_id)
            except GraphError as exc:
                if exc.status in {400, 401, 403, 413, 429}:
                    _save(db, event_id, state="draft")
                raise
        else:
            raise MiniError("Microsoft returned a message with no draft/send status")
    event = db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    if event["state"] == "sending":
        try:
            sent = graph.message(event["draft_id"])
        except GraphError as exc:
            if exc.status != 404:
                raise
            sent = {}
        if sent.get("isDraft") is False and sent.get("sentDateTime"):
            _record_sent(db, event, sent)
        elif datetime.now(UTC) - datetime.fromisoformat(event["send_started"]) > timedelta(
            minutes=10
        ):
            message = (
                "Send status is uncertain. Check Outlook Sent Items before using agent retry-send."
            )
            _save(db, event_id, error=message)
            _notice(db, event_id, "uncertain_send", message)
            return
        else:
            return
    event = db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    if event["state"] in {"waiting_update", "waiting_reply"}:
        updates = [
            message
            for message in messages
            if _matches(message, event, request=False)
            and _time(message["receivedDateTime"]) >= _time(event["sent_at"])
        ]
        if not updates and not event["update_id"]:
            return
        update = max(updates, key=lambda item: _time(item["receivedDateTime"]), default=None)
        if update and not update.get("conversationId"):
            raise MiniError("The UQ update has no conversation ID; inspect it in Outlook")
        if update and (
            not event["update_time"]
            or _time(update["receivedDateTime"]) > _time(event["update_time"])
        ):
            _save(
                db,
                event_id,
                state="waiting_reply",
                update_id=update["id"],
                update_thread=update["conversationId"],
                update_time=update["receivedDateTime"],
                reply_id=None,
                outcome=None,
                details="",
                link="",
                last_notice="",
            )
    event = db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    if event["state"] == "waiting_reply":
        replies = []
        for message in messages:
            match = _subject(message)
            if (
                _sender(message) == CLUBS_SENDER
                and message.get("references") == []
                and match
                and match["id"] == event_id
                and " ".join(match["title"].casefold().split())
                == " ".join(event["title"].casefold().split())
                and _time(message["receivedDateTime"]) >= _time(event["update_time"])
            ):
                _notice(
                    db,
                    event_id,
                    f"missing_thread:{message['id']}",
                    "UQU replied without verifiable thread headers; check the booking in Outlook.",
                )
            if (
                _sender(message) == CLUBS_SENDER
                and (
                    event["update_id"] in message["references"]
                    if "references" in message
                    else message.get("conversationId") == event["update_thread"]
                )
                and _time(message["receivedDateTime"]) >= _time(event["update_time"])
                and (not match or match["id"] == event_id)
            ):
                replies.append(message)
        if not replies:
            return
        reply = max(replies, key=lambda item: _time(item["receivedDateTime"]))
        if reply["id"] != event["reply_id"]:
            detail = graph.message(reply["id"])
            body = detail.get("uniqueBody", {})
            content = body.get("content", "").strip()
            outcome = (
                booking_outcome(content)
                if body.get("contentType", "").casefold() == "text"
                else "review"
            )
            _save(
                db,
                event_id,
                reply_id=reply["id"],
                outcome=outcome,
                details=content[:20000],
                link=detail.get("webLink", ""),
                error="",
                state="waiting_reply" if outcome == "review" else "complete",
            )
    event = db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    if event["outcome"]:
        label = {
            "booked": "Room booked",
            "not_booked": "Room not booked",
            "changed": "Booking changed",
            "review": "UQU replied; booking wording needs review",
        }[event["outcome"]]
        _notice(db, event_id, event["reply_id"], f"{label}. {event['details'][:300]}")


def process(db) -> None:
    """Advance registered events using one mailbox session"""
    events = db.execute(
        "SELECT * FROM events WHERE state != 'stopped' "
        "AND (state != 'complete' OR last_notice IS NOT reply_id)"
    ).fetchall()
    if not events:
        return
    with ExitStack() as stack:
        graph = None
        pending = [event for event in events if event["state"] != "complete"]
        messages = []
        if pending:
            graph = stack.enter_context(mail.connect(db))
            # Keep the original cutoff so offline periods and moved messages cannot create gaps.
            messages = graph.messages(min(event["since"] for event in pending))
        for event in events:
            try:
                if event["error"]:
                    _save(db, event["event_id"], error="")
                _advance(db, event, messages, graph)
            except (MiniError, OSError) as exc:
                _save(db, event["event_id"], error=str(exc))
                if isinstance(exc, mail.GraphError) and exc.status == 429:
                    raise
                _notice(db, event["event_id"], f"error:{exc}", str(exc))


def poll(*, state_dir: Path = DEFAULT_STATE) -> None:
    """Run one recoverable mailbox pass; launchd schedules the next pass"""
    run(process, state_dir=state_dir, storage=database)
