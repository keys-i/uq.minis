"""Run the event-mail workflow under its storage lock"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from sqlite3 import Connection

from uq_minis.core.common import MiniError

from . import db as storage


def run(
    task: Callable[[Connection], None],
    *,
    state_dir: Path,
    database: Callable[[Path], AbstractContextManager[Connection]] | None = None,
) -> None:
    """Run once, preserve retry deadlines, and notify on a new failure"""
    from .service import notify

    with (database or storage.database)(state_dir) as db:
        retry_at = storage.setting(db, "retry_at")
        if retry_at and datetime.fromisoformat(retry_at) > datetime.now(UTC):
            return
        try:
            task(db)
            storage.setting(db, "error", "")
        except (MiniError, OSError) as exc:
            if delay := getattr(exc, "retry_after", None):
                storage.setting(
                    db,
                    "retry_at",
                    (datetime.now(UTC) + timedelta(seconds=delay)).isoformat(),
                )
            if storage.setting(db, "error") != str(exc):
                notify("UQ worker needs attention", str(exc))
                storage.setting(db, "error", str(exc))
            raise
