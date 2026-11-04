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
        "deploy/Caddyfile": "router",
        "deploy/caddy.service": "router unit",
        "deploy/cloudflared.yml": "tunnel config",
        "deploy/minis.service": "unit",
        "deploy/minis.socket": "gateway socket",
        "deploy/minis.tmpfiles": "runtime directory",
        "deploy/minis@.service": "tenant",
        "deploy/minis@.socket": "socket",
        "deploy/minis.rules": "policy",
        "deploy/tunnel.service": "tunnel unit",
        "deploy/mtls/remote.caddy": "optional remote profile",
        "deploy/mtls/rotate.sh": "rotation",
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
            "Caddyfile",
            "caddy.service",
            "cloudflared.yml",
            "minis.service",
            "minis.socket",
            "minis.tmpfiles",
            "minis@.service",
            "minis@.socket",
            "minis.rules",
            "tunnel.service",
            "mtls/remote.caddy",
            "mtls/rotate.sh",
            "frontend/index.html",
            "frontend/assets/app.js",
        }
        assert all(item.isfile() for item in archive.getmembers())
    (build / "frontend/leak").symlink_to(tmp_path / ".minis/auth/.env")
    with pytest.raises(typer.BadParameter, match="instead of a link"):
        deploy.bundle(tmp_path, build)


def test_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    process = Mock(side_effect=AssertionError("A dry run must not build or contact a host"))
    monkeypatch.setattr(subprocess, "run", process)
    key = tmp_path / "deploy-key"
    monkeypatch.setenv("MINIS_SSH_KEY", str(key))
    result = CliRunner().invoke(script.app, ["deploy", "ubuntu@203.0.113.10", "--dry-run"])
    assert result.exit_code == 0 and "deploy-key" in result.output
    assert deploy.ssh_key() == key
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
    for name in (
        "minis.socket",
        "minis.tmpfiles",
        "caddy.service",
        "tunnel.service",
        "Caddyfile",
        "cloudflared.yml",
    ):
        (stage / name).write_text(f"new {name}")
    (stage / "mtls").mkdir()
    (stage / "mtls/README.md").write_text("disabled profile")
    (stage / "mtls/rotate.sh").write_text("#!/bin/sh\n")
    (stage / "requirements.txt").write_text("")
    (stage / "minis.whl").touch()
    state, root, units, binaries, configs, share = (
        tmp_path / name for name in ("state", "opt", "units", "bin", "configs", "share")
    )
    for path in (state, root, units, binaries, configs, share):
        path.mkdir()
    for name in ("caddy", "cloudflared", "minis", "tmpfiles"):
        (configs / name).mkdir()
    oauth = configs / "minis/google-oauth.json"
    oauth.write_text("{}")
    oauth.chmod(0o600)
    (state / "private").write_text("preserve this")
    previous = root / "old"
    previous.mkdir()
    (root / "current").symlink_to(previous, target_is_directory=True)
    (units / "minis.service").write_text("old unit")
    (units / "caddy.service").write_text("old caddy unit")
    (configs / "caddy/Caddyfile").write_text("old router")
    checks = shlex.quote(str(tmp_path / "checks"))
    commands = {
        "id": "printf 0",
        "getent": "exit 0",
        "chown": "exit 0",
        "flock": "exit 0",
        "ffmpeg": "exit 0",
        "caddy": "exit 0",
        "cloudflared": "exit 0",
        "systemd-tmpfiles": "exit 0",
        "usermod": "exit 0",
        "sleep": "exit 0",
        "stat": "printf 600",
        "systemctl": '[ "$1" = is-active ] && [ "$3" = soc-minis.service ] && exit 3\nexit 0',
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
        ("/var/lib/caddy", configs / "caddy-state"),
        ("/etc/systemd/system", units),
        ("/etc/polkit-1/rules.d", units),
        ("/etc/caddy", configs / "caddy"),
        ("/etc/cloudflared", configs / "cloudflared"),
        ("/etc/minis", configs / "minis"),
        ("/etc/tmpfiles.d", configs / "tmpfiles"),
        ("/usr/local/share/minis", share),
        ("/tmp/minis.", tmp_path / "stage."),
    ):
        source = source.replace(old, str(new))
        source = source.replace("install -d -o caddy -g minis-edge -m 700", "install -d -m 700")
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
    assert (configs / "caddy/Caddyfile").read_text() == (
        "new Caddyfile" if healthy else "old router"
    )
    if healthy:
        assert (units / "minis.socket").read_text() == "new minis.socket"
        assert (root / "releases" / revision / "mtls/README.md").is_file()
        assert os.access(root / "releases" / revision / "mtls/rotate.sh", os.X_OK)


