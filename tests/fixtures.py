"""Shared test inputs, isolated state and terminal setup"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path
from threading import Timer
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock

import prompt_toolkit
import pytest
from prompt_toolkit.application import create_app_session, get_app, get_app_session
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output import DummyOutput
from rich.console import Console
from typer.testing import CliRunner

from tests import fakes
from tests.fakes import Mailbox
from uq_minis import cli
from uq_minis.core import cache, mini, terminal
from uq_minis.core.forms import FormProfile
from uq_minis.minis.scrappy import scraper
from uq_minis.minis.timey import preview, style, video
from uq_minis.worker import event as worker
from uq_minis.worker import mail, outlook, service
from uq_minis_tools.scripts import script


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def pipe(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    with create_pipe_input() as input, create_app_session(input=input, output=DummyOutput()):
        token = terminal._RECENT.set(())
        try:
            yield input
        finally:
            terminal._RECENT.reset(token)


@pytest.fixture
def entry(monkeypatch):
    prompt = Mock(return_value="first")
    monkeypatch.setattr(prompt_toolkit, "prompt", prompt)
    return prompt


@pytest.fixture
def cursor(monkeypatch):
    buffer = SimpleNamespace(
        text="", complete_state=SimpleNamespace(current_completion=None), start_completion=Mock()
    )
    app = SimpleNamespace(
        current_buffer=buffer, layout=Layout(Window(FormattedTextControl())), invalidate=Mock()
    )
    clock = Mock(return_value=0)
    monkeypatch.setattr(terminal.time, "monotonic", clock)
    monkeypatch.setattr(prompt_toolkit.application, "get_app", lambda: app)
    monkeypatch.setattr(terminal.random, "uniform", lambda *args: 3)
    monkeypatch.setattr(terminal.random, "choice", lambda choices: "play")
    return buffer, clock, app


@pytest.fixture
def videos(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.extract_info.return_value = {
        "entries": [{"id": "abcdefghijk", "title": "A quiet forest", "duration": 83}]
    }
    factory = Mock(return_value=client)
    monkeypatch.setattr(video, "YoutubeDL", factory)
    return factory, client


@pytest.fixture
def thumbnails(monkeypatch):
    from io import BytesIO

    with BytesIO() as buffer:
        video.Image.new("RGB", (48, 36), "#e8a37e").save(buffer, format="PNG")
        payload = buffer.getvalue()
    reply = MagicMock()
    reply.__enter__.return_value = reply
    reply.iter_bytes.return_value = [payload]
    monkeypatch.setattr(preview.httpx, "stream", Mock(return_value=reply))
    return reply


@pytest.fixture
def canvas(pipe, screen, monkeypatch):
    frames = []
    native = prompt_toolkit.prompt

    def draw(*args, **kwargs):
        app = None

        def sample(app):
            view = app.renderer.last_rendered_screen
            if view:
                frames.append(
                    [
                        "".join(
                            view.data_buffer[y][x].char
                            for x in range(get_app_session().output.get_size().columns)
                        )
                        for y in range(view.height)
                    ]
                )

        def ready():
            nonlocal app
            app = get_app()
            kwargs["pre_run"]()
            app.after_render += sample
            app.loop.set_exception_handler(
                lambda loop, context: app.exit(exception=context["exception"])
            )

        try:
            return native(*args, **{**kwargs, "pre_run": ready})
        finally:
            if app:
                app.after_render -= sample

    monkeypatch.setattr(prompt_toolkit, "prompt", draw)

    def setup(width=80, rows=24, no_color=False):
        screen(width=width, live=True, no_color=no_color)
        monkeypatch.setattr(
            get_app_session().output, "get_size", lambda: Size(rows=rows, columns=width)
        )
        monkeypatch.setattr(
            get_app_session().output, "get_rows_below_cursor_position", lambda: rows
        )
        return frames

    return setup


@pytest.fixture
def keys(pipe):
    timers = []

    def send(*texts):
        for index, text in enumerate(texts):
            timer = Timer(0.05 + index * 0.1, pipe.send_text, args=(text,))
            timers.append(timer)
            timer.start()

    yield send
    for timer in timers:
        timer.join()


@pytest.fixture
def tab(pipe, monkeypatch):
    pending = []
    prompt = prompt_toolkit.prompt

    def complete(*args, **kwargs):
        if not pending:
            return prompt(*args, **kwargs)
        prefix = pending.pop(0)
        before = kwargs.get("pre_run")
        handles = []

        def select(buffer):
            if buffer.text == prefix and buffer.complete_state:
                buffer.on_completions_changed -= select
                pipe.send_text("\t\n")

        def ready():
            app = get_app()
            app.current_buffer.on_completions_changed += select
            handles.append(app.current_buffer)
            handles.append(
                app.loop.call_later(
                    5, lambda: app.exit(exception=TimeoutError("No completions appeared"))
                )
            )
            if before:
                before()
            pipe.send_text(prefix)

        try:
            return prompt(*args, **{**kwargs, "pre_run": ready})
        finally:
            if handles:
                handles[0].on_completions_changed -= select
                handles[1].cancel()

    monkeypatch.setattr(prompt_toolkit, "prompt", complete)

    def send(prefix):
        pending.append(prefix)

    return send


@pytest.fixture
def screen(monkeypatch):
    def make(*, width=80, live=False, no_color=False):
        monkeypatch.setenv("TERM", "xterm-256color")
        output = StringIO()
        console = Console(
            file=output,
            width=width,
            force_terminal=live,
            no_color=no_color,
            theme=terminal.THEME,
            highlight=False,
            color_system="truecolor",
        )
        monkeypatch.setattr(terminal, "CONSOLE", console)
        return console, output

    return make


@pytest.fixture
def event_toml(tmp_path: Path) -> Path:
    path = tmp_path / "event.toml"
    path.write_text(
        """
