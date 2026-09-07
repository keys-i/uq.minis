from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from uq_minis.helper.common import MiniError
from uq_minis.workers import event as worker
from uq_minis.workers import helper, service

mail = helper("mail")


def message(
    identity,
    sender=mail.REQUEST_SENDER,
    *,
    request=False,
    event_id="42",
    title="Sample Event",
    thread="update",
    timestamp="2026-09-07T12:01:00Z",
    content=None,
):
    subject = f"Event Application Update{' Risk Assessment Request' if request else ''}  [Event ID: {event_id}] - {title}"
    result = {
        "id": identity,
        "from": {"emailAddress": {"address": sender}},
        "subject": subject,
        "conversationId": thread,
        "receivedDateTime": timestamp,
    }
    if content is not None:
        result.update(
            uniqueBody={"contentType": "text", "content": content},
            webLink="https://outlook.office.com/mail/test",
        )
    return result


class Mailbox:
    def __init__(self):
        self.incoming = []
        self.drafts = {}
        self.created = 0
        self.sent = 0
        self.attachments = []
        self.fail_send = None
        self.client = SimpleNamespace(close=lambda: None)

    def messages(self, since):
        return self.incoming

    def create_reply(self, request_id):
        self.created += 1
        identity = f"draft-{self.created}"
        self.drafts[identity] = {"id": identity, "isDraft": True}
        return identity

    def message(self, identity):
        return deepcopy(
            self.drafts.get(identity)
            or next(item for item in self.incoming if item["id"] == identity)
        )

    def prepare(self, identity, event_id, filename, document):
        self.attachments.append((filename, document))
        self.drafts[identity].update(
            subject=f"UQU Risk Assessment Return Ref ID: {event_id}",
            toRecipients=[{"emailAddress": {"address": mail.RETURN_TO}}],
            ccRecipients=[],
            bccRecipients=[],
        )

    def send(self, identity):
        self.sent += 1
        self.drafts[identity].update(isDraft=False, sentDateTime="2026-09-07T12:00:00Z")
        if self.fail_send:
            raise self.fail_send


@pytest.fixture
def setup_agent(event_toml, tmp_path, monkeypatch):
    state = tmp_path / "agent"
    worker.watch(event_toml, event_id="42", since="2026-09-01", state_dir=state)
    mailbox = Mailbox()
    notices = []
    monkeypatch.setattr(mail, "token", lambda db: "test-token")
    monkeypatch.setattr(mail, "Graph", lambda token: mailbox)
    monkeypatch.setattr(service, "notify", lambda title, body: notices.append((title, body)))
    return state, mailbox, notices


def test_saved_workflow_matches_id_title_sender_and_thread(setup_agent):
    state, box, notices = setup_agent
    box.incoming = [
        message("wrong-id", request=True, event_id="43"),
        message("wrong-title", request=True, title="Another Event"),
        message("wrong-sender", sender="other@example.org", request=True),
    ]
    worker.poll(state_dir=state)
    assert not box.sent
    box.incoming.append(
        message("request", request=True, thread="request", timestamp="2026-09-07T11:00:00Z")
    )
    worker.poll(state_dir=state)
    assert worker.status(state_dir=state)[0]["state"] == "waiting_update"
    assert box.sent == 1 and box.attachments[0][1].startswith(b"PK")
    worker.poll(state_dir=state)
    assert box.sent == 1
    box.incoming.extend(
        [
            message("update"),
            message(
                "unrelated", mail.CLUBS_SENDER, thread="different", content="Your room is booked."
            ),
            message(
                "other-event", mail.CLUBS_SENDER, event_id="43", content="Your room is booked."
            ),
        ]
    )
    worker.poll(state_dir=state)
    assert worker.status(state_dir=state)[0]["state"] == "waiting_reply"
    box.incoming.append(
        message(
            "uncertain",
            mail.CLUBS_SENDER,
            timestamp="2026-09-07T12:02:00Z",
            content="Your booking is awaiting confirmation.",
        )
    )
    worker.poll(state_dir=state)
    assert worker.status(state_dir=state)[0]["outcome"] == "review"
    assert len(notices) == 1
    worker.poll(state_dir=state)
    assert len(notices) == 1
    box.incoming.append(
        message(
            "confirmed",
            mail.CLUBS_SENDER,
            timestamp="2026-09-07T12:03:00Z",
            content="Your room booking is confirmed.",
        )
    )
    worker.poll(state_dir=state)
    row = worker.status(state_dir=state)[0]
    assert row["state"] == "complete" and row["outcome"] == "booked"
    assert "document" not in row and len(notices) == 2
    worker.poll(state_dir=state)
    assert len(notices) == 2 and box.sent == 1


