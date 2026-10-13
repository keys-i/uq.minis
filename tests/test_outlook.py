from __future__ import annotations

import hashlib
import json
import os
from base64 import b64encode
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from sqlite3 import Connection
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest
from playwright.sync_api import Page

from tests import fakes
from uq_minis.core.common import MiniError
from uq_minis.worker import db as storage
from uq_minis.worker import event, mail, outlook, service


class TestBrowser:
    @pytest.mark.parametrize("interactive", [False, True], ids=["poll", "login"])
    @pytest.mark.parametrize("new", [False, True], ids=["existing-page", "new-page"])
    def test_open(
        self, inbox: outlook.Outlook, browser: SimpleNamespace, interactive: bool, new: bool
    ) -> None:
        inbox.interactive = interactive
        if new:
            browser.context.pages = []
        with inbox as opened:
            assert opened is inbox and opened.page is browser.page
            profile = inbox.state_dir / "browser"
            assert profile.is_dir()
            if os.name == "posix":
                assert profile.stat().st_mode & 0o777 == 0o700
        options = browser.runtime.chromium.launch_persistent_context.call_args.kwargs
        assert options["headless"] == (not interactive)
        assert options["accept_downloads"] and options["locale"] == "en-AU"
        browser.context.close.assert_called_once()
        browser.runtime.stop.assert_called_once()

    @pytest.mark.parametrize("failure", ["launch", "account", "cancel"])
    def test_cleanup(
        self,
        inbox: outlook.Outlook,
        browser: SimpleNamespace,
        monkeypatch: pytest.MonkeyPatch,
        failure: str,
    ) -> None:
        error = KeyboardInterrupt() if failure == "cancel" else fakes.BrowserError("private page")
        if failure == "launch":
            browser.runtime.chromium.launch_persistent_context.side_effect = error
        else:
            monkeypatch.setattr(inbox, "_verify_account", Mock(side_effect=error))
        with (
            pytest.raises(KeyboardInterrupt if failure == "cancel" else MiniError) as caught,
            inbox,
        ):
            pytest.fail("must not open a failed session")
        assert "private page" not in str(caught.value)
        if failure != "launch":
            browser.context.close.assert_called_once()
        browser.runtime.stop.assert_called_once()

    @pytest.mark.parametrize("blocked", ["dependency", "symlink"])
    def test_refuse(
        self,
        inbox: outlook.Outlook,
        browser: SimpleNamespace,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        blocked: str,
    ) -> None:
        if blocked == "dependency":
            import sys

            monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
        else:
            (inbox.state_dir / "browser").symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(MiniError, match="support|symlink"), inbox:
            pytest.fail("must not start an unsafe browser")
        browser.api.sync_playwright.assert_not_called()


