"""Private SQLite storage and a process lock for background workers"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from uq_minis.helper.common import MiniError


@contextmanager
def database(state_dir: Path):
    """Protect state and serialize commands while allowing durable intermediate commits"""
    state_dir = state_dir.expanduser().absolute()
    if state_dir.is_symlink():
        raise MiniError("The agent state directory must not be a symlink")
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    allowed = re.compile(
        r"(?:agent|lock)\.sqlite3(?:-(?:journal|wal|shm))?|agent\.(?:stdout|stderr)\.log|browser"
    )
    if any(not allowed.fullmatch(path.name) or path.is_symlink() for path in state_dir.iterdir()):
        raise MiniError("Use a dedicated agent state directory with no unrelated files or symlinks")
    if (state_dir / "browser").exists() and not (state_dir / "browser").is_dir():
        raise MiniError("The browser profile must be a directory")
    state_dir.chmod(0o700)
    guard = sqlite3.connect(state_dir / "lock.sqlite3", timeout=0)
    db = None
    try:
        # ponytail: one worker per mailbox; separate state directories if parallel mailboxes are needed.
        guard.execute("BEGIN EXCLUSIVE")
        db = sqlite3.connect(state_dir / "agent.sqlite3", isolation_level=None)
        db.row_factory = sqlite3.Row
        for name in ("lock.sqlite3", "agent.sqlite3"):
            (state_dir / name).chmod(0o600)
        db.execute(
            "CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        yield db
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc):
            raise MiniError("Another agent command is running; try again shortly") from exc
        raise MiniError(f"Cannot access the agent state: {exc}") from exc
    finally:
        if db is not None:
            db.close()
        guard.close()


def setting(db, name: str, value: str | None = None) -> str | None:
    """Read or atomically replace a worker setting"""
    if value is not None:
        db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (name, value))
    row = db.execute("SELECT value FROM settings WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None


def update(db, table: str, key: str, identity: str, **values) -> None:
    """Update internal table/column names with parameterized values"""
    if not all(name.isidentifier() for name in (table, key, *values)):
        raise MiniError("Invalid database identifier")
    columns = ", ".join(f"{name} = ?" for name in values)
    # Identifiers are validated above; all values use placeholders.
    query = f"UPDATE {table} SET {columns} WHERE {key} = ?"
    db.execute(query, (*values.values(), identity))
