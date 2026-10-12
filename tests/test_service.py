from __future__ import annotations

import os
import plistlib
import subprocess

import pytest

from uq_minis.core.common import MiniError
from uq_minis.worker import service

pytestmark = pytest.mark.usefixtures("macos")


class TestService:
    def test_notify(self, process):
        service.notify('Title " ;', '$(whoami) \\ "')
        assert process.call_args.args[0] == [
            "/usr/bin/osascript",
            "-e",
            service._OSA_SCRIPT,
            "--",
            'Title " ;',
            '$(whoami) \\ "',
        ]
        process.assert_called_once()

    def test_install(self, tmp_path, monkeypatch, job, process):
        state_dir = tmp_path / "state with spaces"
        monkeypatch.setattr(service.sys, "executable", "/python with spaces/bin/python")
        path = service.install(state_dir, interval=2)
        assert path == job
        data = plistlib.loads(path.read_bytes())
        resolved_state = str(state_dir.resolve())
        assert data["ProgramArguments"] == [
            "/python with spaces/bin/python",
            "-m",
            "uq_minis.cli",
            "--tool",
            "agent",
            "poll",
            "--state-dir",
            resolved_state,
        ]
        assert data["StartInterval"] == 30
        assert data["WorkingDirectory"] == resolved_state
        assert data["StandardOutPath"] == str(state_dir.resolve() / "agent.stdout.log")
        assert data["Umask"] == 0o077
        if os.name == "posix":
            assert state_dir.stat().st_mode & 0o777 == 0o700
        assert [(call.args[0], call.kwargs["check"]) for call in process.call_args_list] == [
            (["/bin/launchctl", "bootout", "gui/501", str(path)], False),
            (["/bin/launchctl", "bootstrap", "gui/501", str(path)], True),
        ]

    @pytest.mark.parametrize(
        "operation,args",
        [(service.install, ("state",)), (service.uninstall, ())],
        ids=["install", "uninstall"],
    )
    def test_foreign(self, tmp_path, job, process, operation, args):
        original = plistlib.dumps({"Label": "com.example.other"})
        job.write_bytes(original)
        with pytest.raises(MiniError, match="unrelated"):
            operation(*(tmp_path / name for name in args))
        assert job.read_bytes() == original
        process.assert_not_called()

    def test_failure(self, tmp_path, job, process):
        process.side_effect = [
            subprocess.CompletedProcess([], 0),
            subprocess.CalledProcessError(1, ["launchctl", "bootstrap"], "", "launch failed"),
        ]
        with pytest.raises(MiniError, match="launch failed"):
            service.install(tmp_path / "state")

    def test_uninstall(self, tmp_path, job, process):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "seen.sqlite3").write_text("state")
        job.write_bytes(
            plistlib.dumps({
                "Label": "au.edu.uq.minis.agent",
                "ProgramArguments": ["python", "-m", "uq_minis.cli", "--tool", "agent", "poll"],
            })
        )
        service.uninstall()
        assert not job.exists()
        assert (state_dir / "seen.sqlite3").read_text() == "state"

    def test_symlink(self, tmp_path, job, process):
        target = tmp_path / "other.plist"
        target.write_text("do not touch")
        job.symlink_to(target)

        with pytest.raises(MiniError, match="symlinked"):
            service.install(tmp_path / "state")
        assert target.read_text() == "do not touch"
        process.assert_not_called()
