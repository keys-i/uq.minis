"""Run the event-mail workflow under its storage lock

Acquire the mailbox state lock before creating its transport and dispatching
one requested worker operation. Transport lifetime and database cleanup
remain tied to that operation rather than an unowned background thread
"""

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
    """Run a mailbox task once using its persistent state database

    Skip work while a stored retry deadline is pending and clear the recorded
    error after success; expected failures retain any supplied retry delay
    Notify only when the error changes, then re-raise it for the caller to handle

    Args:
        task: Operation receiving the worker's open SQLite connection
        state_dir: Private directory for this mailbox's persistent state
        database: Optional connection context, otherwise use shared worker storage

    Raises:
        MiniError: The task or worker state is invalid
        OSError: Persistent state or a required local resource is unavailable
    """
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
