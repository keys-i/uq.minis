"""Repository development tasks; independent of the mini runtime"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import typer

from uq_minis.core.terminal import CONSOLE, application

ROOT = Path(__file__).resolve().parents[2]
FORWARD = {"allow_extra_args": True, "ignore_unknown_options": True}
app = application(add_completion=True, context_settings=FORWARD)


def run(argv: list[str], *, env: dict[str, str] | None = None) -> int:
    """Run a development command from the project root and return its exit status"""
    executable = shutil.which(argv[0])
    if executable is None:
        CONSOLE.print(f"Missing executable: {argv[0]}", style="red", markup=False)
        return 127
    CONSOLE.print(" ".join(argv), style="cyan", markup=False)
    return subprocess.run([executable, *argv[1:]], cwd=ROOT, check=False, env=env).returncode


def _checkout() -> None:
    """Require an editable checkout for development tasks"""
    if not (ROOT / "pyproject.toml").is_file() or not (ROOT / "src").is_dir():
        raise typer.BadParameter("dev requires an editable checkout; run uv sync in the project")


def _types() -> int:
    """Check the current wheel without replacing the interactive environment"""
    directory = ROOT / ".cache/types"
    python = directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return run(
        [
            "uv",
            "run",
            "--locked",
            "--all-extras",
            "--no-editable",
            "--reinstall-package",
            "uq-minis",
            "basedpyright",
            "--pythonpath",
            str(python),
            "--warnings",
        ],
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(directory)},
    )


def _task(task: str, extra: list[str]) -> int:
    """Run the selected checks and stop at the first failed command"""
    _checkout()
    ruff = ["ruff"]
    tests = [
        sys.executable,
        "-m",
        "pytest",
        "--cov",
        "--cov-report=term-missing:skip-covered",
        "--cov-report=xml",
    ]
    if task == "test":
        return run([*tests, *extra])
    if task == "security":
        if status := run([
            "bandit",
            "-q",
            "--severity-level",
            "medium",
            "-c",
            "tools/config/bandit.toml",
            "-r",
            "src",
            "tools",
        ]):
            return status
        with TemporaryDirectory(prefix="uq-minis-audit-") as directory:
            requirements = str(Path(directory) / "requirements.txt")
            return run([
                "uv",
                "export",
                "--locked",
                "--all-groups",
                "--all-extras",
                "--no-emit-project",
                "--no-header",
                "--no-annotate",
                "-q",
                "-o",
                requirements,
            ]) or run([
                "pip-audit",
                "--strict",
                "--require-hashes",
                "--disable-pip",
                "--progress-spinner",
                "off",
                "-r",
                requirements,
                *extra,
            ])
    if task == "check":
        commands = [
            [*ruff, "check", "."],
            [*ruff, "format", "--check", "."],
            [sys.executable, "-m", "compileall", "-q", "src", "tools", "tests"],
        ]
    else:
        check = "--check" in extra
        paths = [arg for arg in extra if arg not in {"--check", "--fix"}] or ["."]
        commands = [
            [*ruff, "check", *([] if check else ["--fix"]), *paths],
            [*ruff, "format", *(["--check"] if check else []), *paths],
        ]
    for command in commands:
        if status := run(command):
            return status
    if task == "check":
        return _types() or run([*tests, *extra])
    return 0


@app.command(context_settings=FORWARD)
def check(context: typer.Context) -> None:
    """Run repository checks"""
    raise typer.Exit(_task("check", context.args))


@app.command(context_settings=FORWARD)
def lint(context: typer.Context) -> None:
    """Format and lint paths"""
    raise typer.Exit(_task("lint", context.args))


@app.command(context_settings=FORWARD)
def security(context: typer.Context) -> None:
    """Run security checks"""
    raise typer.Exit(_task("security", context.args))


@app.command(context_settings=FORWARD)
def test(context: typer.Context) -> None:
    """Run tests with coverage"""
    raise typer.Exit(_task("test", context.args))


def main(argv: list[str] | None = None) -> None:
    """Run the development CLI"""
    app(args=argv, prog_name="dev")


if __name__ == "__main__":
    main()