[output]
mode = "both"
risk_layout = "both"

[document]
output_name = "sample-event"

[form]
action = "preview"
started_at = "2026-09-04T02:31:00.471Z"
submitted_at = "2026-09-04T02:41:24.046Z"

[form.values]
affiliated = "Yes"
date_flexibility = "Not really"
under_18 = "0"
non_uq = "0"
venue_capacity = "21-50"
option_28 = "No"
food = "Pizza + drinks"
option_30 = "No"
option_31 = "No"
option_32 = "No"
terms = "Agree"

[club]
name = "UQ Sample Club"
short_name = "Sample Club"
executives = "UQ Sample Club Executives"
event_officer = "UQ Sample Club Events Officer"

[event]
title = "Sample Event"
date = 2026-09-15
campus = "St Lucia"
room = "03-309"
building = "Steele Building"
category = "Small"
summary = "A small indoor club event."
risk_scope = "Arrival, a seated activity, refreshments and pack-up."
target_audience = "UQ students"
estimated_attendance = "20"
activity = "a seated activity"
entertainment = "quiet presentations"
stakeholders = ["club executives", "attendees"]

[coordinator]
name = "Sample Coordinator"
role = "Events Officer"
email = "sample@example.com"
phone = "0400000000"

[schedule]
setup_start = 17:45:00
setup_end = 18:00:00
event_start = 18:00:00
event_end = 20:00:00
pack_up_start = 20:00:00
pack_up_end = 20:15:00

[catering]
provided = true
description = "commercially prepared pizza and soft drinks"

[operations]
indoor = true
seated = true
vehicles = false
temporary_structures = false
electrical_equipment = true
equipment = "existing UQ AV equipment, laptops and chargers"
cash_handling = false
payment_method = "approved cashless methods"
alcohol = false
physical_competitions = false
off_site_impact = false

[application]
title = "Sample Event Pack"

[application.fields]
"External attendees" = 0
"Terms accepted" = true
"Drinks" = ["Solo", "Sunkist"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(mini, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "src/minis").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "movie night.toml").touch()
    (tmp_path / "events").mkdir()
    return tmp_path


@pytest.fixture
def profile() -> FormProfile:
    return FormProfile(
        Path("profile.toml"),
        "https://forms.cloud.microsoft/formapi/api/tenant/forms('form')/responses",
        "https://forms.cloud.microsoft/pages/responsepage.aspx?id=form",
        "https://forms.cloud.microsoft",
        "business",
        "en-AU",
        False,
        (),
        "COOKIE",
        "TOKEN",
        "SESSION",
        "MUID",
    )


@pytest.fixture
def browser(monkeypatch):
    page = Mock(url=outlook.HOME)
    context = Mock(pages=[page])
    context.new_page.return_value = page
    context.cookies.return_value = [
        {"name": "AADAuth.forms", "value": "signed-in", "domain": ".forms.cloud.microsoft"}
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
    api.Error = fakes.BrowserError
    api.sync_playwright = Mock(return_value=session)
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
def page(chromium):
    with chromium.new_context() as context:
        context.route("**/*", lambda route: route.abort())
        page = context.new_page()
        page.set_default_timeout(1000)
        yield page


@pytest.fixture
def inbox(tmp_path):
    with worker.database(tmp_path / "agent") as db:
        box = outlook.Outlook(db, "rad@example.org")
        db.execute(
            "INSERT INTO events (event_id,title,filename,document,since,state,draft_id,"
            "send_started,request_id,request_time) VALUES (?,?,?,?,?,?,?,?,?,?)",
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
            ),
        )
        db.execute(
            "INSERT INTO browser_mail VALUES (?, ?)",
            ("<request@example>", json.dumps(fakes.request())),
        )
        yield box


@pytest.fixture
def cached(tmp_path):
    root = tmp_path / "cache"
    source = tmp_path / "payload.bin"
    source.write_bytes(b"completed")
    key = f"{'0' * 16}-{'a' * 16}"
    cache.save(root, key, source, {"file": source.name})
    return root, source, root / key


@pytest.fixture
def macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(service.os, "getuid", lambda: 501, raising=False)


