"""Check command routing and real Tab input without running a mini"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Timer
from types import ModuleType
from typing import Literal

import pytest
import typer
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from typer._completion_classes import BashComplete
from typer.main import get_command
from typer.testing import CliRunner

from uq_minis import cli
from uq_minis.helper.prompt import ask
from uq_minis.minis import auth, event
from uq_minis_tools.scripts import script
from uq_minis_tools.scripts.completion import zsh_script


@pytest.mark.parametrize(
    "args,incomplete,expected",
    [
        ([], "", ["add", "rm", "list"]),
        ([], "--t", ["--tool"]),
        (["--tool"], "ev", ["event", "event-form", "event-risk"]),
        (["--tool", "event-risk"], "--l", ["--layout", "--logo"]),
        (["--tool", "event-risk", "--layout"], "f", ["form"]),
        (["--tool=event-risk"], "--layout=f", ["form"]),
        (["--tool", "event", "--mode"], "b", ["both"]),
        (["--tool", "event-form"], "--pr", ["--preview"]),
        (["--tool", "auth", "--browser"], "ch", ["chromium", "chrome"]),
        (["rm"], "ev", ["event", "event-form", "event-risk"]),
    ],
)
def test_completion_uses_selected_typer_app(args, incomplete, expected, monkeypatch):
    monkeypatch.setattr(event, "generate", lambda **kwargs: pytest.fail("must not generate"))
    monkeypatch.setattr(auth, "capture", lambda **kwargs: pytest.fail("must not open a browser"))
    completion = BashComplete(get_command(cli.app), {}, "mini", "_MINI_COMPLETE")
    assert [item.value for item in completion.get_completions(args, incomplete)] == expected


def test_paths_and_prompt_tab_completion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "movie night.toml").touch()
    (tmp_path / "events").mkdir()
    completion = BashComplete(get_command(cli.app), {}, "mini", "_MINI_COMPLETE")
    for args in (
        ["--tool", "event"],
        ["--tool", "event-form", "--form-profile"],
        ["--tool", "event-risk", "--logo"],
        ["--tool", "auth", "-o"],
    ):
        assert [item.value for item in completion.get_completions(args, "mov")] == [
            "movie night.toml"
        ]
    assert [
        item.value for item in completion.get_completions(["--tool", "event-risk", "-o"], "ev")
    ] == ["events/"]
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        pipe.send_text("mov")
        Timer(0.05, lambda: pipe.send_text("\t")).start()
        Timer(0.15, lambda: pipe.send_text("\n")).start()
        assert ask("Event TOML") == "movie night.toml"
        pipe.send_text("event-r")
        Timer(0.05, lambda: pipe.send_text("\t")).start()
        Timer(0.15, lambda: pipe.send_text("\n")).start()
        assert ask("Tool", choices=("event", "event-form", "event-risk")) == "event-risk"


def test_dev_command_completion():
    completion = BashComplete(get_command(script.app), {}, "dev", "_DEV_COMPLETE")
    assert [item.value for item in completion.get_completions([], "li")] == ["lint"]


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh is not installed")
def test_zsh_uv_hook(tmp_path):
    root = Path(__file__).resolve().parents[1]
    generated = tmp_path / "completion.zsh"
    generated.write_text(zsh_script())
    assert "external_command:_normal" in generated.read_text()
    result = subprocess.run(
        [
            "zsh",
            "-f",
            "-c",
            """source "$1"
_arguments() { print -rl -- "$@"; }
words=(mini --tool event-risk --layout f)
CURRENT=5
_mini_completion
words=(dev li)
CURRENT=2
_dev_completion
_files() { print NATIVE_PATH_COMPLETION; }
words=(mini --tool event-risk examples/mo)
CURRENT=4
_mini_completion
""",
            "zsh",
            str(generated),
        ],
        cwd=root,
        env={**os.environ, "UV_CACHE_DIR": str(tmp_path / "uv")},
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"form"' in result.stdout and '"lint"' in result.stdout, result.stderr
    assert "NATIVE_PATH_COMPLETION" in result.stdout, result.stderr


def test_new_mini_completion_comes_from_its_types(tmp_path, monkeypatch):
    source = tmp_path / "minis/new_mini"
    source.mkdir(parents=True)
    (source / "__init__.py").touch()
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "cli/__init__.py"))
    module = ModuleType("uq_minis.minis.new_mini")
    module.app = typer.Typer(add_completion=False)

    @module.app.command()
    def run(source: Path, flavor: Literal["plain", "spicy"] = "plain"):
        pytest.fail("completion must not run the command")

    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "event.toml").touch()
    completion = BashComplete(get_command(cli.app), {}, "mini", "_MINI_COMPLETE")
    for args, incomplete, expected in (
        (["--tool"], "new", ["new-mini"]),
        (["--tool", "new-mini"], "--fl", ["--flavor"]),
        (["--tool", "new-mini", "--flavor"], "sp", ["spicy"]),
        (["--tool", "new-mini"], "ev", ["event.toml"]),
    ):
        assert [item.value for item in completion.get_completions(args, incomplete)] == expected


def test_generated_completion_install_is_idempotent(tmp_path, monkeypatch):
    import typer.completion

    monkeypatch.setattr(typer.completion, "_get_shell_name", lambda: "zsh")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    rc = tmp_path / ".zshrc"
    rc.write_text("# Existing shell configuration\n")
    runner = CliRunner()
    shown = runner.invoke(cli.app, ["--show-completion"])
    assert shown.exit_code == 0, shown.output
    assert "external_command:_normal" in shown.output and "_mini_completion" in shown.output
    for _ in range(2):
        installed = runner.invoke(cli.app, ["--install-completion"])
        assert installed.exit_code == 0, installed.output
    assert rc.read_text().startswith("# Existing shell configuration\n")
    assert rc.read_text().count("source ") == 1
    assert (tmp_path / ".zfunc/uq-minis.zsh").read_text() == shown.output


def test_help_does_not_import_document_or_browser_libraries():
    subprocess.run(
        [
            sys.executable,
            "-c",
            """import sys
from typer.testing import CliRunner
from uq_minis.cli import app
for name in ("auth", "event", "event-form", "event-risk"):
    result = CliRunner().invoke(app, ["--tool", name, "--help"])
    assert result.exit_code == 0, result.output
assert not {"docx", "httpx", "playwright", "prompt_toolkit"}.intersection(sys.modules)
""",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
