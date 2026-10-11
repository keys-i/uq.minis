import tomllib
from pathlib import Path

import pytest

from uq_minis import cli
from uq_minis_tools.scripts import script


def test_layout():
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    assert set(config["project"]["scripts"]) == {"mini", "dev"}
    assert not (root / "src/uq_minis").exists()
    assert not list((root / "src/minis").glob("*/cli.py"))


class TestMini:
    @pytest.mark.parametrize("name", ["hello-world", "hello_world"])
    def test_lifecycle(self, checkout, name, runner):
        assert runner.invoke(cli.app, ["add", name]).exit_code == 0
        source = checkout / "src/minis/hello_world"
        text = (source / "__init__.py").read_text()
        assert "def run()" in text and "import typer" not in text
        assert not (source / "cli.py").exists() and not (source / "__main__.py").exists()
        registration = checkout / "src/cli/hello_world.py"
        skill = checkout / "skills/hello-world/SKILL.md"
        assert "application()" in registration.read_text()
        assert "name: hello-world" in skill.read_text()
        listed = runner.invoke(cli.app, ["list"])
        assert listed.exit_code == 0 and "hello-world" in listed.output
        assert runner.invoke(cli.app, ["add", name]).exit_code == 2
        assert runner.invoke(cli.app, ["rm", name]).exit_code == 0
        assert not source.exists()
        assert not registration.exists() and not skill.parent.exists()
        assert runner.invoke(cli.app, ["rm", "hello-world"]).exit_code != 0

    @pytest.mark.parametrize(
        "args",
        [[], ["../outside"], ["class"], ["HELLO"]],
        ids=["missing", "path", "keyword", "uppercase"],
    )
    def test_names(self, checkout, args, runner):
        assert runner.invoke(cli.app, ["add", *args]).exit_code == 2
        assert not list((checkout / "src/minis").iterdir())


class TestDev:
    @pytest.mark.parametrize("binary", [None, "/tools with spaces/ruff"])
    def test_run(self, monkeypatch, process, binary):
        monkeypatch.setattr(script.shutil, "which", lambda _: binary)
        process.return_value.returncode = 7
        assert script.run(["ruff", "check", "."]) == (7 if binary else 127)
        if binary:
            process.assert_called_once_with([binary, "check", "."], cwd=script.ROOT, check=False)
        else:
            process.assert_not_called()

    @pytest.mark.parametrize("missing", ["pyproject.toml", "src"])
    def test_checkout(self, tmp_path, monkeypatch, commands, runner, missing):
        if missing == "src":
            (tmp_path / "pyproject.toml").touch()
        else:
            (tmp_path / "src").mkdir()
        monkeypatch.setattr(script, "ROOT", tmp_path)
        result = runner.invoke(script.app, ["check"])
        assert result.exit_code == 2 and "requires an editable checkout" in result.output
        commands.assert_not_called()

    @pytest.mark.parametrize("failure", [None, "bandit", "uv", "pip-audit"])
    def test_security(self, commands, runner, failure):
        commands.side_effect = lambda argv: 7 if argv[0] == failure else 0
        result = runner.invoke(script.app, ["security"])
        assert result.exit_code == (7 if failure else 0), result.output
        calls = [call.args[0] for call in commands.call_args_list]
        expected = ["bandit", "uv", "pip-audit"]
        if failure:
            expected = expected[: expected.index(failure) + 1]
        assert [call[0] for call in calls] == expected
        assert calls[0][2:4] == ["--severity-level", "medium"]
        if len(calls) > 1:
            assert "--locked" in calls[1] and "--no-emit-project" in calls[1]
            assert "--no-hashes" not in calls[1]
        if len(calls) > 2:
            assert "--strict" in calls[2] and "--disable-pip" in calls[2]
            assert "--require-hashes" in calls[2]

    @pytest.mark.parametrize(
        "args,expected",
        [
            (["lint"], [(0, "--fix"), (1, "format")]),
            (["check", "-x"], [(1, "--check"), (-1, "--cov"), (-1, "-x")]),
            (["test", "--cov=uq_minis.cli"], [(-1, "--cov=uq_minis.cli")]),
        ],
        ids=["lint", "check", "test"],
    )
    def test_flags(self, commands, args, expected, runner):
        assert runner.invoke(script.app, args).exit_code == 0
        calls = [call.args[0] for call in commands.call_args_list]
        for index, flag in expected:
            assert flag in calls[index]
        assert any("--fix" in command for command in calls) == (args[0] == "lint")

    @pytest.mark.parametrize("task", ["lint", "check", "test"])
    def test_failure(self, commands, task, runner):
        assert "Usage:" in runner.invoke(script.app, [task, "--help"]).output
        commands.assert_not_called()
        commands.return_value = 7
        assert runner.invoke(script.app, [task]).exit_code == 7
        commands.assert_called_once()
