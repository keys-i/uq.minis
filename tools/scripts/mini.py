"""Add, remove and list source minis without importing the runtime"""

from __future__ import annotations

import keyword
import re
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console

ROOT = Path(__file__).resolve().parents[2]
CONSOLE = Console()
app = typer.Typer(
    rich_markup_mode="rich", pretty_exceptions_show_locals=False, add_completion=False
)
TEMPLATE = '''"""{name} mini."""


def run() -> None:
    """Run the mini."""
    print("{name}")
'''


def _directory() -> Path:
    """Find the mini source directory in an editable checkout"""
    directory = ROOT / "src/minis"
    if not (ROOT / "pyproject.toml").is_file() or not directory.is_dir():
        raise typer.BadParameter("mini requires an editable checkout; run uv sync in the project")
    return directory


def _name(name: str | None) -> tuple[str, str]:
    """Validate a mini name and return its importable module name"""
    if name is None and sys.stdin.isatty():
        name = typer.prompt("Mini name")
    if not name or not re.fullmatch(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*", name):
        raise typer.BadParameter(
            "name must contain lowercase letters, digits, hyphens or underscores"
        )
    module = name.replace("-", "_")
    if keyword.iskeyword(module):
        raise typer.BadParameter("name must not be a Python keyword")
    return name, module


@app.command()
def add(name: str | None = typer.Argument(None)) -> None:
    """Create a mini module"""
    name, module = _name(name)
    target = _directory() / module
    if target.is_symlink():
        raise typer.BadParameter("mini directory must not be a symlink")
    if target.exists():
        raise typer.BadParameter(f"mini already exists: {name}")
    target.mkdir()
    (target / "__init__.py").write_text(TEMPLATE.format(name=name), encoding="utf-8")
    CONSOLE.print(f"add: {name}", style="green", markup=False)


def complete_mini(incomplete: str) -> list[str]:
    """Complete names of existing source minis"""
    return [
        path.parent.name.replace("_", "-")
        for path in sorted(_directory().glob("*/__init__.py"))
        if path.parent.name.replace("_", "-").startswith(incomplete)
    ]


@app.command("rm")
def remove(name: str = typer.Argument(autocompletion=complete_mini)) -> None:
    """Remove a mini module"""
    name, module = _name(name)
    target = _directory() / module
    if target.is_symlink():
        raise typer.BadParameter("mini directory must not be a symlink")
    if not (target / "__init__.py").is_file():
        raise typer.BadParameter(f"mini does not exist: {name}")
    shutil.rmtree(target)
    CONSOLE.print(f"rm: {name}", style="green", markup=False)


@app.command("list")
def list_minis() -> None:
    """List mini modules"""
    for path in sorted(_directory().glob("*/__init__.py")):
        CONSOLE.print(path.parent.name.replace("_", "-"), style="cyan", markup=False)


def main(argv: list[str] | None = None) -> None:
    """Run the mini management CLI"""
    app(args=argv, prog_name="mini")


if __name__ == "__main__":
    main()
