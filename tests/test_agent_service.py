from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

import pytest

from uq_minis.helper.common import MiniError
from uq_minis.workers import service


@pytest.fixture(autouse=True)
def macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.platform, "system", lambda: "Darwin")


def test_notify_passes_hostile_text_as_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(service.subprocess, "run", run)

    service.notify('Title " ;', '$(whoami) \\ "')

    assert calls == [
        [
            "/usr/bin/osascript",
            "-e",
            service._OSA_SCRIPT,
            "--",
            'Title " ;',
            '$(whoami) \\ "',
        ]
    ]


def test_install_writes_launchd_job_and_reloads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home with spaces"
    state_dir = tmp_path / "state with spaces"
    monkeypatch.setattr(service.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(service.sys, "executable", "/python with spaces/bin/python")
    monkeypatch.setattr(service.os, "getuid", lambda: 501)
    calls: list[tuple[list[str], bool]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs["check"]))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(service.subprocess, "run", run)

    path = service.install(state_dir, interval=2)

    with path.open("rb") as source:
        job = plistlib.load(source)
    resolved_state = str(state_dir.resolve())
    assert job["ProgramArguments"] == [
        "/python with spaces/bin/python",
        "-m",
        "uq_minis.cli",
        "--tool",
        "agent",
        "poll",
        "--state-dir",
        resolved_state,
    ]
    assert job["StartInterval"] == 30
    assert job["WorkingDirectory"] == resolved_state
    assert job["StandardOutPath"] == str(state_dir.resolve() / "agent.stdout.log")
    assert job["Umask"] == 0o077
    assert state_dir.stat().st_mode & 0o777 == 0o700
    assert calls == [
        (["/bin/launchctl", "bootout", "gui/501", str(path)], False),
        (["/bin/launchctl", "bootstrap", "gui/501", str(path)], True),
    ]


def test_install_rejects_foreign_plist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    path = home / "Library" / "LaunchAgents" / "au.edu.uq.minis.agent.plist"
    path.parent.mkdir(parents=True)
    with path.open("wb") as destination:
        plistlib.dump({"Label": "com.example.other"}, destination)
    monkeypatch.setattr(service.Path, "home", classmethod(lambda cls: home))

    with pytest.raises(MiniError, match="unrelated"):
        service.install(tmp_path / "state")

    with path.open("rb") as source:
        assert plistlib.load(source)["Label"] == "com.example.other"


def test_install_reports_launchctl_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.Path, "home", classmethod(lambda cls: tmp_path / "home"))

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "bootstrap" in command:
            raise subprocess.CalledProcessError(1, command, "", "launch failed")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(service.subprocess, "run", run)

    with pytest.raises(MiniError, match="launch failed"):
        service.install(tmp_path / "state")


def test_uninstall_removes_only_owned_job_and_keeps_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "seen.sqlite3").write_text("state")
    path = home / "Library" / "LaunchAgents" / "au.edu.uq.minis.agent.plist"
    path.parent.mkdir(parents=True)
    with path.open("wb") as destination:
        plistlib.dump(
            {
                "Label": "au.edu.uq.minis.agent",
                "ProgramArguments": [
                    "python",
                    "-m",
                    "uq_minis.cli",
                    "--tool",
                    "agent",
                    "poll",
                ],
            },
            destination,
        )
    monkeypatch.setattr(service.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0),
    )

    service.uninstall()

    assert not path.exists()
    assert (state_dir / "seen.sqlite3").read_text() == "state"


def test_uninstall_rejects_foreign_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    path = home / "Library" / "LaunchAgents" / "au.edu.uq.minis.agent.plist"
    path.parent.mkdir(parents=True)
    with path.open("wb") as destination:
        plistlib.dump({"Label": "com.example.other"}, destination)
    monkeypatch.setattr(service.Path, "home", classmethod(lambda cls: home))

    with pytest.raises(MiniError, match="unrelated"):
        service.uninstall()
    assert path.exists()


def test_install_rejects_symlinked_plist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    path = home / "Library" / "LaunchAgents" / "au.edu.uq.minis.agent.plist"
    target = tmp_path / "other.plist"
    path.parent.mkdir(parents=True)
    target.write_text("do not touch")
    path.symlink_to(target)
    monkeypatch.setattr(service.Path, "home", classmethod(lambda cls: home))

    with pytest.raises(MiniError, match="symlinked"):
        service.install(tmp_path / "state")
    assert target.read_text() == "do not touch"
