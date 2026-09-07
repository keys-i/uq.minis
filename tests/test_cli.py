from types import SimpleNamespace

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from typer.testing import CliRunner

from uq_minis import cli
from uq_minis.minis import event

runner = CliRunner()


@pytest.mark.parametrize(
    "tool,option",
    [
        ("event", "--mode"),
        ("event-form", "--preview"),
        ("event-risk", "--layout"),
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
            "--tool",
            "event",
            str(event_toml),
            "--mode",
            "form",
            "--no-input",
            "--preview",
            "-o",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert [path.name for path in output.iterdir()] == ["sample-event.form.json"]


def test_interactive_menu_and_missing_event_values(event_toml, monkeypatch):
    terminal = SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli, "sys", terminal)
    monkeypatch.setattr(event, "sys", terminal)
    event_toml.write_text(event_toml.read_text().replace('mode = "both"\n', ""))
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        pipe.send_text(f"event\n{event_toml}\nform\n")
        result = runner.invoke(cli.app, [])
    assert result.exit_code == 0, result.output
    assert (event_toml.parent / "generated/sample-event.form.json").exists()


def test_no_input_and_conflicting_submission_flags_fail_before_generation(event_toml, monkeypatch):
    monkeypatch.setattr(event, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True)))
    monkeypatch.setattr(event, "generate", lambda *args, **kwargs: pytest.fail("must not generate"))
    missing = runner.invoke(cli.app, ["--tool", "event", "--no-input"])
    assert missing.exit_code == 2 and "input is required" in missing.output
    for tool in ("event", "event-form"):
        conflict = runner.invoke(
            cli.app, ["--tool", tool, str(event_toml), "--submit", "--preview"]
        )
        assert conflict.exit_code == 2 and "mutually exclusive" in conflict.output
    invalid = runner.invoke(cli.app, ["--tool", "event", "--jobs", "-1"])
    assert invalid.exit_code == 2 and "Traceback" not in invalid.output
