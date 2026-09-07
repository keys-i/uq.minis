from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path
from types import SimpleNamespace

import pytest

from uq_minis.helper.common import MiniError
from uq_minis.workers import event, helper, outlook, service

mail = helper("mail")


def _eml(*, message_id: str, sender: str, subject: str, body: str, to: str = "") -> bytes:
    message = EmailMessage()
    message["Message-ID"] = message_id
    message["From"] = sender
    if to:
        message["To"] = to
    message["Subject"] = subject
    message["Date"] = "Mon, 07 Sep 2026 12:00:00 +0000"
    message["Received"] = "from mail.example by outlook.example; Mon, 07 Sep 2026 12:01:00 +0000"
    message["References"] = "<request@example> <update@example>"
    message["In-Reply-To"] = "<update@example>"
    message.set_content(body)
    return message.as_bytes()


def _request() -> dict:
    return {
        "id": "<request@example>",
        "from": {"emailAddress": {"address": mail.REQUEST_SENDER}},
        "subject": "Event Application Update Risk Assessment Request  [Event ID: 42] - Sample Event",
        "conversationId": "request-thread",
        "receivedDateTime": "2026-09-07T11:00:00+00:00",
        "webLink": "https://outlook.office.com/mail/id/request",
    }


def test_parse_eml_preserves_rfc_thread_and_ignores_quoted_reply():
    raw = _eml(
        message_id="<clubs@example>",
        sender="Clubs <clubs@uqu.com.au>",
        subject="Re: Event Application Update  [Event ID: 42] - Sample Event",
        body="Your room booking is confirmed.\n\nOn yesterday wrote:\n> old text",
    )
    parsed = outlook.parse_message(raw, "https://outlook.office.com/mail/id/clubs")

    assert parsed["id"] == "<clubs@example>"
    assert parsed["from"]["emailAddress"]["address"] == "clubs@uqu.com.au"
    assert parsed["references"] == ["<request@example>", "<update@example>", "<update@example>"]
    assert parsed["uniqueBody"]["content"] == "Your room booking is confirmed."
    assert parsed["body"]["content"].endswith("> old text")


def test_parse_sent_return_requires_every_visible_mail_property():
    document = b"risk-form"
    email = EmailMessage()
    email.set_content(mail.BODY)
    email["Message-ID"] = "<sent@example>"
    email["From"] = "rad@example.org"
    email["To"] = mail.RETURN_TO
    email["Subject"] = "UQU Risk Assessment Return Ref ID: 42"
    email["Date"] = "Mon, 07 Sep 2026 12:00:00 +0000"
    email.add_attachment(
        document, maintype="application", subtype="octet-stream", filename="form.docx"
    )
    parsed = outlook.parse_message(email.as_bytes(), "https://outlook.office.com/mail/id/sent")

    assert outlook._same_return(parsed, "42", "form.docx", document, "rad@example.org")
    assert parsed["attachments"] == [
        {"name": "form.docx", "sha256": hashlib.sha256(document).hexdigest()}
    ]
    altered = {**parsed, "toRecipients": [{"emailAddress": {"address": "other@example.org"}}]}
    assert not outlook._same_return(altered, "42", "form.docx", document, "rad@example.org")
    altered = {**parsed, "body": {"content": mail.BODY + "\nextra"}}
    assert not outlook._same_return(altered, "42", "form.docx", document, "rad@example.org")
    altered = {**parsed, "attachments": [{"name": "form.docx", "sha256": "0" * 64}]}
    assert not outlook._same_return(altered, "42", "form.docx", document, "rad@example.org")
    quoted = outlook.parse_message(
        _sent_eml(document, body=f"{mail.BODY}\n\nOn yesterday wrote:\n> quoted text"),
        "https://outlook.office.com/mail/id/sent",
    )
    assert not outlook._same_return(quoted, "42", "form.docx", document, "rad@example.org")