@pytest.fixture
def process(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(service.subprocess, "run", run)
    return run


@pytest.fixture
def job(tmp_path, monkeypatch):
    home = tmp_path / "home with spaces"
    monkeypatch.setattr(service.Path, "home", classmethod(lambda cls: home))
    path = home / "Library/LaunchAgents/au.edu.uq.minis.agent.plist"
    path.parent.mkdir(parents=True)
    return path


@pytest.fixture
def watch(event_toml, tmp_path, monkeypatch):
    state = tmp_path / "agent"
    worker.watch(event_toml, event_id="42", since="2026-09-01", state_dir=state)
    mailbox = Mailbox()
    notices = []
    monkeypatch.setattr(mail, "token", lambda db: "test-token")
    monkeypatch.setattr(mail, "Graph", lambda token: mailbox)
    monkeypatch.setattr(service, "notify", lambda title, body: notices.append((title, body)))
    return state, mailbox, notices


@pytest.fixture
def offerings(tmp_path, courses):
    html, csv = tmp_path / "search.html", tmp_path / "links.csv"
    listing = '<h2 class="trigger"><a class="code">COMP3400</a><a class="title">Logic</a></h2><a href="/course.html?course_code=COMP3400">View all previous offerings</a>'
    html.write_text(listing + listing.replace("COMP3400", "CSSE2002"))
    scraper.export_links(csv, html=html)
    return csv


@pytest.fixture
def draft():
    return {
        "snippet": {"title": "Minecraft timer", "description": "", "tags": []},
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }


@pytest.fixture
def art():
    return {
        "name": "Hollow Knight",
        "font": "serif",
        "shapes": [
            {
                "kind": "round",
                "points": [[0, 0], [540, 234]],
                "colour": "#101830EE",
                "width": 1,
                "radius": 24,
            },
            {
                "kind": "line",
                "points": [[12, 12], [528, 12]],
                "colour": "#BBCFFF",
                "width": 3,
                "radius": 0,
            },
            {
                "kind": "polygon",
                "points": [[15, 40], [30, 20], [45, 40]],
                "colour": "#FFFFFF",
                "width": 1,
                "radius": 0,
            },
            {
                "kind": "ellipse",
                "points": [[480, 20], [515, 55]],
                "colour": "#BBCFFF",
                "width": 1,
                "radius": 0,
            },
        ],
        "text": {
            key: {
                "point": [270, top],
                "size": size,
                "colour": "#FFFFFF",
                "outline": "#101830",
                "stroke": 1,
            }
            for key, top, size in (("label", 30, 20), ("timer", 80, 60), ("caption", 155, 16))
        },
        "bar": {
            "points": [[35, 190], [505, 200]],
            "colour": "#BBCFFF",
            "background": "#252F42",
            "segments": 8,
        },
    }


@pytest.fixture
def designer(monkeypatch, art):
    result = SimpleNamespace(
        calls=[],
        status=0,
        output={"codex": json.dumps(art), "claude": json.dumps({"structured_output": art})},
    )
    monkeypatch.setattr(style.shutil, "which", lambda name: f"/bin/{name}")

    def run(argv, **kwargs):
        from io import BytesIO

        result.calls.append(argv)
        if "exec" in argv:
            Path(argv[argv.index("-o") + 1]).write_text(result.output["codex"])
            assert argv[argv.index("--sandbox") + 1] == "read-only"
            assert "--ephemeral" in argv and "--output-schema" in argv
        else:
            assert argv[argv.index("--tools") + 1] == ""
            kwargs["stdout"].write(result.output["claude"].encode())
            kwargs["stdout"].flush()
        return SimpleNamespace(
            stdin=BytesIO(), poll=lambda: result.status, returncode=result.status
        )

    monkeypatch.setattr(style.subprocess, "Popen", run)
    return result


@pytest.fixture
def courses(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "STATE", tmp_path / ".minis")


@pytest.fixture
def tty():
    return SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))


@pytest.fixture
def module(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "cli/__init__.py"))

    def add(name, run):
        source = tmp_path / "minis" / name
        source.mkdir(parents=True)
        (source / "__init__.py").touch()
        result = ModuleType(f"uq_minis.minis.{name}")
        result.run = run
        monkeypatch.setitem(sys.modules, result.__name__, result)
        return result

    return add


@pytest.fixture
def commands(monkeypatch):
    run = Mock(return_value=0)
    monkeypatch.setattr(script, "run", run)
    return run


@pytest.fixture
def clip(tmp_path):
    pytest.importorskip("PIL.Image")
    if not all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe")):
        pytest.skip("FFmpeg is an optional native video tool")

    def make(name, source, seconds=1, *, audio=False, options=()):
        path = tmp_path / name
        argv = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source]
        if audio:
            argv += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
        argv += ["-t", str(seconds), "-c:v", "libx264"]
        if audio:
            argv += ["-c:a", "aac"]
        subprocess.run([*argv, *options, str(path)], check=True, capture_output=True)
        return path

    return make
