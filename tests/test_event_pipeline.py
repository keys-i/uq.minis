from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from uq_minis.helper.common import MiniError
from uq_minis.minis.event.pipeline import generate


def test_form_only_and_risk_only_outputs(event_toml: Path, tmp_path: Path) -> None:
    form_dir = tmp_path / "form"
    form = generate(event_toml, mode="form", destination=form_dir, form_action="preview")
    assert [path.name for _, path in form.outputs] == ["sample-event.form.json"]
    assert len(json.loads((form_dir / "sample-event.form.json").read_text())["answers"]) > 100
    if os.name == "posix":
        assert (form_dir / "sample-event.form.json").stat().st_mode & 0o077 == 0

    risk_dir = tmp_path / "risk"
    risk = generate(
        event_toml,
        mode="risk",
        risk_layout="both",
        destination=risk_dir,
        jobs=1,
    )
    assert [path.name for _, path in risk.outputs] == [
        "sample-event-pack.docx",
        "sample-event.docx",
    ]
    assert all(path.stat().st_size > 10_000 for _, path in risk.outputs)


def test_noninteractive_generic_mode_requires_selection(event_toml: Path) -> None:
    event_toml.write_text(event_toml.read_text().replace('mode = "both"\n', ""))
    with pytest.raises(MiniError, match=r"Set \[output\]\.mode"):
        generate(event_toml, interactive=False)


def test_invalid_jobs_does_not_write_outputs(event_toml: Path, tmp_path: Path) -> None:
    destination = tmp_path / "invalid"
    with pytest.raises(MiniError, match="--jobs"):
        generate(event_toml, mode="form", destination=destination, jobs=-1)
    assert not destination.exists()


def test_function_calls_do_not_emit_terminal_progress(event_toml, tmp_path, capsys):
    result = generate(
        event_toml, mode="form", form_action="preview", destination=tmp_path / "quiet"
    )
    assert result.outputs
    assert capsys.readouterr().out == ""
