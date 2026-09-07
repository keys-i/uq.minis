"""Run a persistent background task under a shared storage lock"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from uq_minis.helper.common import MiniError


def helper(name: str):
    """Load the two helper files whose filenames contain a dot"""
    if name not in {"db", "mail"}:
        raise ValueError("Unknown worker helper")
    module_name = f"{__name__}._{name}"
    if module_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            module_name, Path(__file__).with_name(f"{name}.helper.py")
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
    return sys.modules[module_name]


def run(task, *, state_dir: Path, storage=None) -> None:
    """Run once, preserve retry deadlines, and notify on a new failure"""
    from .service import notify

    db_helper = helper("db")
    with (storage or db_helper.database)(state_dir) as db:
        retry_at = db_helper.setting(db, "retry_at")
        if retry_at and datetime.fromisoformat(retry_at) > datetime.now(UTC):
            return
        try:
            task(db)
            db_helper.setting(db, "error", "")
        except (MiniError, OSError) as exc:
            if delay := getattr(exc, "retry_after", None):
                db_helper.setting(
                    db, "retry_at", (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
                )
            if db_helper.setting(db, "error") != str(exc):
                notify("UQ worker needs attention", str(exc))
                db_helper.setting(db, "error", str(exc))
            raise
