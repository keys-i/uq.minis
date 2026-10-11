from __future__ import annotations

from pathlib import Path

import pytest

from uq_minis.core.common import MiniError, discover_events, ensure_outputs


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
