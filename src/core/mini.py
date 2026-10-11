"""Add, remove and list source minis without importing the runtime"""

from __future__ import annotations

import keyword
import re
import shutil
import sys
from pathlib import Path

import typer

from uq_minis.core.terminal import CONSOLE, ask

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = '''"""{name} mini"""


def run() -> None:
    """Run the mini"""
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
        name = ask("Mini name", required=True)
    if not name or not re.fullmatch(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*", name):
        raise typer.BadParameter(
            "name must contain lowercase letters, digits, hyphens or underscores"
        )
    module = name.replace("-", "_")
    if keyword.iskeyword(module):
        raise typer.BadParameter("name must not be a Python keyword")
    return name, module


def add(name: str | None = typer.Argument(None)) -> None:
    """Create a mini module"""
    name, module = _name(name)
    target = _directory() / module
    if target.is_symlink():
        raise typer.BadParameter("mini directory must not be a symlink")
    if target.exists():
        raise typer.BadParameter(f"mini already exists: {name}")
    registration = ROOT / "src/cli" / f"{module}.py"
    skill_name = module.replace("_", "-")
    skill = ROOT / "skills" / skill_name / "SKILL.md"
    if (
        registration.exists()
        or registration.is_symlink()
        or skill.exists()
        or skill.parent.is_symlink()
    ):
        raise typer.BadParameter(f"CLI registration or skill already exists: {name}")
    target.mkdir()
    (target / "__init__.py").write_text(TEMPLATE.format(name=name), encoding="utf-8")
    registration.parent.mkdir(parents=True, exist_ok=True)
    registration.write_text(
        f'"""Register {name} commands with the shared terminal stack"""\n\n'
        "from uq_minis.core.terminal import application\n"
        f"from uq_minis.minis.{module} import run\n\n"
        "app = application()\napp.command()(run)\n",
        encoding="utf-8",
    )
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        f"---\nname: {skill_name}\ndescription: Describe the task this mini helps complete and when to use it\n---\n\n"
        f"# {skill_name}\n\n"
        "Describe the task inputs, useful decisions, expected deliverables and recovery steps\n"
        f"Use `mini {skill_name} --help` for optional tool support\n",
        encoding="utf-8",
    )
    CONSOLE.print(f"add: {name}", style="success", markup=False)


def complete_mini(incomplete: str) -> list[str]:
    """Complete names of existing source minis"""
    return [
        path.parent.name.replace("_", "-")
        for path in sorted(_directory().glob("*/__init__.py"))
        if path.parent.name.replace("_", "-").startswith(incomplete)
    ]


def remove(name: str = typer.Argument(autocompletion=complete_mini)) -> None:
    """Remove a mini module"""
    name, module = _name(name)
    target = _directory() / module
    if target.is_symlink():
        raise typer.BadParameter("mini directory must not be a symlink")
    if not (target / "__init__.py").is_file():
        raise typer.BadParameter(f"mini does not exist: {name}")
    registration = ROOT / "src/cli" / f"{module}.py"
    skill = ROOT / "skills" / module.replace("_", "-")
    if registration.is_symlink() or skill.is_symlink():
        raise typer.BadParameter("CLI registration and skill must not be symlinks")
    shutil.rmtree(target)
    if module not in {"core", "completion", "__init__", "__main__"}:
        registration.unlink(missing_ok=True)
    if skill.is_dir():
        shutil.rmtree(skill)
    CONSOLE.print(f"rm: {name}", style="success", markup=False)


def list_minis() -> None:
    """List mini modules"""
    for path in sorted(_directory().glob("*/__init__.py")):
        CONSOLE.print(path.parent.name.replace("_", "-"), style="accent", markup=False)
