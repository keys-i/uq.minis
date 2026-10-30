"""Start repository tooling without bundling development scripts in releases"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    """Locate the checkout and dispatch its development command

    Args:
        argv: Optional command arguments, otherwise the current command line

    Raises:
        SystemExit: No editable checkout is available from the current directory
    """
    root = next(
        (
            path
            for path in (Path.cwd(), *Path.cwd().parents)
            if (path / "tools/scripts/script.py").is_file()
            and (path / "backend/pyproject.toml").is_file()
        ),
        None,
    )
    if root is None:
        raise SystemExit("dev requires an editable checkout; run it from the repository")
    sys.path.insert(0, str(root))
    from tools.scripts.script import main as run

    run(argv)
