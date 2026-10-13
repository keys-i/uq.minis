from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from uq_minis.core.common import MiniError, discover_events, ensure_outputs


@pytest.mark.parametrize("package", ["uq_minis.core", "uq_minis.minis.timey"])
def test_exports(package: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""import importlib, sys
module = importlib.import_module({package!r})
assert 'uq_minis.core.terminal' not in sys.modules
assert 'uq_minis.minis.timey.video' not in sys.modules
for name in module.__all__:
    assert getattr(module, name) is not None, name
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


class TestFiles:
    def test_discovery(self, tmp_path: Path) -> None:
        (tmp_path / "other.toml").write_text("x = 1\n")
        with pytest.raises(MiniError, match="No event.toml"):
            discover_events(tmp_path)

        nested = tmp_path / "nested"
        nested.mkdir()
        event = nested / "movie.event.toml"
        event.write_text("x = 1\n")
        assert discover_events(tmp_path) == [event.resolve()]

    def test_outputs(self, tmp_path: Path) -> None:
        output = tmp_path / "event.docx"
        with pytest.raises(MiniError, match="collision"):
            ensure_outputs([output, output], force=False)
        output.write_text("existing")
        with pytest.raises(MiniError, match="Refusing to overwrite"):
            ensure_outputs([output], force=False)
        ensure_outputs([output], force=True)
