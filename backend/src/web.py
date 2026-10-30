"""Start the HTTP service without importing the interactive terminal framework

The CLI shares this startup path while systemd uses the small native entry
Socket activation and delegate credentials retain their existing boundaries
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from uq_minis.core.common import MiniError


def run(port: int = 8765, frontend: Path | None = None) -> None:
    """Start the loopback service using only validated process configuration"""
    if not 1024 <= port <= 65535:
        raise MiniError("Choose a port between 1024 and 65535")
    try:
        import uvicorn

        from uq_minis.app import create
    except ImportError as exc:
        raise MiniError("Install browser support with uv sync --extra browser") from exc
    delegate = None
    if credentials := os.environ.get("CREDENTIALS_DIRECTORY"):
        values = json.loads((Path(credentials) / "identity").read_text())
        from uq_minis.app.gateway import ACCOUNT

        if not ACCOUNT.fullmatch(values["account"]) or len(values["secret"]) != 64:
            raise MiniError("The workspace identity is invalid")
        delegate = (values["account"], values["secret"])
    activated = (
        os.environ.get("LISTEN_PID") == str(os.getpid()) and os.environ.get("LISTEN_FDS") == "1"
    )
    uvicorn.run(
        create(
            port=port,
            frontend=frontend,
            origin=os.environ.get("MINIS_ORIGIN", ""),
            delegate=delegate,
        ),
        host="127.0.0.1",
        port=port,
        access_log=False,
        fd=3 if activated else None,
    )


def main() -> None:
    """Parse the two public server options using the standard library"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--frontend", type=Path)
    arguments = parser.parse_args()
    try:
        run(arguments.port, arguments.frontend)
    except MiniError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