def test_lost_send_response_is_reconciled_without_resending(setup_agent):
    state, box, _ = setup_agent
    box.incoming = [message("request", request=True, timestamp="2026-09-07T11:00:00Z")]
    box.fail_send = MiniError("Connection lost after server accepted send")
    worker.poll(state_dir=state)
    assert worker.status(state_dir=state)[0]["state"] == "sending"
    box.fail_send = None
    worker.poll(state_dir=state)
    assert worker.status(state_dir=state)[0]["state"] == "waiting_update"
    assert box.sent == 1


def test_crash_before_send_requires_explicit_retry(setup_agent):
    state, box, notices = setup_agent
    draft_id = box.create_reply("request")
    old = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with worker.database(state) as db:
        worker._save(
            db, "42", state="sending", request_id="request", draft_id=draft_id, send_started=old
        )
    worker.poll(state_dir=state)
    worker.poll(state_dir=state)
    assert box.sent == 0 and len(notices) == 1
    with pytest.raises(MiniError, match="Sent Items"):
        worker.retry_send("42", state_dir=state)
    worker.retry_send("42", confirm_not_sent=True, state_dir=state)
    worker.poll(state_dir=state)
    assert box.sent == 1


def test_completion_notification_retries_after_failure(setup_agent, monkeypatch):
    state, box, notices = setup_agent
    box.incoming = [
        message("request", request=True, timestamp="2026-09-07T11:00:00Z"),
        message("update"),
        message(
            "reply",
            mail.CLUBS_SENDER,
            content="Your room booking has been changed.",
            timestamp="2026-09-07T12:02:00Z",
        ),
    ]
    monkeypatch.setattr(
        service,
        "notify",
        lambda *args: (_ for _ in ()).throw(MiniError("Notifications unavailable")),
    )
    with pytest.raises(MiniError, match="Notifications"):
        worker.poll(state_dir=state)
    assert worker.status(state_dir=state)[0]["state"] == "complete"
    monkeypatch.setattr(service, "notify", lambda *args: notices.append(args))
    worker.poll(state_dir=state)
    assert len(notices) == 1 and box.sent == 1


@pytest.mark.parametrize(
    "content,expected",
    [
        ("Your room booking is confirmed.", "booked"),
        ("The room has been booked.", "booked"),
        ("Your booking has been cancelled.", "not_booked"),
        ("The room is not available.", "not_booked"),
        ("The room has not been booked.", "not_booked"),
        ("Your booking has been moved to another room.", "changed"),
        ("Your room will be booked once approval arrives.", "review"),
        ("Can you confirm the room is booked?", "review"),
        ("The booking is pending.", "review"),
        ("> Your booking is confirmed.", "review"),
        ("The booking is confirmed. The room is not available.", "review"),
        ("The room booking has not changed.", "review"),
        ("The booking has not been cancelled.", "review"),
    ],
)
def test_booking_outcome_is_conservative(content, expected):
    assert worker.booking_outcome(content) == expected


def test_state_lock_and_registration_validation(setup_agent, event_toml):
    state, _, _ = setup_agent
    with worker.database(state):
        with pytest.raises(MiniError, match="Another agent"):
            worker.status(state_dir=state)
    with worker.database(state) as db:
        with pytest.raises(MiniError, match="Invalid database identifier"):
            helper("db").update(db, "events; DROP TABLE events", "event_id", "42", state="stopped")
    with pytest.raises(MiniError, match="already registered"):
        worker.watch(event_toml, event_id="42", state_dir=state)
    with pytest.raises(MiniError, match="Event ID"):
        worker.watch(event_toml, event_id="42\nBcc: other@example.org", state_dir=state)
    worker.stop("42", state_dir=state)
    assert worker.status(state_dir=state)[0]["state"] == "stopped"


def test_completed_history_is_not_polled_again(setup_agent, monkeypatch):
    state, _, _ = setup_agent
    with worker.database(state) as db:
        worker._save(
            db, "42", state="complete", reply_id="reply", last_notice="reply", outcome="booked"
        )
    monkeypatch.setattr(
        worker, "_advance", lambda *args: pytest.fail("completed history must be skipped")
    )
    worker.poll(state_dir=state)


