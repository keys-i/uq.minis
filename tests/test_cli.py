import sys
from types import ModuleType, SimpleNamespace

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from typer.testing import CliRunner

from uq_minis import cli
from uq_minis.cli import commands
from uq_minis.helper.common import MiniError
from uq_minis.minis import agent
from uq_minis.minis.event import pipeline

runner = CliRunner()


@pytest.mark.parametrize(
    "tool,option",
    [
        ("event", "--form"),
        ("auth", "--browser"),
    ],
)
def test_tool_help_is_forwarded(tool, option):
    result = runner.invoke(cli.app, ["--tool", tool, "--help"])
    assert result.exit_code == 0, result.output
    assert option in result.output
    assert "Choose a tool" not in result.output


def test_dispatcher_lists_and_rejects_unknown_tools():
    assert runner.invoke(cli.app, []).exit_code == 0
    result = runner.invoke(cli.app, ["--tool", "not-a-mini"])
    assert result.exit_code == 2
    assert "unknown tool" in result.output
    assert "Traceback" not in result.output


def test_noninteractive_dispatch_forwards_flags_and_paths(event_toml, tmp_path):
    output = tmp_path / "output with spaces"
    result = runner.invoke(
        cli.app,
        [
            "event",
            str(event_toml),
            "--form",
            "--no-input",
            "--preview",
            "-o",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert [path.name for path in output.iterdir()] == ["sample-event.form.json"]


def test_direct_generic_mini_runs_plain_run(tmp_path, monkeypatch):
    source = tmp_path / "minis/new_mini"
    source.mkdir(parents=True)
    (source / "__init__.py").touch()
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "cli/__init__.py"))
    module = ModuleType("uq_minis.minis.new_mini")
    called: list[str] = []

    def run(value: str) -> None:
        called.append(value)

    module.run = run
    monkeypatch.setitem(sys.modules, module.__name__, module)
    result = runner.invoke(cli.app, ["new-mini", "done"])
    assert result.exit_code == 0, result.output
    assert called == ["done"]


def test_interactive_menu_and_missing_event_values(event_toml, monkeypatch):
    terminal = SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli, "sys", terminal)
    monkeypatch.setattr(commands, "sys", terminal)
    event_toml.write_text(event_toml.read_text().replace('mode = "both"\n', ""))
    with (
        create_pipe_input() as pipe,
        create_app_session(input=pipe, output=DummyOutput()),
    ):
        pipe.send_text(f"event\n{event_toml}\nform\n")
        result = runner.invoke(cli.app, [])
    assert result.exit_code == 0, result.output
    assert (event_toml.parent / "generated/sample-event.form.json").exists()


def test_no_input_and_conflicting_submission_flags_fail_before_generation(event_toml, monkeypatch):
    monkeypatch.setattr(
        commands, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
    )
    monkeypatch.setattr(
        pipeline, "generate", lambda *args, **kwargs: pytest.fail("must not generate")
    )
    missing = runner.invoke(cli.app, ["--tool", "event", "--no-input"])
    assert missing.exit_code == 2 and "input is required" in missing.output
    conflict = runner.invoke(cli.app, ["--tool", "event", str(event_toml), "--submit", "--preview"])
    assert conflict.exit_code == 2 and "mutually exclusive" in conflict.output
    invalid = runner.invoke(cli.app, ["--tool", "event", "--jobs", "-1"])
    assert invalid.exit_code == 2 and "Traceback" not in invalid.output


def test_agent_login_requires_ids_and_status_renders_state(tmp_path, monkeypatch):
    invalid = runner.invoke(cli.app, ["--tool", "agent", "login", "--client-id", "id"])
    assert invalid.exit_code == 2 and "Missing option" in invalid.output

    monkeypatch.setattr(
        agent,
        "status",
        lambda **_: [
            {
                "event_id": "42",
                "title": "Sample Event",
                "state": "registered",
                "outcome": "",
                "error": "",
                "details": "",
                "link": "",
            }
        ],
    )
    result = runner.invoke(cli.app, ["--tool", "agent", "status", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "registered" in result.output and "State" in result.output


def test_dispatcher_reports_agent_errors(tmp_path, monkeypatch):
    def unavailable(**_):
        raise MiniError("agent state is unavailable")

    monkeypatch.setattr(agent, "status", unavailable)
    result = runner.invoke(cli.app, ["agent", "status", "--state-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert "agent state is unavailable" in result.output and "Traceback" not in result.output


def test_direct_scrappy_errors_are_friendly(tmp_path):
    result = runner.invoke(cli.app, ["scrappy", "links", "--html", str(tmp_path / "missing.html")])
    assert result.exit_code == 2
    assert "missing.html" in result.output and "Traceback" not in result.output
