"""Register shared fixture groups without hiding feature-specific setup"""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Keep default mini paths away from real checkout drafts and credentials"""
    monkeypatch.chdir(tmp_path)


pytest_plugins = [
    "tests.support.core",
    "tests.support.event",
    "tests.support.media",
    "tests.support.study",
    "tests.support.terminal",
    "tests.support.worker",
]