class TestUI:
    @pytest.mark.parametrize("search", ["Search", "Search for email, meetings, files and more."])
    @pytest.mark.parametrize("folder", [None, "Sent Items"], ids=["all", "sent"])
    @pytest.mark.parametrize("scope", ["All folders", "Current folder"])
    def test_search(
        self, inbox: outlook.Outlook, page: Page, search: str, folder: None | str, scope: str
    ) -> None:
        inbox.page = page
        page.route(
            outlook.HOME,
            lambda route: route.fulfill(
                content_type="text/html",
                body=f"""
          <input role="combobox" aria-label="{search}">
          <div role="treeitem">Sent Items</div>
          <button id="all" {"hidden" if scope != "All folders" else ""}
            onclick="document.querySelector('#current-menu').hidden=false">All folders</button>
          <button id="current" {"hidden" if scope != "Current folder" else ""}
            onclick="document.querySelector('#all-menu').hidden=false">Current folder</button>
          <button id="all-menu" role="menuitem" hidden
            onclick="document.querySelector('#all').hidden=false; this.hidden=true">All folders</button>
          <button id="current-menu" role="menuitem" hidden
            onclick="document.querySelector('#current').hidden=false; this.hidden=true">Current folder</button>
        """,
            ),
        )
        page.goto(outlook.HOME)
        inbox._search("test event", folder)
        assert inbox._search_box().input_value() == "test event"
        assert page.get_by_role(
            "button", name="Current folder" if folder else "All folders", exact=True
        ).is_visible()

    @pytest.mark.parametrize("account", ["Account manager", "Test User"])
    def test_account(self, inbox: outlook.Outlook, page: Page, account: str) -> None:
        inbox.page = page
        page.set_content(
            '<div id="owa-me-control-container">'
            f"<button onclick=\"document.querySelector('#account').hidden=false\">{account}</button></div>"
            '<div id="account" hidden>rad@example.org</div>'
        )
        inbox._verify_account()
        assert page.get_by_text("rad@example.org", exact=True).is_visible()

    @pytest.mark.parametrize("actions", ["More actions", "More items"])
    def test_export(self, inbox: outlook.Outlook, page: Page, actions: str) -> None:
        inbox.page = page
        download = "data:message/rfc822;base64," + b64encode(fakes.sent(b"form")).decode()
        html = (
            '<div role="document" aria-label="Message body">Test message</div>'
            "<button>More actions</button><button>More actions</button>"
            f'<div role="toolbar"><button onclick="document.querySelector(\'#export\').hidden=false">{actions}</button></div>'
            + (
                '<button id="export" hidden onclick="document.querySelector(\'#eml\').hidden=false">Download</button>'
                f'<a id="eml" role="menuitem" href="{download}" download="test.eml" hidden>Download as EML</a>'
                if actions == "More items"
                else f'<a id="export" role="menuitem" href="{download}" download="test.eml" hidden>Save as</a>'
            )
        )
        page.route(
            "https://outlook.office.com/**",
            lambda route: route.fulfill(content_type="text/html", body=html),
        )
        page.goto(outlook.HOME + "id/test")
        assert inbox._read()["id"] == "<sent@example>"

    @pytest.mark.parametrize("failure", ["conversation", "link"])
    def test_export_refuse(self, inbox: outlook.Outlook, page: Page, failure: str) -> None:
        inbox.page = page
        html = '<div role="document" aria-label="Message body">message</div>'
        page.route(
            "https://outlook.office.com/**",
            lambda route: route.fulfill(
                content_type="text/html",
                body=html * (2 if failure == "conversation" else 1),
            ),
        )
        page.goto(outlook.HOME + ("id/test" if failure == "conversation" else ""))
        with pytest.raises(MiniError, match="individual messages|selected message"):
            inbox._read()

    @pytest.mark.parametrize("rows", ["empty", "unique", "duplicate"])
    def test_collect(
        self, inbox: outlook.Outlook, page: Page, monkeypatch: pytest.MonkeyPatch, rows: str
    ) -> None:
        inbox.page = page
        monkeypatch.setattr(inbox, "_search", Mock())
        read = Mock(return_value={"id": "test"})
        monkeypatch.setattr(inbox, "_read", read)
        row = '<div role="option" aria-label="Test message" aria-selected="true">Message</div>'
        page.set_content(
            "<div>No results.</div>"
            if rows == "empty"
            else '<div role="listbox" aria-label="Message list">'
            + row * (2 if rows == "duplicate" else 1)
            + '<div role="listbox" aria-label="file attachments">'
            '<div role="option" aria-label="form.docx">Attachment</div></div></div>'
        )
        if rows == "duplicate":
            with pytest.raises(MiniError, match="indistinguishable"):
                inbox._collect("test")
            read.assert_not_called()
        else:
            assert inbox._collect("test") == ([{"id": "test"}] if rows == "unique" else [])
            assert read.call_count == (1 if rows == "unique" else 0)

    @pytest.mark.parametrize("filename", ["form.docx", "form.pdf"])
    @pytest.mark.parametrize("hidden", [False, True], ids=["subject", "edit-subject"])
    def test_prepare(self, inbox: outlook.Outlook, page: Page, filename: str, hidden: bool) -> None:
        inbox.page = page
        inbox.db.execute("UPDATE events SET filename = ?", (filename,))
        page.route(
            "https://outlook.office.com/**",
            lambda route: route.fulfill(
                content_type="text/html",
                body=fakes.compose(filename, ready=False, hidden=hidden),
            ),
        )
        inbox.prepare("browser:local", "42", filename, b"form")
        assert inbox.prepared == "browser:local"
        assert page.get_by_role("textbox", name="Subject", exact=True).input_value() == (
            "UQU Risk Assessment Return Ref ID: 42"
        )
        assert page.locator("#upload").evaluate("input => input.files[0].size") == 4
        assert page.locator(".ms-PickerItem-root").get_attribute("data-email") == mail.RETURN_TO
        assert page.evaluate("window.sends") == 0

    @pytest.mark.parametrize(
        "change,error",
        [
            ("document.querySelector('#subject').value='different'", "subject or body"),
            (
                "document.querySelector('[contenteditable]').textContent='different'",
                "subject or body",
            ),
            (
                "document.querySelector('.ms-PickerItem-root').dataset.email='other@example.org'",
                "recipients",
            ),
            (
                "document.querySelector('[aria-label=Cc]').value='pending@example.org'",
                "recipients",
            ),
            ("document.querySelector('.ms-PickerItem-root').remove()", "recipients"),
            (
                "document.querySelector('.ms-BasePicker-text').className='unknown'",
                "unsupported",
            ),
            ("document.querySelector('#attachments').innerHTML=''", "attachments"),
            (
                "document.querySelector('#attachments').append(document.querySelector('#attachments button').cloneNode(true))",
                "attachments",
            ),
            (
                "document.querySelector('#attachments').insertAdjacentHTML('beforeend', '<div role=progressbar></div>')",
                "uploading",
            ),
        ],
        ids=[
            "subject",
            "body",
            "wrong-to",
            "pending-cc",
            "missing-to",
            "layout",
            "missing-file",
            "extra-file",
            "upload",
        ],
    )
    def test_refuse(self, inbox: outlook.Outlook, page: Page, change: str, error: str) -> None:
        inbox.page, inbox.prepared = page, "browser:local"
        page.set_content(fakes.compose())
        page.evaluate(change)
        with pytest.raises(MiniError, match=error):
            inbox.send("browser:local")
        assert page.evaluate("window.sends") == 0

    @pytest.mark.parametrize("saved", [True, False], ids=["saved-intent", "no-intent"])
    def test_send(self, inbox: outlook.Outlook, page: Page, saved: bool) -> None:
        inbox.page, inbox.prepared = page, "browser:local"
        page.set_content(fakes.compose())
        if not saved:
            inbox.db.execute("UPDATE events SET send_started = NULL")
        if saved:
            inbox.send("browser:local")
            assert page.evaluate("window.sends") == 1
            with pytest.raises(MiniError, match="no verified prepared reply"):
                inbox.send("browser:local")
            assert page.evaluate("window.sends") == 1
        else:
            with pytest.raises(MiniError, match="saved send intent"):
                inbox.send("browser:local")
            assert page.evaluate("window.sends") == 0


