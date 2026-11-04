"""Add, remove and list source minis without importing the runtime

Management edits source packages and their matching CLI, browser and skill
files in an editable checkout. Names are validated before paths are formed
and listing does not import mini implementations
"""

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


def run() -> str:
    """Run the mini"""
    return "{name}"
'''
BROWSER = '''"""Browser workflow for {name}"""

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from uq_minis.app.core import page
from uq_minis.minis.{module} import run

router = APIRouter()


@router.get("/api/minis/{name}")
def home(request: Request) -> dict[str, object]:
    """Describe the mini's browser workflow"""
    return page(request, "{name}", fields=[], submit="Run")


@router.post("/api/minis/{name}")
async def submit(request: Request) -> dict[str, object]:
    """Run the shared mini core outside the browser event loop"""
    return page(request, "{name}", fields=[], result=await run_in_threadpool(run))
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
    browser = ROOT / "src/app" / f"{module}.py"
    skill_name = module.replace("_", "-")
    skill = ROOT.parent / "skills" / skill_name / "SKILL.md"
    if (
        registration.exists()
        or registration.is_symlink()
        or browser.exists()
        or browser.is_symlink()
        or skill.exists()
        or skill.parent.is_symlink()
    ):
        raise typer.BadParameter(f"CLI, browser registration or skill already exists: {name}")
    target.mkdir()
    (target / "__init__.py").write_text(TEMPLATE.format(name=name), encoding="utf-8")
    registration.parent.mkdir(parents=True, exist_ok=True)
    registration.write_text(
        f'"""Register {name} commands with the shared terminal stack"""\n\n'
        "from uq_minis.core.terminal import application\n"
        f"from uq_minis.minis.{module} import run\n\n"
        "app = application()\n\n\n@app.command()\ndef main() -> None:\n"
        '    """Run the mini in the terminal"""\n    print(run())\n',
        encoding="utf-8",
    )
    browser.parent.mkdir(parents=True, exist_ok=True)
    browser.write_text(BROWSER.format(name=skill_name, module=module), encoding="utf-8")
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
    browser = ROOT / "src/app" / f"{module}.py"
    skill = ROOT.parent / "skills" / module.replace("_", "-")
    if registration.is_symlink() or browser.is_symlink() or skill.is_symlink():
        raise typer.BadParameter(
            "CLI registration, browser registration and skill must not be symlinks"
        )
    shutil.rmtree(target)
    if module not in {"core", "completion", "__init__", "__main__"}:
        registration.unlink(missing_ok=True)
        browser.unlink(missing_ok=True)
    if skill.is_dir():
        shutil.rmtree(skill)
    CONSOLE.print(f"rm: {name}", style="success", markup=False)


def list_minis() -> None:
    """List source or installed mini modules"""
    source = ROOT / "src/minis"
    directory = (
        source
        if (ROOT / "pyproject.toml").is_file() and source.is_dir()
        else Path(__file__).resolve().parents[1] / "minis"
    )
    for path in sorted(directory.glob("*/__init__.py")):
        CONSOLE.print(path.parent.name.replace("_", "-"), style="accent", markup=False)
