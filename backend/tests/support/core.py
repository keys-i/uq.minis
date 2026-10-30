"""Shared test inputs, isolated state and terminal setup"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from tools.scripts import script
from uq_minis import cli
from uq_minis.core import cache, mini


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    tmp_path = tmp_path / "backend"
    tmp_path.mkdir()
    monkeypatch.setattr(mini, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "src/minis").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "movie night.toml").touch()
    (tmp_path / "events").mkdir()
    return tmp_path


@pytest.fixture
def cached(tmp_path: Path):
    root = tmp_path / "cache"
    source = tmp_path / "payload.bin"
    source.write_bytes(b"completed")
    key = f"{'0' * 16}-{'a' * 16}"
    cache.save(root, key, source, {"file": source.name})
    return root, source, root / key


@pytest.fixture
def module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "cli/__init__.py"))

    def add(name: str, run: Callable[..., object]):
        source = tmp_path / "minis" / name
        source.mkdir(parents=True)
        (source / "__init__.py").touch()
        result = ModuleType(f"uq_minis.minis.{name}")
        result.__dict__["run"] = run
        monkeypatch.setitem(sys.modules, result.__name__, result)
        return result

    return add


@pytest.fixture
def commands(monkeypatch: pytest.MonkeyPatch):
    run = Mock(return_value=0)
    monkeypatch.setattr(script, "run", run)
    return run