def test_browser_draft_is_local_and_restart_only_reconciles_exact_sent_return(tmp_path):
    state = tmp_path / "agent"
    document = b"risk-form"
    with event.database(state) as db:
        box = outlook.Outlook(db, "rad@example.org")
        db.execute(
            "INSERT INTO events (event_id,title,filename,document,since,state,request_id,request_time) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                "42",
                "Sample Event",
                "form.docx",
                document,
                "2026-09-01T00:00:00+00:00",
                "draft",
                "<request@example>",
                "2026-09-07T11:00:00+00:00",
            ),
        )
        db.execute(
            "INSERT INTO browser_mail VALUES (?, ?)", ("<request@example>", json.dumps(_request()))
        )
        identity = box.create_reply("<request@example>")
        assert identity.startswith("browser:")
        db.execute("UPDATE events SET draft_id = ? WHERE event_id = '42'", (identity,))
        box._collect = lambda *args: []
        assert box.message(identity) == {"id": identity, "isDraft": True}

        sent = outlook.parse_message(_sent_eml(document), "https://outlook.office.com/mail/id/sent")
        db.execute(
            "UPDATE events SET state = 'sending', send_started = ? WHERE event_id = '42'",
            ("2026-09-07T11:30:00+00:00",),
        )
        box._collect = lambda *args: [sent]
        assert box.message(identity)["id"] == "<sent@example>"

        box._collect = lambda *args: [sent, sent]
        with pytest.raises(MiniError, match="Multiple matching"):
            box.message(identity)
        unthreaded = {**sent, "references": []}
        box._collect = lambda *args: [unthreaded]
        assert box.message(identity) == {"id": identity, "isDraft": True}


def _sent_eml(document: bytes, *, body: str = mail.BODY) -> bytes:
    message = EmailMessage()
    message["Message-ID"] = "<sent@example>"
    message["From"] = "rad@example.org"
    message["To"] = mail.RETURN_TO
    message["Subject"] = "UQU Risk Assessment Return Ref ID: 42"
    message["In-Reply-To"] = "<request@example>"
    message["References"] = "<request@example>"
    message["Date"] = "Mon, 07 Sep 2026 12:00:00 +0000"
    message.set_content(body)
    message.add_attachment(
        document, maintype="application", subtype="octet-stream", filename="form.docx"
    )
    return message.as_bytes()


def test_browser_send_is_not_retried_after_restart_without_confirmation(
    event_toml, tmp_path, monkeypatch
):
    state = tmp_path / "agent"
    event.watch(event_toml, event_id="42", since="2026-09-01", state_dir=state)

    class BrowserUI:
        def __init__(self):
            self.sent = self.attempt = 0
            self.prepared = []

        def messages(self, since):
            return [_request()]

        def create_reply(self, request_id):
            return "browser:local"

        def message(self, identity):
            if identity == "browser:local" and self.sent:
                return {
                    "id": "<sent@example>",
                    "isDraft": False,
                    "sentDateTime": "2026-09-07T12:00:00+00:00",
                    "subject": "UQU Risk Assessment Return Ref ID: 42",
                    "toRecipients": [{"emailAddress": {"address": mail.RETURN_TO}}],
                    "ccRecipients": [],
                    "bccRecipients": [],
                }
            return {"id": identity, "isDraft": True}

        def prepare(self, *args):
            self.prepared.append(args)

        def send(self, identity):
            self.attempt += 1
            if self.attempt == 1:
                raise MiniError("browser closed while sending")
            self.sent += 1

    ui = BrowserUI()

    @contextmanager
    def connect(db):
        yield ui

    monkeypatch.setattr(mail, "connect", connect)
    monkeypatch.setattr(service, "notify", lambda *args: None)
    event.poll(state_dir=state)
    assert event.status(state_dir=state)[0]["state"] == "sending"
    event.poll(state_dir=state)
    assert ui.attempt == 1  # A restart must reconcile, never click Send again.
    with event.database(state) as db:
        event._save(
            db,
            "42",
            send_started=(datetime.now(UTC) - timedelta(minutes=11)).isoformat(),
        )
    event.poll(state_dir=state)
    with pytest.raises(MiniError, match="Sent Items"):
        event.retry_send("42", state_dir=state)
    event.retry_send("42", confirm_not_sent=True, state_dir=state)
    event.poll(state_dir=state)
    assert ui.attempt == 2
    assert event.status(state_dir=state)[0]["state"] == "waiting_update"


