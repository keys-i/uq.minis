import json
from pathlib import Path

import pytest

from uq_minis.core.common import MiniError
from uq_minis.core.paths import migrate


def test_migrate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    files = {
        ".minis/planny/plan.json": "draft",
        ".minis/timey/media/source/upload.mp4": "original",
        ".minis/timey/media/remote/clip.mp4": "download",
        ".minis/app/exports/abc/video.mp4": "export",
    }
    for name, text in files.items():
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    registry = Path(".minis/app/registry.json")
    registry.write_text(
        json.dumps({"a" * 32: str(Path(".minis/app/exports/abc/video.mp4").resolve())})
    )
    migrate()
    migrate()
    assert Path(".config/planny/plan.json").read_text() == "draft"
    assert Path(".config/timey/sources/source/upload.mp4").read_text() == "original"
    assert Path("out/.cache/timey/media/remote/clip.mp4").read_text() == "download"
    assert json.loads(Path(".config/app/registry.json").read_text())["a" * 32] == str(
        Path("out/legacy/abc/video.mp4").resolve()
    )
    for name, text in files.items():
        assert Path(name).read_text() == text


def test_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    legacy = Path(".minis/planny/plan.json")
    legacy.parent.mkdir(parents=True)
    legacy.write_text("saved")
    target = Path(".config/planny/plan.json")
    target.parent.mkdir(parents=True)
    target.write_text("different")
    with pytest.raises(MiniError, match="differs"):
        migrate()
    assert not Path(".config/.migration.json").exists()
    assert target.read_text() == "different"
    target.write_text("saved")
    migrate()
    assert Path(".config/.migration.json").exists()


@pytest.mark.parametrize("destination", [False, True])
def test_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, destination: bool) -> None:
    monkeypatch.chdir(tmp_path)
    private = tmp_path / "private"
    private.write_text("secret")
    source = Path(".minis/planny/plan.json")
    source.parent.mkdir(parents=True)
    source.write_text("draft")
    link = Path(".config/planny/plan.json") if destination else source
    link.parent.mkdir(parents=True, exist_ok=True)
    link.unlink(missing_ok=True)
    link.symlink_to(private)
    with pytest.raises(MiniError, match="link"):
        migrate()
    assert private.read_text() == "secret"
    assert not Path(".config/.migration.json").exists()
