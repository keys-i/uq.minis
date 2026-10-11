"""Check command routing and real Tab input without running a mini"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

import pytest
from typer._completion_classes import BashComplete
from typer.main import get_command

from uq_minis import cli
from uq_minis.cli.completion import zsh_script
from uq_minis.core.terminal import ask
from uq_minis_tools.scripts import script


class TestCompletion:
    @pytest.mark.parametrize(
        "prefix,options,expected",
        [
            ("mov", {"paths": True, "required": True}, "movie night.toml"),
            ("event", {"choices": ("event",)}, "event"),
        ],
        ids=["path", "choice"],
    )
    def test_tab(self, paths, tab, prefix, options, expected):
        tab(prefix)
        assert ask("Choose", **options) == expected

    @pytest.mark.skipif(not shutil.which("zsh"), reason="zsh is not installed")
    def test_zsh(self, tmp_path):
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
words=(mini --tool event --layout f)
CURRENT=5
_mini_completion
words=(dev li)
CURRENT=2
_dev_completion
_files() { print NATIVE_PATH_COMPLETION; }
words=(mini --tool event examples/mo)
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

    @pytest.mark.parametrize(
        "args,incomplete,expected",
        [
            (["--tool"], "new", ["new-mini"]),
            (["--tool", "new-mini"], "--fl", ["--flavor"]),
            (["--tool", "new-mini", "--flavor"], "sp", ["spicy"]),
            (["--tool", "new-mini"], "ev", ["event.toml"]),
            ([], "new", ["new-mini"]),
            (["new-mini"], "--fl", ["--flavor"]),
        ],
        ids=["tool", "flag", "choice", "path", "direct", "direct-flag"],
    )
    def test_generic(self, tmp_path, monkeypatch, module, args, incomplete, expected):
        def run(source: Path, flavor: Literal["plain", "spicy"] = "plain"):
            pytest.fail("completion must not run the command")

        module("new_mini", run)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "event.toml").touch()
        completion = BashComplete(get_command(cli.app), {}, "mini", "_MINI_COMPLETE")
        assert [item.value for item in completion.get_completions(args, incomplete)] == expected

    def test_install(self, tmp_path, monkeypatch, runner):
        import typer.completion

        monkeypatch.setattr(typer.completion, "_get_shell_name", lambda: "zsh")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        rc = tmp_path / ".zshrc"
        rc.write_text("# Existing shell configuration\n")
        shown = runner.invoke(cli.app, ["--show-completion"])
        assert shown.exit_code == 0, shown.output
        assert "external_command:_normal" in shown.output and "_mini_completion" in shown.output
        for _ in range(2):
            installed = runner.invoke(cli.app, ["--install-completion"])
            assert installed.exit_code == 0, installed.output
        assert rc.read_text().startswith("# Existing shell configuration\n")
        assert rc.read_text().count("source ") == 1
        assert (tmp_path / ".zfunc/uq-minis.zsh").read_text() == shown.output

    @pytest.mark.parametrize("name", ["auth", "event", "scrappy", "timey"])
    def test_imports(self, name):
        subprocess.run(
            [
                sys.executable,
                "-c",
                """import sys
from typer.testing import CliRunner
from uq_minis.cli import app
result = CliRunner().invoke(app, ["--tool", sys.argv[1], "--help"])
assert result.exit_code == 0, result.output
assert not {"docx", "httpx", "playwright", "prompt_toolkit", "PIL", "yt_dlp", "googleapiclient"}.intersection(sys.modules)
""",
                name,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @pytest.mark.parametrize(
        "app,args,incomplete,expected",
        [
            (cli.app, [], "", ["add", "rm", "list", "agent", "auth", "event", "scrappy", "timey"]),
            (cli.app, [], "--t", ["--tool"]),
            (cli.app, ["--tool"], "ev", ["event"]),
            (cli.app, ["--tool", "event"], "--l", ["--layout", "--logo"]),
            (cli.app, ["--tool", "event", "--layout"], "f", ["form"]),
            (cli.app, ["--tool=event"], "--layout=f", ["form"]),
            (cli.app, ["--tool", "event"], "--fo", ["--form", "--force", "--form-profile"]),
            (cli.app, ["--tool", "event"], "--pr", ["--preview"]),
            (cli.app, ["--tool", "auth", "--browser"], "ch", ["chromium", "chrome"]),
            (cli.app, ["event"], "--fo", ["--form", "--force", "--form-profile"]),
            (cli.app, ["scrappy"], "li", ["list", "links"]),
            (cli.app, ["agent", "status"], "--j", ["--json"]),
            (cli.app, ["rm"], "ev", ["event"]),
            (cli.app, ["--tool", "event"], "mov", ["movie night.toml"]),
            (cli.app, ["--tool", "event", "--form-profile"], "mov", ["movie night.toml"]),
            (cli.app, ["--tool", "event", "--logo"], "mov", ["movie night.toml"]),
            (cli.app, ["--tool", "auth", "-o"], "mov", ["movie night.toml"]),
            (cli.app, ["--tool", "event", "-o"], "ev", [f"events{os.sep}"]),
            (script.app, [], "li", ["lint"]),
        ],
        ids=[
            "root",
            "tool-flag",
            "tool",
            "layout-flag",
            "layout",
            "inline",
            "form",
            "preview",
            "browser",
            "direct",
            "scrappy",
            "agent",
            "remove",
            "input",
            "profile",
            "logo",
            "credentials",
            "directory",
            "dev",
        ],
    )
    def test_complete(self, paths, app, args, incomplete, expected):
        completion = BashComplete(get_command(app), {}, "mini", "_MINI_COMPLETE")
        assert [item.value for item in completion.get_completions(args, incomplete)] == expected