def test_login_defaults_to_browser_and_refuses_account_swap(tmp_path, monkeypatch):
    opened = []

    class Browser:
        def __init__(self, db, mailbox, *, username=None, interactive=False):
            opened.append((mailbox, username, interactive))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(outlook, "Outlook", Browser)
    state = tmp_path / "agent"
    event.login(mailbox="RAD@EXAMPLE.ORG", username="s123@uq.edu.au", state_dir=state)
    assert opened == [("rad@example.org", "s123@uq.edu.au", True)]
    with event.database(state) as db:
        assert json.loads(event._setting(db, "account")) == {
            "backend": "browser",
            "mailbox": "rad@example.org",
            "username": "s123@uq.edu.au",
        }
    with pytest.raises(MiniError, match="another account"):
        event.login(mailbox="other@example.org", state_dir=state)


def test_browser_send_checks_live_dom_and_consumes_send_permission(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).is_file():
            pytest.skip("Install Chromium to run the local browser check")
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            with event.database(tmp_path / "agent") as db:
                db.execute(
                    "INSERT INTO events (event_id,title,filename,document,since,state,draft_id,send_started) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        "42",
                        "Sample Event",
                        "form.docx",
                        b"form",
                        "2026-09-01T00:00:00Z",
                        "sending",
                        "browser:local",
                        "2026-09-07T12:00:00Z",
                    ),
                )
                box = outlook.Outlook(db, "rad@example.org")
                box.page = page
                html = f"""<input aria-label="Subject" value="UQU Risk Assessment Return Ref ID: 42">
                <div role="textbox" contenteditable="true" aria-label="Message body" style="white-space:pre-wrap">{escape(mail.BODY)}</div>
                <div class="ms-BasePicker-text"><span class="ms-PickerItem-root" data-email="{mail.RETURN_TO}">{mail.RETURN_TO}</span><input aria-label="To"></div>
                <div class="ms-BasePicker-text" id="cc"><input aria-label="Cc"></div>
                <div class="ms-BasePicker-text"><input aria-label="Bcc"></div>
                <button aria-label="Remove form.docx attachment">Remove attachment</button>
                <button onclick="window.sends++; document.querySelector('#notice').hidden=false">Send</button>
                <div id="notice" hidden>Message sent</div><script>window.sends=0</script>"""
                page.set_content(html)
                box.prepared = "browser:local"
                page.locator("#cc").evaluate(
                    "node => node.insertAdjacentHTML('afterbegin', '<span class=ms-PickerItem-root data-email=other@example.org>other@example.org</span>')"
                )
                with pytest.raises(MiniError, match="recipients"):
                    box.send("browser:local")
                assert page.evaluate("window.sends") == 0
                page.set_content(html)
                box.send("browser:local")
                assert page.evaluate("window.sends") == 1
                with pytest.raises(MiniError, match="no verified prepared reply"):
                    box.send("browser:local")
                assert page.evaluate("window.sends") == 1
        finally:
            browser.close()


def test_browser_booking_requires_update_reference_and_reports_missing_headers(
    event_toml, tmp_path, monkeypatch
):
    state = tmp_path / "agent"
    event.watch(event_toml, event_id="42", state_dir=state)
    notices = []
    monkeypatch.setattr(service, "notify", lambda *args: notices.append(args))
    reply = outlook.parse_message(
        _eml(
            message_id="<clubs@example>",
            sender=mail.CLUBS_SENDER,
            subject="Re: Event Application Update  [Event ID: 42] - Sample Event",
            body="Your room is booked.",
        ),
        "https://outlook.office.com/mail/id/clubs",
    )
    box = SimpleNamespace(message=lambda _: reply)
    with event.database(state) as db:
        event._save(
            db,
            "42",
            state="waiting_reply",
            update_id="<update@example>",
            update_thread="<update@example>",
            update_time="2026-09-07T12:00:00Z",
            sent_at="2026-09-07T11:00:00Z",
        )
        for references in (["<different@example>"], [], []):
            row = db.execute("SELECT * FROM events WHERE event_id = '42'").fetchone()
            event._advance(db, row, [{**reply, "references": references}], box)
            assert db.execute("SELECT state FROM events").fetchone()[0] == "waiting_reply"
        assert len(notices) == 1 and "headers" in notices[0][1]
        row = db.execute("SELECT * FROM events WHERE event_id = '42'").fetchone()
        event._advance(db, row, [reply], box)
        assert db.execute("SELECT state,outcome FROM events").fetchone()[:] == (
            "complete",
            "booked",
        )
        assert len(notices) == 2
