"""Timey timey behaviour and failure paths"""

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from prompt_toolkit.input import PipeInput
from rich.text import Text
from typer.testing import CliRunner

from tests.fixtures import Screen
from uq_minis import cli
from uq_minis.cli import timey as wizard
from uq_minis.core import terminal
from uq_minis.core.common import MiniError
from uq_minis.minis import timey
from uq_minis.minis.timey import video, youtube


class TestWizard:
    def test_filename(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        tty: SimpleNamespace,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        monkeypatch.setattr(
            wizard, "download", Mock(return_value=(tmp_path / "source.mp4", "Forest"))
        )
        render = Mock()
        monkeypatch.setattr(wizard, "render", render)
        folder = tmp_path / "out/timey"
        folder.mkdir(parents=True)
        for name in ("timey.mp4", "timey-1.mp4"):
            (folder / name).write_text("keep")
        args = [
            "timey",
            "source.mp4",
            "--length",
            "3s",
            "--video-start",
            "0s",
            "--start-gap",
            "0s",
            "--end-gap",
            "0s",
            "--style",
            "minimal",
            "--no-upload",
        ]
        result = runner.invoke(cli.app, args, input="n\n\nmake\n")
        assert result.exit_code == 0, result.output
        assert render.call_args.args[1] == folder / "timey-2.mp4"
        assert (folder / "timey.mp4").read_text() == "keep"
        assert "Finish and create timer" in result.output
        result = runner.invoke(cli.app, [*args, "--no-input", "-o", str(folder / "timey.mp4")])
        assert result.exit_code == 2 and "Refusing to overwrite" in result.output
        assert render.call_count == 1

    @pytest.mark.parametrize("bad", [False, True], ids=["edit", "keep-after-error"])
    def test_review(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        tty: SimpleNamespace,
        bad: bool,
    ) -> None:
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        monkeypatch.setattr(
            wizard, "download", Mock(return_value=(tmp_path / "source.mp4", "Forest"))
        )
        render = Mock()
        monkeypatch.setattr(wizard, "render", render)
        result = runner.invoke(
            cli.app,
            [
                "timey",
                "source.mp4",
                "--length",
                "3s",
                "--video-start",
                "0s",
                "--start-gap",
                "0s",
                "--end-gap",
                "0s",
                "--style",
                "minimal",
                "--no-upload",
                "-o",
                str(tmp_path / "timer.mp4"),
            ],
            input="n\nedit\n" + ("oops\n" if bad else "") + "15s\n1s\n2s\ncentre\n120\nmake\n",
        )
        assert result.exit_code == 0, result.output
        render.assert_called_once()
        timer = render.call_args.args[2]
        assert timer.seconds == 15 and timer.total == 18 and timer.size == 1.2
        assert "00:18" in result.output
        if bad:
            assert "Use seconds" in result.output

    @pytest.mark.parametrize("height", [None, 0, 240])
    def test_quality(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        tty: SimpleNamespace,
        height: int | None,
    ) -> None:
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        choose = Mock(return_value="source.mp4")
        download = Mock(return_value=(tmp_path / "source.mp4", "Forest"))
        render = Mock()
        monkeypatch.setattr(wizard, "_media", choose)
        monkeypatch.setattr(wizard, "download", download)
        monkeypatch.setattr(wizard, "render", render)
        args = [
            "timey",
            "--preview",
            "--length",
            "1s",
            "--start-gap",
            "0s",
            "--end-gap",
            "0s",
            "--style",
            "minimal",
            "-o",
            str(tmp_path / "timer.png"),
        ]
        if height is not None:
            args += ["--height", str(height)]
        result = runner.invoke(cli.app, args, input=("720\n" if height is None else "") + "0s\nn\n")
        assert result.exit_code == 0, result.output
        expected = 720 if height is None else height
        assert (
            choose.call_args.kwargs["height"]
            == download.call_args.kwargs["height"]
            == render.call_args.kwargs["height"]
            == expected
        )

    def test_metadata(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        tty: SimpleNamespace,
    ) -> None:
        context = {
            "video_title": "Unverified Minecraft gameplay title",
            "style": "temple-run",
            "countdown_seconds": 60,
            "start_gap": 5,
            "end_gap": 5,
            "total_seconds": 70,
            "source_start": 80,
            "audio": "muted",
            "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "instructions": "A focus timer for study breaks",
        }
        draft = youtube.metadata(context, tmp_path)
        assert "1 Minute Countdown Timer" in draft["title"]
        assert "00:05" in draft["description"] and "01:05" in draft["description"]
        assert context["source_url"] in draft["description"] and "Minecraft" not in draft["title"]
        assert "Audio: muted" in draft["description"]
        prompts: list[str] = []

        def generate(prompt: str, schema: dict[str, Any], directory: Path, **kwargs: Any):
            prompts.append(prompt)
            assert schema == youtube.METADATA and kwargs["agent"] == "claude"
            assert kwargs["task"] == "Writing your YouTube metadata"
            return {
                **draft,
                "title": "1 Minute Countdown Timer | Temple-Inspired Stone & Gold",
            }

        monkeypatch.setattr(youtube, "generate", generate)
        generated = youtube.metadata(context, tmp_path, agent="claude")
        assert "Stone & Gold" in generated["title"] and "unverified data" in prompts[0]
        assert "AI search" in prompts[0] and "No keyword stuffing" in prompts[0]
        for bad in ({"seconds": "60"}, {"seconds": True}, {"seconds": 0}):
            with pytest.raises(MiniError, match="Metadata"):
                youtube.metadata({**context, "countdown_seconds": bad["seconds"]}, tmp_path)
        monkeypatch.setattr(youtube, "generate", Mock(return_value={**draft, "title": "x" * 101}))
        with pytest.raises(MiniError, match="title"):
            youtube.metadata(context, tmp_path, agent="claude")
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "_metadata", Mock(return_value=generated))
        path = tmp_path / "wizard.youtube.json"

        def read_draft(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return youtube.read_details(path)

        monkeypatch.setattr(wizard, "prepare_upload", Mock(side_effect=read_draft))
        result = runner.invoke(
            cli.app,
            [
                "timey",
                "game.mp4",
                "--upload-only",
                "--details",
                str(path),
                "--metadata",
                "--first-frame",
            ],
            input="Study timer\nEdited timer title\n\ncountdown,study\nunlisted\nn\nn\nn\nn\n",
        )
        # Exercise the draft questions without a real video or Google sign-in
        data = youtube.read_details(path)
        assert data["snippet"]["title"] == "Edited timer title"
        assert data["snippet"]["description"] == generated["description"]
        assert (
            data["thumbnail"] == "first-frame" and data["context"]["instructions"] == "Study timer"
        )
        assert result.exit_code == 0 and "Upload skipped" in result.output

    def test_tab(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        pipe: PipeInput,
        tab: Callable[[str], None],
        screen: Screen,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "moon timer.mp4").touch()
        styles = tmp_path / ".config/timey/styles"
        styles.mkdir(parents=True)
        (styles / "frosted-orbit.json").touch()
        screen(live=True)
        cases: tuple[tuple[str, dict[str, Any], str], ...] = (
            ("mine", {"suggestions": wizard._styles(), "paths": True}, "minecraft"),
            (
                "frost",
                {"suggestions": wizard._styles(), "paths": True},
                "frosted-orbit",
            ),
            ("cent", {"choices": video.POSITIONS}, "centre"),
            (
                "237",
                {
                    "choices": ["03-237 · 26 seats · Seminar"],
                    "show_choices": False,
                    "search": True,
                },
                "03-237 · 26 seats · Seminar",
            ),
            ("moo", {"paths": True}, "moon timer.mp4"),
        )
        for prefix, options, expected in cases:
            tab(prefix)
            assert terminal.ask("Choose", **options) == expected
        pipe.send_text("An icy moon with carved numbers\n")
        assert (
            terminal.ask("Style", suggestions=wizard._styles(), paths=True)
            == "An icy moon with carved numbers"
        )
        pipe.send_text("https://youtu.be/abcdefghijk\n")
        assert terminal.ask("Music", paths=True) == "https://youtu.be/abcdefghijk"
        pipe.send_text("\n")
        assert terminal.ask("Font", paths=True) == ""
        pipe.send_text("wrong\ncentre\n")
        assert terminal.ask("Position", choices=video.POSITIONS) == "centre"

    @pytest.mark.parametrize(
        "args",
        [
            [],
            ["source.mp4", "--no-input"],
            [
                "source.mp4",
                "--length",
                "1s",
                "--no-input",
                "--upload",
                "--yes",
                "--details",
                "missing.json",
            ],
            ["source.mp4", "--upload-only", "--no-input"],
            [
                "source.mp4",
                "--length",
                "1s",
                "--metadata",
                "--no-upload",
                "--no-input",
                "--details",
                "same.mp4",
                "-o",
                "same.mp4",
            ],
        ],
        ids=[
            "missing-source",
            "missing-length",
            "missing-details",
            "missing-upload-draft",
            "output-collision",
        ],
    )
    def test_guards(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str], runner: CliRunner
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli.app, ["timey", *args])
        assert result.exit_code == 2 and "Traceback" not in result.output

    def test_preview(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        tty: SimpleNamespace,
    ) -> None:
        assert (
            "--start-gap"
            in Text.from_ansi(runner.invoke(cli.app, ["timey", "--help"]).output).plain
        )
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        monkeypatch.setattr(
            wizard,
            "download",
            Mock(return_value=(tmp_path / "source.mp4", "Minecraft")),
        )
        renders: list[tuple[video.Timer, dict[str, Any]]] = []

        def render(source: Path, output: Path, timer: video.Timer, **kwargs: Any):
            renders.append((timer, kwargs))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.touch()

        monkeypatch.setattr(wizard, "render", render)
        launch = Mock()
        monkeypatch.setattr("typer.launch", launch)
        monkeypatch.setattr(
            wizard, "upload", Mock(side_effect=AssertionError("upload was declined"))
        )
        result = runner.invoke(
            cli.app,
            ["timey", "local.mp4", "-o", str(tmp_path / "timer.mp4")],
            input="3s\n0s\n2s\n4s\nauto\nn\nn\npreview\nmake\n",
        )
        assert result.exit_code == 0, result.output
        assert "upload the finished timer" in result.output
        assert len(renders) == 2 and renders[0][1]["sample"] and not renders[0][1]["preview"]
        launch.assert_called_once()
        assert renders[1][0] == timey.Timer(seconds=3, start_gap=2, end_gap=4, style="minecraft")
        assert not list(tmp_path.glob(".timey-*"))

    def test_free_placement(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        monkeypatch.setattr(
            wizard, "download", Mock(return_value=(tmp_path / "source.mp4", "Backdrop"))
        )
        render = Mock()
        monkeypatch.setattr(wizard, "render", render)
        result = runner.invoke(
            cli.app,
            [
                "timey",
                "local.mp4",
                "--length",
                "5s",
                "--style",
                "minimal",
                "--x",
                "0.2",
                "--y",
                "0.8",
                "--overlay-width",
                "0.4",
                "--overlay-height",
                "0.2",
                "--preview",
                "--no-input",
                "-o",
                str(tmp_path / "preview.png"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert render.call_args.args[2].x == 0.2 and render.call_args.args[2].y == 0.8
        assert render.call_args.args[2].width == 0.4 and render.call_args.args[2].height == 0.2
        assert "20% across, 80% down" in result.output

    def test_upload(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        tty: SimpleNamespace,
    ) -> None:
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        monkeypatch.setattr(
            wizard,
            "download",
            Mock(return_value=(tmp_path / "source.mp4", "Minecraft")),
        )

        def render(source: Path, output: Path, timer: video.Timer, **kwargs: Any) -> None:
            output.touch()

        monkeypatch.setattr(wizard, "render", render)
        monkeypatch.setattr(
            wizard, "upload", Mock(side_effect=AssertionError("upload was declined"))
        )
        output, details, description = (
            tmp_path / name for name in ("timer.mp4", "details.json", "description.txt")
        )
        description.write_text("Focus time\nA short timer")
        answers = [
            "n",
            "make",
            "n",
            "",
            f"@{description}",
            "timer,minecraft",
            "unlisted",
            "y",
            "n",
            "youtube",
            "y",
            "gaming",
            "en-AU",
            "creativeCommon",
            "n",
            "y",
            "2099-01-01T18:00:00+10:00",
            "n",
        ]
        result = runner.invoke(
            cli.app,
            [
                "timey",
                "game.mp4",
                "--length",
                "3s",
                "--video-start",
                "0s",
                "--start-gap",
                "0s",
                "--end-gap",
                "0s",
                "--style",
                "auto",
                "--upload",
                "--details",
                str(details),
                "-o",
                str(output),
            ],
            input="\n".join(answers) + "\n",
        )
        assert result.exit_code == 0, result.output
        data = json.loads(details.read_text())
        assert data["snippet"]["title"] == "00:03 minecraft timer"
        assert data["snippet"]["description"] == description.read_text()
        assert data["snippet"]["defaultLanguage"] == "en-AU"
        assert data["status"]["selfDeclaredMadeForKids"] and data["notifySubscribers"]
        assert not data["status"]["embeddable"]
        assert data["status"]["privacyStatus"] == "private"
        assert data["status"]["license"] == "creativeCommon"
        assert output.exists() and "Upload skipped" in result.output

    def test_music(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        runner: CliRunner,
        art: dict[str, Any],
        tty: SimpleNamespace,
        screen: Screen,
    ) -> None:
        console, _ = screen()
        monkeypatch.setattr(wizard, "CONSOLE", console)
        monkeypatch.setattr(wizard, "sys", tty)
        monkeypatch.setattr(wizard, "require_ffmpeg", lambda: None)
        monkeypatch.setattr(wizard, "reference", Mock(return_value=None))
        monkeypatch.setattr(wizard, "choose_designer", str)
        data = art
        downloads: list[tuple[str, dict[str, Any]]] = []
        renders: list[tuple[video.Timer, dict[str, Any]]] = []

        def download(source: str, directory: Path, **kwargs: Any):
            downloads.append((source, kwargs))
            return tmp_path / ("music.m4a" if kwargs.get("audio") else "game.mp4"), "Hollow Knight"

        monkeypatch.setattr(wizard, "download", download)
        monkeypatch.setattr(wizard, "design", Mock(return_value=(data, tmp_path / "custom.json")))
        monkeypatch.setattr(wizard, "resolve_font", Mock(return_value=""))

        def render(source: Path, output: Path, timer: video.Timer, **kwargs: Any) -> None:
            renders.append((timer, kwargs))
            output.touch()

        monkeypatch.setattr(
            wizard,
            "render",
            render,
        )
        result = runner.invoke(
            cli.app,
            [
                "timey",
                "game.mp4",
                "--length",
                "3s",
                "--start-gap",
                "0s",
                "--end-gap",
                "0s",
                "--style",
                "custom",
                "--customise",
                "-o",
                str(tmp_path / "timer.mp4"),
            ],
            input="0s\nHollow Knight mask\ncodex\n\n160\nn\n0.4\nFocus\n\nhttps://fonts.google.com/specimen/Cinzel\ny\nhttps://youtu.be/abcdefghijk\n40\ny\nn\nn\nmake\n",
        )
        assert result.exit_code == 0, result.output
        assert len(downloads) == 2 and downloads[1][1]["audio"]
        assert renders[-1][0].artwork == data
        assert renders[-1][1]["music_volume"] == 0.4 and renders[-1][1]["mix_audio"]
        assert renders[-1][0].size == 1.6 and not renders[-1][0].motion
        assert renders[-1][0].loop_blend == 0.4 and renders[-1][0].position == "centre"
        assert not list(tmp_path.glob(".timey-*"))
