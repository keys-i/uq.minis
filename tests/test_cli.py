import json
from unittest.mock import Mock

import pytest
from rich.text import Text
from typer import rich_utils

from uq_minis import cli
from uq_minis.cli import event
from uq_minis.core.common import MiniError
from uq_minis.minis import agent
from uq_minis.minis import event as mini_event


class TestCLI:
    @pytest.mark.parametrize("error", [MiniError, OSError, cli.typer.BadParameter])
    def test_recover(self, module, monkeypatch, runner, tty, pipe, keys, error):
        from uq_minis.core import terminal

        answers, approvals = [], []

        def run():
            answers.append(terminal.ask("Name", default="guest"))
            approvals.append(terminal.confirm("Approve", default=False))
            if len(answers) == 1:
                raise error("Something needs correcting")

        module("new_mini", run)
        monkeypatch.setattr(cli, "sys", tty)
        keys("Mina\n", "y\n", "edit\n", "\n", "\n")
        result = runner.invoke(cli.app, ["new-mini"])
        assert result.exit_code == 0, result.output
        assert answers == ["Mina", "Mina"] and approvals == [True, False]
        assert "Something needs correcting" in result.output
        assert terminal._DRAFT.get() is None and not terminal._RESTORE.get()

    @pytest.mark.parametrize("action", ["menu\n", "\x1b[1;3D"])
    def test_failed_back(self, module, monkeypatch, runner, tty, pipe, keys, action):
        calls = []

        def run():
            calls.append(True)
            raise MiniError("Try another file")

        module("new_mini", run)
        monkeypatch.setattr(cli, "sys", tty)
        keys(action, "\x03")
        result = runner.invoke(cli.app, ["new-mini"])
        assert result.exit_code == 0, result.output
        assert calls == [True] and "Choose a tool" in result.output

    def test_no_input(self, module, monkeypatch, runner, tty):
        def run(no_input: bool = False):
            raise MiniError("Needs a different source")

        module("new_mini", run)
        monkeypatch.setattr(cli, "sys", tty)
        result = runner.invoke(cli.app, ["new-mini", "--no-input"])
        assert result.exit_code == 2 and "What next" not in result.output

    @pytest.mark.parametrize(
        "tool,option",
        [
            ("event", "--form"),
            ("auth", "--browser"),
            ("agent", "login"),
            ("scrappy", "details"),
            ("timey", "--length"),
        ],
    )
    @pytest.mark.parametrize("selector", [[], ["--tool"]], ids=["direct", "option"])
    @pytest.mark.parametrize("coloured", [False, True], ids=["plain", "colour"])
    def test_help(self, tool, option, selector, runner, monkeypatch, coloured):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setattr(rich_utils, "FORCE_TERMINAL", coloured)
        result = runner.invoke(cli.app, [*selector, tool, "--help"], color=coloured)
        assert result.exit_code == 0, result.output
        assert option in Text.from_ansi(result.output).plain
        assert ("\x1b[" in result.output) == coloured
        assert "Choose a tool" not in result.output

    @pytest.mark.parametrize("tool", ["not-a-mini", "agents"])
    def test_unknown(self, tool, runner):
        result = runner.invoke(cli.app, ["--tool", tool])
        assert result.exit_code == 2
        assert "unknown tool" in result.output
        assert "Traceback" not in result.output

    def test_list(self, runner):
        result = runner.invoke(cli.app, [])
        assert result.exit_code == 0, result.output
        assert "UQ minis" in result.output

    def test_preview(self, event_toml, tmp_path, runner):
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

    @pytest.mark.parametrize("name", ["new_mini", "core", "completion"])
    def test_generic(self, module, name, runner):
        called: list[str] = []

        def run(value: str) -> None:
            called.append(value)

        module(name, run)
        result = runner.invoke(cli.app, [name.replace("_", "-"), "done"])
        assert result.exit_code == 0, result.output
        assert called == ["done"]

    def test_menu(self, event_toml, monkeypatch, pipe, runner, tty):
        terminal = tty
        monkeypatch.setattr(cli, "sys", terminal)
        monkeypatch.setattr(event, "sys", terminal)
        visitor = Mock(return_value=cli._habitats()["huia"])
        monkeypatch.setattr(cli.random, "choice", visitor)
        event_toml.write_text(event_toml.read_text().replace('mode = "both"\n', ""))
        pipe.send_text(f"event\n{event_toml}\nform\n")
        result = runner.invoke(cli.app, [])
        assert result.exit_code == 0, result.output
        assert (event_toml.parent / "generated/sample-event.form.json").exists()
        animals = visitor.call_args.args[0]
        assert len(animals) == 50
        assert len({pet.animal for pet in animals}) == 50
        assert set(animals) == set(cli._habitats().values())
        assert not visitor.call_args.kwargs

    @pytest.mark.parametrize("args", [[], ["new-mini"]], ids=["menu", "direct"])
    def test_back(self, module, monkeypatch, runner, tty, pipe, keys, args):
        from uq_minis.core import terminal

        reached = []

        def run():
            terminal.ask("Name", required=True)
            reached.append(True)

        module("new_mini", run)
        monkeypatch.setattr(cli, "sys", tty)
        keys(*([] if args else ["new-mini\n"]), "\x1b[1;3D", "\x03")
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 0, result.output
        assert "Choose a tool" in result.output
        assert reached == []
        assert terminal._HABITAT.get() is None

    @pytest.mark.parametrize(
        "args,error",
        [
            (["event", "--no-input"], "input is required"),
            (["event", "event.toml", "--submit", "--preview"], "mutually exclusive"),
            (["event", "--jobs", "-1"], "--jobs"),
            (["agent", "login", "--client-id", "id"], "Missing option"),
        ],
        ids=[
            "missing-input",
            "conflicting-actions",
            "invalid-jobs",
            "missing-login-options",
        ],
    )
    def test_invalid(self, event_toml, monkeypatch, args, error, runner, tty):
        monkeypatch.chdir(event_toml.parent)
        monkeypatch.setattr(event, "sys", tty)
        monkeypatch.setattr(
            mini_event,
            "generate",
            lambda *args, **kwargs: pytest.fail("must not generate"),
        )
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 2, result.output
        assert error in result.output and "Traceback" not in result.output

    @pytest.mark.parametrize("selector", [[], ["--tool"]], ids=["direct", "option"])
    @pytest.mark.parametrize("saved", [True, False], ids=["saved", "empty"])
    @pytest.mark.parametrize("as_json", [False, True], ids=["pretty", "json"])
    def test_status(self, tmp_path, monkeypatch, selector, runner, saved, as_json):
        rows = [{"event_id": "42", "title": "Sample Event", "state": "registered"}] if saved else []
        monkeypatch.setattr(
            agent,
            "status",
            lambda **_: rows,
        )
        result = runner.invoke(
            cli.app,
            [
                *selector,
                "agent",
                "status",
                "--state-dir",
                str(tmp_path),
                *(["--json"] if as_json else []),
            ],
        )
        assert result.exit_code == 0, result.output
        if as_json:
            assert json.loads(result.output) == rows
        elif saved:
            assert "registered" in result.output and "State" in result.output
        else:
            assert "Nothing to keep an eye on" in result.output
            assert "mini agent watch" in result.output

    def test_watch(self, event_toml, tmp_path, runner):
        state = tmp_path / "state"
        common = ["--state-dir", str(state)]
        watched = runner.invoke(
            cli.app,
            [
                "agent",
                "watch",
                str(event_toml),
                "--event-id",
                "42",
                "--since",
                "2026-09-01",
                *common,
            ],
        )
        assert watched.exit_code == 0, watched.output
        assert json.loads(watched.output)["event_id"] == "42"
        stopped = runner.invoke(cli.app, ["agent", "stop", "42", *common])
        assert stopped.exit_code == 0, stopped.output
        status = runner.invoke(cli.app, ["agent", "status", "--json", *common])
        assert status.exit_code == 0, status.output
        assert json.loads(status.output)[0]["state"] == "stopped"
        assert runner.invoke(cli.app, ["agent", "poll", *common]).exit_code == 0

    @pytest.mark.parametrize(
        "args,error",
        [
            (["agent", "status"], "agent state is unavailable"),
            (["scrappy", "links", "--html", "missing.html"], "missing.html"),
        ],
        ids=["agent", "scrappy"],
    )
    def test_errors(self, tmp_path, monkeypatch, args, error, runner):
        monkeypatch.chdir(tmp_path)

        def unavailable(**_):
            raise MiniError("agent state is unavailable")

        monkeypatch.setattr(agent, "status", unavailable)
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 2
        assert error in result.output and "Traceback" not in result.output
