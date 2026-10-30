from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from uq_minis.core.common import MiniError, atomic_json, discover_events, ensure_outputs, unique


@pytest.mark.parametrize(
    "package",
    [
        "uq_minis.core",
        "uq_minis.minis.timey",
        "uq_minis.minis.event",
        "uq_minis.minis.scrappy",
        "uq_minis.minis.agent",
    ],
)
def test_exports(package: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""import importlib, sys
module = importlib.import_module({package!r})
assert 'uq_minis.core.terminal' not in sys.modules
assert 'uq_minis.minis.timey.video' not in sys.modules
assert 'httpx' not in sys.modules
assert 'docx' not in sys.modules
for name in module.__all__:
    assert getattr(module, name) is not None, name
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_version() -> None:
    from importlib.metadata import version

    import uq_minis

    assert uq_minis.__version__ == version("uq-minis")
    with pytest.raises(AttributeError):
        getattr(uq_minis, "missing")


class TestFiles:
    def test_json_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "private.json"
        target.write_text("original")
        with pytest.raises(TypeError):
            atomic_json(target, {"secret": "keep private", "invalid": object()}, private=True)
        assert target.read_text() == "original"
        assert list(tmp_path.iterdir()) == [target]

    def test_names(self, tmp_path: Path) -> None:
        output = tmp_path / "timer.mp4"
        assert unique(output) == output
        for path in (output, tmp_path / "timer-1.mp4"):
            path.write_text("keep")
        broken = tmp_path / "timer-2.mp4"
        broken.symlink_to(tmp_path / "missing")
        assert unique(output) == tmp_path / "timer-3.mp4"
        assert output.read_text() == "keep"
        for invalid in (broken, tmp_path):
            with pytest.raises(MiniError, match="not a regular file"):
                unique(invalid)

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