def test_fractional_timestamps_and_newer_update_threads(setup_agent):
    state, box, _ = setup_agent
    box.incoming = [
        message("request", request=True, timestamp="2026-09-07T11:00:00Z"),
        message("update", timestamp="2026-09-07T12:00:00.100Z"),
    ]
    worker.poll(state_dir=state)
    assert worker.status(state_dir=state)[0]["state"] == "waiting_reply"
    box.incoming += [
        message("new-update", thread="new", timestamp="2026-09-07T12:00:00.200Z"),
        message(
            "old-reply",
            mail.CLUBS_SENDER,
            timestamp="2026-09-07T12:01:00Z",
            content="Your room is booked.",
        ),
    ]
    worker.poll(state_dir=state)
    assert worker.status(state_dir=state)[0]["state"] == "waiting_reply"
    box.incoming = [
        message(
            "new-reply",
            mail.CLUBS_SENDER,
            thread="new",
            timestamp="2026-09-07T12:02:00Z",
            content="Your room booking has changed.",
        )
    ]
    worker.poll(state_dir=state)
    assert worker.status(state_dir=state)[0]["outcome"] == "changed"


def test_throttling_deadline_survives_restart(setup_agent, monkeypatch):
    state, box, notices = setup_agent
    calls = []

    def throttled(since):
        calls.append(since)
        raise mail.GraphError(429, retry_after=3600)

    monkeypatch.setattr(box, "messages", throttled)
    with pytest.raises(mail.GraphError):
        worker.poll(state_dir=state)
    worker.poll(state_dir=state)
    assert len(calls) == len(notices) == 1


def test_token_refresh_is_saved_without_printing_tokens(tmp_path, monkeypatch, capsys):
    import json
    import sys

    cache = SimpleNamespace(
        has_state_changed=True, deserialize=lambda data: None, serialize=lambda: "rotated-cache"
    )

    class App:
        def __init__(self, client_id, **kwargs):
            assert (
                kwargs["authority"]
                == "https://login.microsoftonline.com/00000000-0000-0000-0000-000000000002"
            )

        def get_accounts(self, username):
            assert username == "rad@example.org"
            return [{"username": username}]

        def acquire_token_silent(self, scopes, account):
            assert scopes == ["Mail.ReadWrite", "Mail.Send"]
            return {"access_token": "private-test-token"}

    monkeypatch.setitem(
        sys.modules,
        "msal",
        SimpleNamespace(SerializableTokenCache=lambda: cache, PublicClientApplication=App),
    )
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(RequestException=ConnectionError))
    with worker.database(tmp_path / "state") as db:
        config = mail.validate_account(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "rad@example.org",
        )
        worker._setting(db, "account", json.dumps(config))
        assert mail.token(db) == "private-test-token"
        assert worker._setting(db, "tokens") == "rotated-cache"
    assert not capsys.readouterr().out


def test_graph_exact_reply_attachment_and_untrusted_pagination():
    calls = []
    attachments = []

    def handler(request):
        import json

        calls.append(request)
        assert request.headers["prefer"] == 'IdType="ImmutableId", outlook.body-content-type="text"'
        if request.method == "PATCH":
            body = json.loads(request.content)
            assert body["subject"] == "UQU Risk Assessment Return Ref ID: 42"
            assert body["body"]["content"] == mail.BODY
            assert body["toRecipients"] == [{"emailAddress": {"address": mail.RETURN_TO}}]
            assert not body["ccRecipients"] and not body["bccRecipients"]
            return httpx.Response(200, json={})
        if request.method == "POST":
            attachments.append(json.loads(request.content))
            return httpx.Response(201, json=attachments[-1])
        return httpx.Response(200, json={"value": attachments})

    graph = mail.Graph("test-token")
    graph.client.close()
    graph.client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"Prefer": 'IdType="ImmutableId", outlook.body-content-type="text"'},
    )
    try:
        graph.prepare("draft", "42", "form.docx", b"form-bytes")
        graph.prepare("draft", "42", "form.docx", b"form-bytes")
        assert len(attachments) == 1
        with pytest.raises(MiniError, match="outside"):
            list(graph.pages("https://other.example/v1.0/me/messages"))
        assert len(calls) == 5
    finally:
        graph.client.close()
