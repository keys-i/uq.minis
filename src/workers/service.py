"""macOS integration for the event-mail agent."""

from __future__ import annotations

import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

from uq_minis.helper.common import MiniError

_LABEL = "au.edu.uq.minis.agent"
_PLIST_NAME = f"{_LABEL}.plist"
_OSA_SCRIPT = """on run argv
	display notification (item 2 of argv) with title (item 1 of argv)
end run"""


def _require_macos() -> None:
    if platform.system() != "Darwin":
        raise MiniError("The event-mail service is available only on macOS")


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / _PLIST_NAME


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        # Fixed executables; mail content is passed as arguments, never as shell or AppleScript source.
        return subprocess.run(command, check=check, text=True, capture_output=True, timeout=15)
    except FileNotFoundError as exc:
        raise MiniError(f"Required macOS command is unavailable: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MiniError(f"macOS command timed out: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or (exc.stdout or "").strip() or "unknown error"
        raise MiniError(f"macOS command failed: {detail}") from exc


def notify(title: str, message: str) -> None:
    """Show a macOS notification without interpreting mail content as script."""
    _require_macos()
    _run(["/usr/bin/osascript", "-e", _OSA_SCRIPT, "--", title, message])


def _owned(data: object) -> bool:
    return (
        isinstance(data, dict)
        and data.get("Label") == _LABEL
        and data.get("ProgramArguments", [])[1:6]
        == ["-m", "uq_minis.cli", "--tool", "agent", "poll"]
    )


def _read_plist(path: Path) -> object:
    try:
        with path.open("rb") as source:
            return plistlib.load(source)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise MiniError(f"Cannot read existing launchd job {path}: {exc}") from exc


def _ensure_owned(path: Path) -> None:
    if path.is_symlink():
        raise MiniError(f"Refusing symlinked launchd job: {path}")
    if path.exists() and not _owned(_read_plist(path)):
        raise MiniError(f"Refusing to replace unrelated launchd job: {path}")


def install(state_dir: Path, interval: int = 60) -> Path:
    """Install the current Python environment as a per-user launchd job."""
    _require_macos()
    if interval < 1:
        raise MiniError("Polling interval must be positive")

    state_dir = state_dir.expanduser().resolve()
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        state_dir.chmod(0o700)
    except OSError as exc:
        raise MiniError(f"Cannot secure agent state directory {state_dir}: {exc}") from exc
    plist_path = _plist_path()
    _ensure_owned(plist_path)
    plist_path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)

    data = {
        "Label": _LABEL,
        "ProgramArguments": [
            sys.executable,
            "-m",
            "uq_minis.cli",
            "--tool",
            "agent",
            "poll",
            "--state-dir",
            str(state_dir),
        ],
        "RunAtLoad": True,
        "StartInterval": max(interval, 30),
        "WorkingDirectory": str(state_dir),
        "StandardOutPath": str(state_dir / "agent.stdout.log"),
        "StandardErrorPath": str(state_dir / "agent.stderr.log"),
        "Umask": 0o077,
    }
    try:
        with plist_path.open("wb") as destination:
            plistlib.dump(data, destination, sort_keys=False)
    except OSError as exc:
        raise MiniError(f"Cannot write launchd job {plist_path}: {exc}") from exc

    domain = f"gui/{os.getuid()}"
    _run(["/bin/launchctl", "bootout", domain, str(plist_path)], check=False)
    _run(["/bin/launchctl", "bootstrap", domain, str(plist_path)])
    return plist_path


def uninstall() -> None:
    """Remove this user's agent job while retaining its state and logs."""
    _require_macos()
    plist_path = _plist_path()
    if not plist_path.exists():
        return
    _ensure_owned(plist_path)
    _run(
        ["/bin/launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)],
        check=False,
    )
    try:
        plist_path.unlink()
    except OSError as exc:
        raise MiniError(f"Cannot remove launchd job {plist_path}: {exc}") from exc
