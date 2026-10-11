from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from uq_minis.core import forms
from uq_minis.core.common import MiniError
from uq_minis.minis.event.pipeline import generate


class TestEvent:
    def test_outputs(self, event_toml: Path, tmp_path: Path) -> None:
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

    def test_mode(self, event_toml: Path) -> None:
        event_toml.write_text(event_toml.read_text().replace('mode = "both"\n', ""))
        with pytest.raises(MiniError, match=r"Set \[output\]\.mode"):
            generate(event_toml, interactive=False)

    def test_jobs(self, event_toml: Path, tmp_path: Path) -> None:
        destination = tmp_path / "invalid"
        with pytest.raises(MiniError, match="--jobs"):
            generate(event_toml, mode="form", destination=destination, jobs=-1)
        assert not destination.exists()

    def test_quiet(self, event_toml, tmp_path, capsys):
        result = generate(
            event_toml, mode="form", form_action="preview", destination=tmp_path / "quiet"
        )
        assert result.outputs
        assert capsys.readouterr().out == ""

    def test_parallel(self, event_toml, tmp_path):
        result = generate(
            event_toml, mode="both", risk_layout="both", destination=tmp_path / "pack", jobs=2
        )
        assert [kind for kind, _ in result.outputs] == ["risk-pack", "risk-form", "form"]
        assert all(path.is_file() and path.stat().st_size > 0 for _, path in result.outputs)

    @pytest.mark.parametrize("action", ["preview", "submit", "failed"])
    def test_submit(self, event_toml, tmp_path, monkeypatch, action):
        submit = Mock(
            return_value=201,
            side_effect=MiniError("service unavailable") if action == "failed" else None,
        )
        monkeypatch.setattr(forms, "submit_payload", submit)
        output = tmp_path / "output"
        if action == "failed":
            with pytest.raises(MiniError, match="service unavailable"):
                generate(event_toml, mode="form", destination=output, form_action="submit")
        else:
            result = generate(event_toml, mode="form", destination=output, form_action=action)
            assert result.submissions == (((event_toml, 201),) if action == "submit" else ())
        payload = json.loads((output / "sample-event.form.json").read_text())
        if action == "preview":
            submit.assert_not_called()
        else:
            submit.assert_called_once()
            assert submit.call_args.args[1] == payload
