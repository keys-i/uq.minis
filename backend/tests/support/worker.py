"""Shared test inputs, isolated state and terminal setup"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from playwright.sync_api import Browser

from tests import fakes
from tests.fakes import Mailbox
from uq_minis.worker import event as worker
from uq_minis.worker import mail, outlook, service


@pytest.fixture
def browser(monkeypatch: pytest.MonkeyPatch):
    page = Mock(url=outlook.HOME)
    context = Mock(pages=[page])
    context.new_page.return_value = page
    context.cookies.return_value = [
        {
            "name": "AADAuth.forms",
            "value": "signed-in",
            "domain": ".forms.cloud.microsoft",
        }
    ]
    instance = Mock()
    instance.new_context.return_value = context
    runtime = Mock()
    for name in ("chromium", "firefox", "webkit"):
        engine = getattr(runtime, name)
        engine.launch.return_value = instance
        engine.launch_persistent_context.return_value = context
    session = MagicMock()
    session.__enter__.return_value = session.start.return_value = runtime
    api = ModuleType("playwright.sync_api")
    api.__dict__["Error"] = fakes.BrowserError
    api.__dict__["sync_playwright"] = Mock(return_value=session)
    monkeypatch.setitem(sys.modules, api.__name__, api)
    return SimpleNamespace(page=page, context=context, instance=instance, runtime=runtime, api=api)


@pytest.fixture(scope="module")
def chromium():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).is_file():
            pytest.skip("Install Chromium to run the local browser checks")
        browser = runtime.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(chromium: Browser):
    with chromium.new_context() as context:
        context.route("**/*", lambda route: route.abort())
        page = context.new_page()
        page.set_default_timeout(1000)
        yield page


@pytest.fixture
def inbox(tmp_path: Path):
    with worker.database(tmp_path / "agent") as db:
        box = outlook.Outlook(db, "rad@example.org")
        db.execute(
            "INSERT INTO events (event_id,title,filename,document,since,state,draft_id,"
            "send_started,request_id,request_time,subject) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "42",
                "Sample Event",
                "form.docx",
                b"form",
                "2026-09-01T00:00:00Z",
                "sending",
                "browser:local",
                "2026-09-07T12:00:00Z",
                "<request@example>",
                "2026-09-07T11:00:00+00:00",
                "UQU Risk Assessment Return Ref ID: 42",
            ),
        )
        db.execute(
            "INSERT INTO browser_mail VALUES (?, ?)",
            ("<request@example>", json.dumps(fakes.request())),
        )
        yield box


@pytest.fixture
def macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(os, "getuid", lambda: 501, raising=False)


@pytest.fixture
def process(monkeypatch: pytest.MonkeyPatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(subprocess, "run", run)
    return run


@pytest.fixture
def job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home with spaces"
    monkeypatch.setattr(Path, "home", classmethod(Mock(return_value=home)))
    path = home / "Library/LaunchAgents/au.edu.uq.minis.agent.plist"
    path.parent.mkdir(parents=True)
    return path


@pytest.fixture
def watch(event_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state = tmp_path / "agent"
    worker.watch(event_toml, event_id="42", since="2026-09-01", state_dir=state)
    mailbox = Mailbox()
    notices: list[tuple[str, str]] = []
    monkeypatch.setattr(mail, "token", Mock(return_value="test-token"))
    monkeypatch.setattr(mail, "Graph", Mock(return_value=mailbox))

    def notify(title: str, body: str) -> None:
        notices.append((title, body))

    monkeypatch.setattr(service, "notify", notify)
    return state, mailbox, notices