class TestOutlook:
    def test_parse(self) -> None:
        raw = fakes.eml(
            message_id="<clubs@example>",
            sender="Clubs <clubs@uqu.com.au>",
            subject="Re: Event Application Update  [Event ID: 42] - Sample Event",
            body="Your room booking is confirmed.\n\nOn yesterday wrote:\n> old text",
        )
        parsed = outlook.parse_message(raw, "https://outlook.office.com/mail/id/clubs")

        assert parsed["id"] == "<clubs@example>"
        assert parsed["from"]["emailAddress"]["address"] == "clubs@uqu.com.au"
        assert parsed["references"] == [
            "<request@example>",
            "<update@example>",
            "<update@example>",
        ]
        assert parsed["uniqueBody"]["content"] == "Your room booking is confirmed."
        assert parsed["body"]["content"].endswith("> old text")

    @pytest.mark.parametrize(
        "change,error",
        [
            ({"Message-ID": "bad"}, "Message-ID"),
            ({"Date": "bad", "Received": None}, "timestamp"),
            ({"Date": "bad"}, "sent date"),
            ({"Date": "Mon, 07 Sep 2026 12:00:00"}, "sent date"),
            ({"From": None}, "one sender"),
            ({"From": "one@example.org, two@example.org"}, "one sender"),
        ],
        ids=["identity", "timestamp", "sent-date", "timezone", "sender", "senders"],
    )
    def test_malformed(self, change: dict[str, Any], error: str) -> None:
        raw = fakes.eml(
            message_id="<test@example>",
            sender=mail.CLUBS_SENDER,
            subject="Update",
            body="Confirmed",
        )
        message = BytesParser(policy=policy.default).parsebytes(raw)
        for name, value in change.items():
            del message[name]
            if value is not None:
                message[name] = value
        with pytest.raises(MiniError, match=error):
            outlook.parse_message(message.as_bytes(), outlook.HOME + "id/test")

    @pytest.mark.parametrize(
        "quote",
        [
            "<blockquote>old reply</blockquote>",
            '<div id="divRplyFwd">old reply</div>',
            '<div class="gmail_quote">old reply</div>',
        ],
        ids=["blockquote", "outlook", "gmail"],
    )
    def test_html(self, quote: str) -> None:
        message = BytesParser(policy=policy.default).parsebytes(
            fakes.eml(
                message_id="<test@example>",
                sender=mail.CLUBS_SENDER,
                subject="Update",
                body="",
            )
        )
        message.replace_header("Received", "from mail.example; invalid date")
        message.set_content(
            "<style>hidden CSS</style><script>hidden JS</script>"
            "<p>Room confirmed<br>Thanks</p>" + quote,
            subtype="html",
        )
        parsed = outlook.parse_message(message.as_bytes(), outlook.HOME + "id/test")
        assert parsed["uniqueBody"]["content"] == "Room confirmed\nThanks"
        assert "old reply" in parsed["body"]["content"]
        assert "hidden" not in parsed["body"]["content"]
        assert parsed["receivedDateTime"] == parsed["sentDateTime"]

    def test_messages(self, inbox: outlook.Outlook, monkeypatch: pytest.MonkeyPatch) -> None:
        accepted = fakes.message("new", timestamp="2026-09-07T12:00:00+00:00")
        old = fakes.message("old", timestamp="2026-09-01T10:00:00+00:00")
        foreign = fakes.message("foreign", sender="other@example.org")
        collect = Mock(side_effect=[[accepted, old, foreign], []])
        monkeypatch.setattr(inbox, "_collect", collect)
        assert inbox.messages("2026-09-07T00:00:00+00:00") == [accepted]
        assert [call.args[0] for call in collect.call_args_list] == [
            f"from:{sender} received:>=2026-09-07"
            for sender in (mail.REQUEST_SENDER, mail.CLUBS_SENDER)
        ]
        assert inbox.message("new") == accepted
        with pytest.raises(MiniError, match="missing"):
            inbox.message("old")
        with pytest.raises(MiniError, match="missing"):
            inbox.create_reply("foreign")
        with pytest.raises(MiniError, match="Unknown browser draft"):
            inbox.message("browser:unknown")

    @pytest.mark.parametrize("changed", ["subject", "before-request", "content"])
    def test_reconcile(
        self, inbox: outlook.Outlook, monkeypatch: pytest.MonkeyPatch, changed: str
    ) -> None:
        sent = outlook.parse_message(fakes.sent(b"form"), outlook.HOME + "id/sent")
        if changed == "subject":
            sent["subject"] = "Another return"
        elif changed == "before-request":
            sent["sentDateTime"] = "2026-09-01T00:00:00Z"
        else:
            sent["body"]["content"] = "Changed reply"
        monkeypatch.setattr(inbox, "_collect", Mock(return_value=[sent]))
        if changed == "content":
            with pytest.raises(MiniError, match="different recipients, body or attachment"):
                inbox.message("browser:local")
        else:
            assert inbox.message("browser:local") == {
                "id": "browser:local",
                "isDraft": True,
            }

    def test_return(self) -> None:
        document = b"risk-form"
        email = EmailMessage()
        email.set_content(mail.BODY)
        email["Message-ID"] = "<sent@example>"
        email["From"] = "rad@example.org"
        email["To"] = mail.RETURN_TO
        email["Subject"] = "UQU Risk Assessment Return Ref ID: 42"
        email["Date"] = "Mon, 07 Sep 2026 12:00:00 +0000"
        email.add_attachment(
            document,
            maintype="application",
            subtype="octet-stream",
            filename="form.docx",
        )
        parsed = outlook.parse_message(email.as_bytes(), "https://outlook.office.com/mail/id/sent")

        assert outlook._same_return(parsed, "42", "form.docx", document, "rad@example.org")
        assert parsed["attachments"] == [
            {"name": "form.docx", "sha256": hashlib.sha256(document).hexdigest()}
        ]
        altered = {
            **parsed,
            "toRecipients": [{"emailAddress": {"address": "other@example.org"}}],
        }
        assert not outlook._same_return(altered, "42", "form.docx", document, "rad@example.org")
        altered = {**parsed, "body": {"content": mail.BODY + "\nextra"}}
        assert not outlook._same_return(altered, "42", "form.docx", document, "rad@example.org")
        altered = {**parsed, "attachments": [{"name": "form.docx", "sha256": "0" * 64}]}
        assert not outlook._same_return(altered, "42", "form.docx", document, "rad@example.org")
        quoted = outlook.parse_message(
            fakes.sent(document, body=f"{mail.BODY}\n\nOn yesterday wrote:\n> quoted text"),
            "https://outlook.office.com/mail/id/sent",
        )
        assert not outlook._same_return(quoted, "42", "form.docx", document, "rad@example.org")

    def test_draft(self, tmp_path: Path) -> None:
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
                "INSERT INTO browser_mail VALUES (?, ?)",
                ("<request@example>", json.dumps(fakes.request())),
            )
            identity = box.create_reply("<request@example>")
            assert identity.startswith("browser:")
            db.execute("UPDATE events SET draft_id = ? WHERE event_id = '42'", (identity,))
            box._collect = Mock(return_value=[])
            assert box.message(identity) == {"id": identity, "isDraft": True}

            sent = outlook.parse_message(
                fakes.sent(document), "https://outlook.office.com/mail/id/sent"
            )
            db.execute(
                "UPDATE events SET state = 'sending', send_started = ? WHERE event_id = '42'",
                ("2026-09-07T11:30:00+00:00",),
            )
            box._collect = Mock(return_value=[sent])
            assert box.message(identity)["id"] == "<sent@example>"

            box._collect = Mock(return_value=[sent, sent])
            with pytest.raises(MiniError, match="Multiple matching"):
                box.message(identity)
            unthreaded: dict[str, Any] = {**sent, "references": []}
            box._collect = Mock(return_value=[unthreaded])
            assert box.message(identity) == {"id": identity, "isDraft": True}

    def test_retry(self, event_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        state = tmp_path / "agent"
        event.watch(event_toml, event_id="42", since="2026-09-01", state_dir=state)

        class BrowserUI:
            def __init__(self):
                self.sent = self.attempt = 0
                self.prepared: list[tuple[str, str, str, bytes]] = []

            def messages(self, since: str):
                return [fakes.request()]

            def create_reply(self, request_id: str):
                return "browser:local"

            def message(self, identity: str):
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

            def prepare(self, *args: Any):
                self.prepared.append(args)

            def send(self, identity: str):
                self.attempt += 1
                if self.attempt == 1:
                    raise MiniError("browser closed while sending")
                self.sent += 1

        ui = BrowserUI()

        @contextmanager
        def connect(db: Connection):
            yield ui

        monkeypatch.setattr(mail, "connect", connect)
        monkeypatch.setattr(service, "notify", Mock(return_value=None))
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

    def test_login(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        opened: list[tuple[str, str | None, bool]] = []

        class Browser:
            def __init__(
                self,
                db: Connection,
                mailbox: str,
                *,
                username: str | None = None,
                interactive: bool = False,
            ):
                opened.append((mailbox, username, interactive))

            def __enter__(self):
                return self

            def __exit__(self, *args: Any):
                return False

        monkeypatch.setattr(outlook, "Outlook", Browser)
        state = tmp_path / "agent"
        event.login(mailbox="RAD@EXAMPLE.ORG", username="s123@uq.edu.au", state_dir=state)
        assert opened == [("rad@example.org", "s123@uq.edu.au", True)]
        with event.database(state) as db:
            assert json.loads(storage.setting(db, "account") or "{}") == {
                "backend": "browser",
                "mailbox": "rad@example.org",
                "username": "s123@uq.edu.au",
            }
        with pytest.raises(MiniError, match="another account"):
            event.login(mailbox="other@example.org", state_dir=state)

    def test_booking(
        self, event_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = tmp_path / "agent"
        event.watch(event_toml, event_id="42", state_dir=state)
        notices: list[tuple[str, str]] = []

        def notify(title: str, body: str) -> None:
            notices.append((title, body))

        monkeypatch.setattr(service, "notify", notify)
        reply = outlook.parse_message(
            fakes.eml(
                message_id="<clubs@example>",
                sender=mail.CLUBS_SENDER,
                subject="Re: Event Application Update  [Event ID: 42] - Sample Event",
                body="Your room is booked.",
            ),
            "https://outlook.office.com/mail/id/clubs",
        )
        box = cast(mail.Graph, SimpleNamespace(message=Mock(return_value=reply)))
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

    @pytest.mark.parametrize(
        "url,valid",
        [
            ("https://outlook.office.com/mail/id/test", True),
            ("https://outlook.cloud.microsoft/mail/id/test", True),
            ("https://outlook.cloud.microsoft.evil.test/mail/id/test", False),
            ("https://evil.test/mail/id/test", False),
            ("https://user@outlook.cloud.microsoft/mail/id/test", False),
            ("http://outlook.cloud.microsoft/mail/id/test", False),
            ("https://outlook.cloud.microsoft/other/id/test", False),
        ],
        ids=["office", "cloud", "suffix", "domain", "userinfo", "scheme", "path"],
    )
    def test_url(self, url: str, valid: bool) -> None:
        with nullcontext() if valid else pytest.raises(MiniError, match="mailbox link"):
            assert outlook._url(url) == url
