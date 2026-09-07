"""Private credential-file handling."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile

from dotenv import set_key

from uq_minis.helper.common import MiniError


def write_env(path: Path, values: Mapping[str, str], *, force: bool) -> None:
    """Save credentials atomically and reject accidental overwrites."""
    if path.is_symlink():
        raise MiniError("Credential output must not be a symlink")
    if path.exists() and not force:
        raise MiniError(f"Refusing to overwrite {path}; pass --force")
    if any(
        not value or any(ord(char) < 32 or ord(char) == 127 for char in value)
        for value in values.values()
    ):
        raise MiniError("Credential values must be nonempty and contain no control characters")
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        if path.exists():
            temporary.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        for name, value in values.items():
            set_key(str(temporary), name, value, quote_mode="always")
        temporary.chmod(0o600)
        if force:
            temporary.replace(path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
