import tomllib
from pathlib import Path

from typer.testing import CliRunner

from uq_minis_tools.scripts import mini, script

RUNNER = CliRunner()


def test_mini_lifecycle_and_path_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(mini, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").touch()
    directory = tmp_path / "src/minis"
    directory.mkdir(parents=True)
    assert RUNNER.invoke(mini.app, ["add", "hello-world"]).exit_code == 0
    source = directory / "hello_world"
    text = (source / "__init__.py").read_text()
    assert "def run()" in text and "import typer" not in text
    assert not (source / "cli.py").exists() and not (source / "__main__.py").exists()
    listed = RUNNER.invoke(mini.app, ["list"])
    assert listed.exit_code == 0 and "hello-world" in listed.output
    for name in ("../outside", "class", "HELLO", "hello-world"):
        assert RUNNER.invoke(mini.app, ["add", name]).exit_code != 0
    assert RUNNER.invoke(mini.app, ["add"]).exit_code != 0
    assert RUNNER.invoke(mini.app, ["rm", "hello-world"]).exit_code == 0
    assert not source.exists()
    assert RUNNER.invoke(mini.app, ["rm", "hello-world"]).exit_code != 0


def test_dev_tasks_fix_check_coverage_and_exit_status(monkeypatch):
    commands = []
    monkeypatch.setattr(script, "run", lambda argv: commands.append(argv) or 0)
    assert RUNNER.invoke(script.app, ["lint"]).exit_code == 0
    assert "--fix" in commands[0] and "format" in commands[1]
    commands.clear()
    assert RUNNER.invoke(script.app, ["check", "-x"]).exit_code == 0
    assert all("--fix" not in command for command in commands)
    assert "--check" in commands[1]
    assert "--cov" in commands[-1] and "-x" in commands[-1]
    commands.clear()
    assert RUNNER.invoke(script.app, ["test", "--cov=uq_minis.cli"]).exit_code == 0
    assert commands[-1][-1] == "--cov=uq_minis.cli"
    assert "Usage:" in RUNNER.invoke(script.app, ["check", "--help"]).output
    monkeypatch.setattr(script, "run", lambda argv: 7)
    assert RUNNER.invoke(script.app, ["check"]).exit_code == 7


def test_project_has_only_requested_entrypoints():
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    assert set(config["project"]["scripts"]) == {"mini", "dev"}
    assert not (root / "src/uq_minis").exists()
