from __future__ import annotations

import json
import os
import tomllib
from datetime import date, time
from pathlib import Path
from typing import Any, Literal
from unittest.mock import Mock

import pytest

from uq_minis.cli import event
from uq_minis.core import forms
from uq_minis.core.common import MiniError
from uq_minis.core.terminal import Back
from uq_minis.minis.event.pipeline import generate
from uq_minis.minis.event.source import save


class TestEvent:
    @pytest.mark.parametrize("mode", ["risk", "form"])
    @pytest.mark.parametrize("accept", [True, False], ids=["save", "cancel"])
    def test_setup(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        mode: Literal["risk", "form"],
        accept: bool,
    ) -> None:
        path = tmp_path / "nested" / "event.toml"
        answers = iter([
            'UQ "Film" Club',
            "Movie night 🦉",
            "Films, food and friends",
            "Mina",
            "Events Officer",
            "mina@example.com",
            "0400000000",
            "Pizza",
            "",
        ])
        monkeypatch.setattr(event, "ask", Mock(side_effect=answers))
        monkeypatch.setattr(event, "day", Mock(return_value=date(2026, 10, 20)))
        monkeypatch.setattr(
            event,
            "clock",
            Mock(
                side_effect=[
                    time(17, 45),
                    time(18),
                    time(18),
                    time(20),
                    time(20),
                    time(20, 15),
                ]
            ),
        )

        def approve(label: str, **options: Any) -> bool:
            return accept if label == "Save this event source?" else bool(options.get("default"))

        def amount(*args: object, **options: Any) -> float:
            return float(options["default"])

        monkeypatch.setattr(event, "confirm", approve)
        monkeypatch.setattr(event, "number", amount)

        def venue(raw: dict[str, Any], *args: object, **kwargs: object) -> None:
            raw["event"].update(campus="St Lucia", building="Forgan Smith", room="01-101")
            if "form" in raw:
                raw["form"]["values"]["venue_capacity"] = "21-50"

        monkeypatch.setattr("uq_minis.minis.event.rooms.choose", venue)
        if not accept:
            with pytest.raises(Back):
                event._setup(path, mode, None)
            assert not path.exists()
            return
        event._setup(path, mode, None)
        raw = tomllib.loads(path.read_text())
        assert raw["club"]["name"] == 'UQ "Film" Club' and raw["event"]["title"] == "Movie night 🦉"
        assert (
            raw["schedule"]["setup_start"] == "17:45" and raw["event"]["estimated_attendance"] == 20
        )
        assert generate(path, mode=mode).outputs
        before = path.read_bytes()
        with pytest.raises(FileExistsError):
            save(path, raw)
        assert path.read_bytes() == before

    @pytest.mark.parametrize("accept", [True, False], ids=["valid", "invalid"])
    def test_source(self, event_toml: Path, tmp_path: Path, accept: bool) -> None:
        raw = tomllib.loads(event_toml.read_text())
        path = tmp_path / "new" / "event.toml"
        if accept:
            save(path, raw)
            assert tomllib.loads(path.read_text())["event"]["date"] == str(raw["event"]["date"])
            assert generate(path, mode="form").outputs
        else:
            raw["event"]["title"] = ""
            with pytest.raises(ValueError, match="title"):
                save(path, raw)
            assert not path.exists() and not path.parent.exists()

    @pytest.mark.parametrize("accept", [True, False], ids=["make", "back"])
    def test_review(
        self, event_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, accept: bool
    ) -> None:
        confirm = Mock(return_value=accept)
        submit = Mock(return_value=201)
        monkeypatch.setattr(event, "confirm", confirm)
        monkeypatch.setattr(forms, "submit_payload", submit)
        output = tmp_path / "review"
        if accept:
            result = generate(
                event_toml,
                mode="form",
                form_action="submit",
                destination=output,
                review=event._review,
            )
            assert result.outputs and result.submissions and submit.call_count == 1
        else:
            with pytest.raises(Back):
                generate(
                    event_toml,
                    mode="form",
                    form_action="submit",
                    destination=output,
                    review=event._review,
                )
            assert not list(output.glob("*.json"))
            submit.assert_not_called()
        details = confirm.call_args.kwargs["details"]
        assert details["Guests"] == "20" and details["Submission"] == "Send to Microsoft Forms now"
        assert confirm.call_args.kwargs["default"] is False

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

    def test_quiet(
        self, event_toml: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = generate(
            event_toml,
            mode="form",
            form_action="preview",
            destination=tmp_path / "quiet",
        )
        assert result.outputs
        assert capsys.readouterr().out == ""

    def test_parallel(self, event_toml: Path, tmp_path: Path) -> None:
        result = generate(
            event_toml,
            mode="both",
            risk_layout="both",
            destination=tmp_path / "pack",
            jobs=2,
        )
        assert [kind for kind, _ in result.outputs] == [
            "risk-pack",
            "risk-form",
            "form",
        ]
        assert all(path.is_file() and path.stat().st_size > 0 for _, path in result.outputs)

    @pytest.mark.parametrize("action", ["preview", "submit", "failed"])
    def test_submit(
        self,
        event_toml: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        action: Literal["preview", "submit", "failed"],
    ) -> None:
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
