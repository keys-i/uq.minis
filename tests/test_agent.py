from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from tests.fakes import message
from uq_minis.core.common import MiniError
from uq_minis.worker import db as storage
from uq_minis.worker import event as worker
from uq_minis.worker import mail, service


class TestWatcher:
    @pytest.mark.parametrize("return_to", [mail.RETURN_TO, "radhesh.goel@student.uq.edu.au"])
    def test_workflow(self, watch, monkeypatch, return_to):
        monkeypatch.setattr(mail, "RETURN_TO", return_to)
        state, box, notices = watch
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
        assert box.drafts["draft-1"]["toRecipients"] == [{"emailAddress": {"address": return_to}}]
        worker.poll(state_dir=state)
        assert box.sent == 1
        box.incoming.extend(
            [
                message("update"),
                message(
                    "unrelated",
                    mail.CLUBS_SENDER,
                    thread="different",
                    content="Your room is booked.",
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

    def test_reconcile(self, watch):
        state, box, _ = watch
        box.incoming = [message("request", request=True, timestamp="2026-09-07T11:00:00Z")]
        box.fail_send = MiniError("Connection lost after server accepted send")
        worker.poll(state_dir=state)
        assert worker.status(state_dir=state)[0]["state"] == "sending"
        box.fail_send = None
        worker.poll(state_dir=state)
        assert worker.status(state_dir=state)[0]["state"] == "waiting_update"
        assert box.sent == 1

    def test_retry(self, watch):
        state, box, notices = watch
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

    def test_notify(self, watch, monkeypatch):
        state, box, notices = watch
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
        ids=[
            "confirmed",
            "booked",
            "cancelled",
            "unavailable",
            "unbooked",
            "moved",
            "conditional",
            "question",
            "pending",
            "quoted",
            "conflicting",
            "unchanged",
            "not-cancelled",
        ],
    )
    def test_outcome(self, content, expected):
        assert worker.booking_outcome(content) == expected

    def test_lock(self, watch, event_toml):
        state, _, _ = watch
        with worker.database(state):
            with pytest.raises(MiniError, match="Another agent"):
                worker.status(state_dir=state)
        with worker.database(state) as db:
            with pytest.raises(MiniError, match="Invalid database identifier"):
                storage.update(db, "events; DROP TABLE events", "event_id", "42", state="stopped")
        with pytest.raises(MiniError, match="already registered"):
            worker.watch(event_toml, event_id="42", state_dir=state)
        with pytest.raises(MiniError, match="Event ID"):
            worker.watch(event_toml, event_id="42\nBcc: other@example.org", state_dir=state)
        worker.stop("42", state_dir=state)
        assert worker.status(state_dir=state)[0]["state"] == "stopped"

    def test_history(self, watch, monkeypatch):
        state, _, _ = watch
        with worker.database(state) as db:
            worker._save(
                db, "42", state="complete", reply_id="reply", last_notice="reply", outcome="booked"
            )
        monkeypatch.setattr(
            worker, "_advance", lambda *args: pytest.fail("completed history must be skipped")
        )
        worker.poll(state_dir=state)

    def test_threads(self, watch):
        state, box, _ = watch
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

    def test_throttle(self, watch, monkeypatch):
        state, box, notices = watch
        calls = []

        def throttled(since):
            calls.append(since)
            raise mail.GraphError(429, retry_after=3600)

        monkeypatch.setattr(box, "messages", throttled)
        with pytest.raises(mail.GraphError):
            worker.poll(state_dir=state)
        worker.poll(state_dir=state)
        assert len(calls) == len(notices) == 1


class TestGraph:
    def test_token(self, tmp_path, monkeypatch, capsys):
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
        monkeypatch.setitem(
            sys.modules, "requests", SimpleNamespace(RequestException=ConnectionError)
        )
        with worker.database(tmp_path / "state") as db:
            config = mail.validate_account(
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "rad@example.org",
            )
            storage.setting(db, "account", json.dumps(config))
            assert mail.token(db) == "private-test-token"
            assert storage.setting(db, "tokens") == "rotated-cache"
        assert not capsys.readouterr().out

    @pytest.mark.parametrize("return_to", [mail.RETURN_TO, "radhesh.goel@student.uq.edu.au"])
    def test_reply(self, monkeypatch, return_to):
        monkeypatch.setattr(mail, "RETURN_TO", return_to)
        calls = []
        attachments = []

        def handler(request):
            import json

            calls.append(request)
            assert (
                request.headers["prefer"]
                == 'IdType="ImmutableId", outlook.body-content-type="text"'
            )
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