def test_private_router_contracts() -> None:
    caddy = (ROOT / "deploy/Caddyfile").read_text()
    cloudflared = (ROOT / "deploy/cloudflared.yml").read_text()
    tunnel = (ROOT / "deploy/tunnel.service").read_text()
    gateway = (ROOT / "deploy/minis.socket").read_text()
    assert "bind unix//run/minis-edge/caddy.sock|0660" in caddy
    assert "reverse_proxy unix//run/minis-edge/uq.sock" in caddy
    assert "reverse_proxy unix//run/soc-minis/app.sock" in caddy
    assert "@soc path /soc /soc/*" in caddy
    assert "@uq path /api /api/* /download /download/* /calendar.ics" in caddy
    assert "handle_path /mini/*" in caddy
    assert 'respond "Not found" 404' in caddy
    assert "127.0.0.1:8765" not in caddy
    assert "service: unix:/run/minis-edge/caddy.sock" in cloudflared
    assert "LoadCredential=credentials:/etc/cloudflared/minis.json" in tunnel
    assert "--credentials-file ${CREDENTIALS_DIRECTORY}/credentials" in tunnel
    assert "${MINIS_TUNNEL_ID}" in tunnel
    assert "token-file" not in tunnel
    assert "ListenStream=/run/minis-edge/uq.sock" in gateway
    assert "SocketMode=0660" in gateway and "SocketGroup=minis-edge" in gateway
    assert (
        "LoadCredential=google-oauth:/etc/minis/google-oauth.json"
        in (ROOT / "deploy/minis@.service").read_text()
    )
    installer = (ROOT / "deploy/install.sh").read_text()
    assert "--unix-socket /run/soc-minis/app.sock" in installer
    assert "http://localhost/soc/api/health/ready" in installer


def test_origin_security_and_service_hardening() -> None:
    caddy = (ROOT / "deploy/Caddyfile").read_text()
    assert "style-src-elem 'self'" in caddy
    assert "style-src-attr 'unsafe-inline'" in caddy
    assert "@uq_security path /mini /mini/* /api /api/*" in caddy
    assert "'unsafe-eval'" not in caddy
    assert "frame-ancestors 'none'" in caddy
    assert 'Strict-Transport-Security "max-age=31536000"' in caddy
    assert "includeSubDomains" not in caddy
    assert 'Cross-Origin-Opener-Policy "same-origin-allow-popups"' in caddy
    assert "X-Request-ID {http.request.uuid}" in caddy
    for name in ("caddy.service", "tunnel.service", "minis.service", "minis@.service"):
        unit = (ROOT / "deploy" / name).read_text()
        assert "NoNewPrivileges=yes" in unit
        assert "ProtectSystem=strict" in unit
        assert "ProtectHome=yes" in unit
        assert "CapabilityBoundingSet=" in unit
    assert "RestrictAddressFamilies=AF_UNIX\n" in (ROOT / "deploy/caddy.service").read_text()
    assert "SupplementaryGroups=minis-edge soc-minis" in (ROOT / "deploy/caddy.service").read_text()


def test_remote_mtls_profile_is_inert_and_rotates_before_expiry() -> None:
    main = (ROOT / "deploy/Caddyfile").read_text()
    remote = (ROOT / "deploy/mtls/remote.caddy").read_text()
    rotation = (ROOT / "deploy/mtls/rotate.sh").read_text()
    service = (ROOT / "deploy/mtls/rotate.service").read_text()
    timer = (ROOT / "deploy/mtls/rotate.timer").read_text()
    installer = (ROOT / "deploy/install.sh").read_text()
    assert "remote.caddy" not in main
    assert "require_and_verify" in remote and "root_ca.crt" in remote
    for threshold in ("336h", "168h", "72h"):
        assert f"--expires-in {threshold}" in rotation
    assert "step ca renew" in rotation and "caddy validate" in rotation
    assert "mktemp -d" in rotation and "openssl verify" in rotation
    assert 'mv -Tf "$next" "$current"' in rotation
    assert "/current/server.crt" in remote and "/current/server.key" in remote
    assert "ConditionPathExists=/etc/minis/remote-mtls.enabled" in service
    assert "Persistent=true" in timer and "RandomizedDelaySec=30m" in timer
    assert "enable minis-mtls-rotate" not in installer
