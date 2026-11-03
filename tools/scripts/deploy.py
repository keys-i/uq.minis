"""Publish a checked browser release through the owner's existing Oracle SSH key

Only built frontend files, the Python wheel and locked runtime dependencies
leave this checkout. Credentials and saved workspace state remain on their own machines
The server must already have uv, FFmpeg and Playwright's OS libraries
"""

from __future__ import annotations

import os
import re
import subprocess
import tarfile
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import typer


def target(host: str) -> str:
    """Accept an explicit SSH destination without SSH options or shell syntax"""
    if not re.fullmatch(
        r"[a-z_][a-z0-9_-]*@(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host
    ) or any(
        not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
        for label in host.split("@", 1)[-1].split(".")
    ):
        raise typer.BadParameter("Use an explicit destination such as ubuntu@203.0.113.10")
    return host


def ssh_key() -> Path:
    """Return the explicit deployment key or the Minis default"""
    return Path(os.environ.get("MINIS_SSH_KEY", "~/.ssh/minis")).expanduser()


def bundle(root: Path, output: Path) -> None:
    """Archive an allowlist of build outputs, rejecting links before upload"""
    wheels = list((output / "wheel").glob("*.whl"))
    if len(wheels) != 1:
        raise typer.BadParameter("Build exactly one backend wheel before deploying")
    entries = {
        wheels[0]: wheels[0].name,
        output / "requirements.txt": "requirements.txt",
        root / "deploy/install.sh": "install.sh",
        root / "deploy/Caddyfile": "Caddyfile",
        root / "deploy/caddy.service": "caddy.service",
        root / "deploy/cloudflared.yml": "cloudflared.yml",
        root / "deploy/minis.service": "minis.service",
        root / "deploy/minis.socket": "minis.socket",
        root / "deploy/minis.tmpfiles": "minis.tmpfiles",
        root / "deploy/minis@.socket": "minis@.socket",
        root / "deploy/minis@.service": "minis@.service",
        root / "deploy/minis.rules": "minis.rules",
        root / "deploy/tunnel.service": "tunnel.service",
    }
    entries.update({
        path: "mtls/" + path.relative_to(root / "deploy/mtls").as_posix()
        for path in (root / "deploy/mtls").rglob("*")
    })
    frontend = output / "frontend"
    if not (frontend / "index.html").is_file():
        raise typer.BadParameter("Build the frontend before deploying")
    entries.update({
        path: "frontend/" + path.relative_to(frontend).as_posix() for path in frontend.rglob("*")
    })
    with tarfile.open(output / "release.tar.gz", "w:gz") as archive:
        for path, name in entries.items():
            if any(parent.is_symlink() for parent in (path, *path.parents)):
                raise typer.BadParameter(f"Deploy a real build file instead of a link: {path}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise typer.BadParameter(f"The release is missing a build file: {path}")
            archive.add(path, arcname=name, recursive=False)


def publish(root: Path, host: str) -> None:
    """Build and transfer a release, activating it only after a complete upload

    Args:
        root: Repository root containing backend, frontend and deploy directories
        host: Validated user@host destination whose host key is already verified

    Raises:
        BadParameter: The destination, key or build outputs aren't usable
        CalledProcessError: A build, transfer, installation or health check fails
    """
    host = target(host)
    key = ssh_key()
    if not key.is_file() or key.stat().st_mode & 0o077:
        raise typer.BadParameter(f"Use {key} with private permissions or set MINIS_SSH_KEY")
    options = [
        "-F",
        "/dev/null",
        "-i",
        str(key),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
    ]
    cache = root / "out/.cache"
    cache.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="deploy-", dir=cache) as scratch:
        output = Path(scratch)
        subprocess.run(
            ["uv", "build", "--wheel", "--no-sources", "--out-dir", str(output / "wheel")],
            cwd=root / "backend",
            check=True,
        )
        subprocess.run(
            [
                "uv",
                "export",
                "--locked",
                "--all-extras",
                "--no-default-groups",
                "--no-emit-project",
                "--output-file",
                str(output / "requirements.txt"),
            ],
            cwd=root / "backend",
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "npm",
                "run",
                "build",
                "--",
                "--base=/mini/",
                "--outDir",
                str(output / "frontend"),
            ],
            cwd=root / "frontend",
            check=True,
        )
        bundle(root, output)
        remote = subprocess.run(
            ["ssh", *options, host, "mktemp -d /tmp/minis.XXXXXXXXXX"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        # mktemp creates the private directory; this only validates its returned name
        if not re.fullmatch(r"/tmp/minis\.[A-Za-z0-9]{10}", remote):  # nosec B108
            raise typer.BadParameter("The server didn't return a private deployment directory")
        try:
            subprocess.run(
                ["scp", *options, str(output / "release.tar.gz"), f"{host}:{remote}/"], check=True
            )
            release = uuid4().hex
            subprocess.run(
                [
                    "ssh",
                    *options,
                    host,
                    f"tar -xzf {remote}/release.tar.gz -C {remote} && "
                    f"sudo sh {remote}/install.sh {remote} {release}",
                ],
                check=True,
            )
        finally:
            cleanup = subprocess.run(["ssh", *options, host, f"rm -rf -- {remote}"], check=False)
            if cleanup.returncode:
                warnings.warn(
                    f"Deployment staging files still need removal on {host}: {remote}", stacklevel=2
                )
