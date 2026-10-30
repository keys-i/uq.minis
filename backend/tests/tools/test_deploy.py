import os
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest
import typer
from typer.testing import CliRunner

from tests import ROOT
from tools.scripts import deploy, script


@pytest.mark.parametrize(
    "host",
    [
        "-oProxyCommand=x",
        "ubuntu@host;id",
        "ubuntu@host/path",
        "ubuntu@a..b",
        "ubuntu@-host",
        "ubuntu@host\n",
    ],
)
def test_target(host: str) -> None:
    with pytest.raises(typer.BadParameter):
        deploy.target(host)
    assert deploy.target("ubuntu@203.0.113.10") == "ubuntu@203.0.113.10"


def test_bundle(tmp_path: Path) -> None:
    build = tmp_path / "build"
    files = {
        "build/wheel/minis.whl": "wheel",
        "build/requirements.txt": "locked",
        "build/frontend/index.html": "app",
        "build/frontend/assets/app.js": "script",
        "deploy/install.sh": "installer",
        "deploy/minis.service": "unit",
        "deploy/minis@.service": "tenant",
        "deploy/minis@.socket": "socket",
        "deploy/minis.rules": "policy",
        ".minis/auth/.env": "never upload",
        "frontend/.env": "never upload",
    }
    for name, data in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
    deploy.bundle(tmp_path, build)
    with tarfile.open(build / "release.tar.gz") as archive:
        assert set(archive.getnames()) == {
            "minis.whl",
            "requirements.txt",
            "install.sh",
            "minis.service",
            "minis@.service",
            "minis@.socket",
            "minis.rules",
            "frontend/index.html",
            "frontend/assets/app.js",
        }
        assert all(item.isfile() for item in archive.getmembers())
    (build / "frontend/leak").symlink_to(tmp_path / ".minis/auth/.env")
    with pytest.raises(typer.BadParameter, match="instead of a link"):
        deploy.bundle(tmp_path, build)


def test_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    process = Mock(side_effect=AssertionError("A dry run must not build or contact a host"))
    monkeypatch.setattr(subprocess, "run", process)
    result = CliRunner().invoke(script.app, ["deploy", "ubuntu@203.0.113.10", "--dry-run"])
    assert result.exit_code == 0 and "~/.ssh/oracle" in result.output
    process.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="The server installer targets Linux")
@pytest.mark.parametrize("healthy,delay", [(True, 0), (True, 7), (False, 0)])
def test_activation(tmp_path: Path, healthy: bool, delay: int) -> None:
    stage = tmp_path / "stage.1234567890"
    frontend = stage / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("new app")
    (stage / "minis.service").write_text("new unit")
    for name in ("minis@.service", "minis@.socket", "minis.rules"):
        (stage / name).write_text("new template")
    (stage / "requirements.txt").write_text("")
    (stage / "minis.whl").touch()
    state, root, units, binaries = (tmp_path / name for name in ("state", "opt", "units", "bin"))
    for path in (state, root, units, binaries):
        path.mkdir()
    (state / "private").write_text("preserve this")
    previous = root / "old"
    previous.mkdir()
    (root / "current").symlink_to(previous, target_is_directory=True)
    (units / "minis.service").write_text("old unit")
    checks = shlex.quote(str(tmp_path / "checks"))
    commands = {
        "id": "printf 0",
        "getent": "exit 0",
        "chown": "exit 0",
        "flock": "exit 0",
        "ffmpeg": "exit 0",
        "sleep": "exit 0",
        "systemctl": "exit 0",
        "curl": f"""attempts=0
[ ! -f {checks} ] || read -r attempts < {checks}
attempts=$((attempts + 1))
printf '%s\\n' "$attempts" > {checks}
[ "$attempts" -gt {delay} ] && exit {0 if healthy else 1}
exit 1""",
        "uv": 'if [ "$1" = venv ]; then for dest; do :; done; mkdir -p "$dest/bin"; printf "#!/bin/sh\\nexit 0\\n" > "$dest/bin/playwright"; chmod +x "$dest/bin/playwright"; fi',
    }
    for name, body in commands.items():
        path = binaries / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)
    move = binaries / "mv"
    move.write_text(f"#!{sys.executable}\nimport os, sys\nos.replace(sys.argv[-2], sys.argv[-1])\n")
    move.chmod(0o755)
    source = (ROOT / "deploy/install.sh").read_text()
    for old, new in (
        ("/opt/minis", root),
        ("/var/lib/minis", state),
        ("/etc/systemd/system", units),
        ("/etc/polkit-1/rules.d", units),
        ("/tmp/minis.", tmp_path / "stage."),
    ):
        source = source.replace(old, str(new))
    installer = tmp_path / "install.sh"
    installer.write_text(source)
    revision = "a" * 32
    result = subprocess.run(
        ["sh", str(installer), str(stage), revision],
        env={**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if healthy else 1), result.stderr
    assert (state / "private").read_text() == "preserve this"
    assert (root / "current").resolve() == (root / "releases" / revision if healthy else previous)
    assert (units / "minis.service").read_text() == ("new unit" if healthy else "old unit")
