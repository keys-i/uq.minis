"""Timey preview behaviour and failure paths"""

from io import BytesIO
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock

import httpx
import pytest
from PIL import Image
from typer.testing import CliRunner

from tests.fixtures import Canvas, Clip, Keys
from uq_minis.assets import ROOT as ASSETS
from uq_minis.cli import timey as wizard
from uq_minis.core import STATE, terminal
from uq_minis.core.common import MiniError
from uq_minis.minis import timey
from uq_minis.minis.timey import preview, video


class TestPreview:
    def test_face(
        self, canvas: Canvas, keys: Keys, monkeypatch: pytest.MonkeyPatch, fontlist: dict[str, str]
    ) -> None:
        font = str(ASSETS / "timey/fonts/bungee.ttf")
        download = AsyncMock(return_value=font)
        monkeypatch.setattr(wizard, "specimen", download)
        monkeypatch.setattr(wizard, "resolve_font", Mock(return_value=font))
        frames = canvas(140, 34, reply=("Font: Bungee", "\ny\n"))
        keys("Open Sans")
        assert wizard._Studio(timey.Timer()).font("") == font
        download.assert_awaited_once_with(
            "https://fonts.google.com/specimen/Open+Sans", STATE / "timey/fonts"
        )
        assert any("Open Sans" in row for frame in frames for row in frame)
        assert any("Font: Bungee" in row for frame in frames for row in frame)

    @pytest.mark.parametrize(
        "field,answers,expected",
        [
            ("position", "top-left\n", "top-left"),
            ("accent", "#6FE9EF\n", "#6FE9EF"),
            ("accent", "bad\n#FF0000\nn\n#FFD34D\n", "#FFD34D"),
        ],
        ids=["placement", "palette", "review-colour"],
    )
    def test_choices(self, field: str, answers: str, expected: str, runner: CliRunner) -> None:
        app = terminal.application()
        picked: list[str] = []

        @app.command()
        def run():
            studio = wizard._Studio(timey.Timer(x=0.3, y=0.7))
            choices = (
                {value: value for value in video.POSITIONS}
                if field == "position"
                else {"#6FE9EF": "Blue", "#FFD34D": "Yellow"}
            )
            picked.append(studio.choose(field, "Choose", choices, free=field == "accent"))
            assert getattr(studio.timer, field) == picked[-1]
            assert (studio.timer.x, studio.timer.y) == (
                (None, None) if field == "position" else (0.3, 0.7)
            )

        result = runner.invoke(app, [], input=answers)
        assert result.exit_code == 0, result.output
        assert picked == [expected]

    @pytest.mark.parametrize(
        "answer,source",
        [
            ("Cinzel\ny\n", "https://fonts.google.com/specimen/Cinzel"),
            ("Space Mono\nn\nbungee\n", "https://fonts.google.com/specimen/Space+Mono"),
            (
                "https://fonts.google.com/specimen/Cinzel\ny\n",
                "https://fonts.google.com/specimen/Cinzel",
            ),
            ("missing.ttf\nbungee\n", None),
            ("spook\nCreepster\ny\n", "https://fonts.google.com/specimen/Creepster"),
            ("ariel\nArimo\ny\n", "https://fonts.google.com/specimen/Arimo"),
            ("Ciznel\nCinzel\ny\n", "https://fonts.google.com/specimen/Cinzel"),
            ("random nonsense\nback\nbungee\n", None),
            ("open sans\ny\n", "https://fonts.google.com/specimen/Open+Sans"),
            (
                "noto sans devanagari\ny\n",
                "https://fonts.google.com/specimen/Noto+Sans+Devanagari",
            ),
        ],
        ids=[
            "family",
            "reject",
            "link",
            "missing-file",
            "mood",
            "ariel",
            "typo",
            "refine",
            "open-sans",
            "full-list",
        ],
    )
    def test_font_review(
        self,
        answer: str,
        source: None | str,
        runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
        fontlist: dict[str, str],
    ) -> None:
        font = str(ASSETS / "timey/fonts/bungee.ttf")
        resolve: list[str] = []

        def resolve_font(value: str, *args: Any, **kwargs: Any) -> str:
            resolve.append(value)
            return font

        monkeypatch.setattr(
            wizard,
            "resolve_font",
            Mock(side_effect=resolve_font),
        )
        app = terminal.application()

        @app.command()
        def run():
            assert wizard._Studio(timey.Timer()).font("") == font

        result = runner.invoke(app, [], input=answer)
        assert result.exit_code == 0, result.output
        assert resolve == ([source] if source else [])

    def test_font_failure(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch, fontlist: dict[str, str]
    ) -> None:
        requests: list[str] = []

        def fail(value: Any, *args: Any, **kwargs: Any):
            requests.append(value)
            raise MiniError("Google Fonts is offline")

        monkeypatch.setattr(wizard, "resolve_font", fail)
        app = terminal.application()

        @app.command()
        def run():
            studio = wizard._Studio(timey.Timer())
            assert studio.font("") == ""
            assert studio.timer.font == ""

        result = runner.invoke(app, [], input="spook\nCreepster\nrandom words\ntheme\n")
        assert result.exit_code == 0, result.output
        assert "Google Fonts is offline" in result.output
        assert requests == ["https://fonts.google.com/specimen/Creepster"]

    @pytest.mark.parametrize("timer", [None, timey.Timer(start_gap=5)])
    def test_frame(
        self, clip: Clip, timer: video.Timer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        source = clip("opening.mp4", "color=c=navy:s=480x270:r=24", seconds=1)
        result = preview.frame(source, timer)
        assert "▀" in result.picture.plain
        assert not list(tmp_path.glob(".timey-preview-*"))

    @pytest.mark.parametrize("state", ["image", "fallback", "oversized", "broken", "offline"])
    def test_thumbnail(
        self, videos: tuple[Mock, MagicMock], thumbnails: MagicMock, state: str
    ) -> None:
        if state == "fallback":
            type(thumbnails).status_code = PropertyMock(side_effect=[404, 404, 200])
        elif state == "oversized":
            thumbnails.iter_bytes.return_value = [b"x" * (1024 * 1024 + 1)]
        elif state == "broken":
            thumbnails.iter_bytes.return_value = [b"not an image"]
        elif state == "offline":
            thumbnails.raise_for_status.side_effect = httpx.ConnectError("Offline")
        result = preview.thumbnail(video.search("forest")[0])
        assert "01:23" in result.description
        assert ("▀" in result.picture.plain) is (state in {"image", "fallback"})
        if state in {"image", "fallback"}:
            assert len(result.picture.plain.splitlines()[0]) == 40
            assert (
                cast(Mock, httpx.stream)
                .call_args_list[-1]
                .args[1]
                .endswith("hqdefault.jpg" if state == "fallback" else "maxresdefault.jpg")
            )
        else:
            assert "Thumbnail unavailable" in result.picture.plain

    @pytest.mark.parametrize(
        "field,values",
        [
            ("style", list(video.STYLES)),
            ("position", video.POSITIONS),
            ("accent", ["", "#8FDA53", "#6FE9EF"]),
        ],
    )
    def test_samples(self, field: str, values: Any) -> None:
        samples = wizard._Studio(timey.Timer()).samples(field, values)
        assert len({sample.picture.spans.__repr__() for sample in samples.values()}) == len(values)
        assert all(len(sample.picture.plain.splitlines()) <= 14 for sample in samples.values())

    @pytest.mark.parametrize("size", [(40, 16), (73, 26), (128, 48), (256, 90)])
    def test_size(self, size: tuple[int, int]) -> None:
        with BytesIO() as encoded:
            Image.new("RGB", (640, 360), "#e8a37e").save(encoded, format="PNG")
            sample = preview.picture(encoded.getvalue(), "A forest video\n01:23")
        rendered = sample.fit(size)
        lines = rendered.plain.splitlines()
        assert len(lines[0]) == size[0]
        assert len(lines) <= size[1]
        assert lines[-2:] == ["A forest video", "01:23"]
        assert abs((len(lines) - 2) * 2 / len(lines[0]) - 9 / 16) <= 2 / len(lines[0])
        assert sample.fit(size) is rendered

    @pytest.mark.parametrize("height", [0, 240, 360, 480, 720, 1080])
    def test_quality(self, height: int) -> None:
        with BytesIO() as encoded:
            Image.new("RGB", (1920, 1080), "#e8a37e").save(encoded, format="PNG")
            sample = preview.picture(encoded.getvalue(), "Title\n01:23", height=height)
        lines = sample.fit((512, 256)).plain.splitlines()
        pixels = (len(lines) - 2) * 2
        assert pixels == (240 if height == 240 else 288)
        assert len(lines[0]) == (427 if height == 240 else 512)

    @pytest.mark.parametrize("name", list(video.STYLES))
    @pytest.mark.parametrize("motion", [True, False])
    def test_live(self, name: str, motion: bool) -> None:
        sample = preview.overlay(video.Timer(style=name, motion=motion), name)
        assert "Font: " in sample.description
        first = sample.fit((92, 36), elapsed=0)
        assert sample.fit((92, 36), elapsed=0.08) is first
        second = sample.fit((92, 36), elapsed=1.25)
        assert (first.spans != second.spans) is motion
        assert (sample.live is not None) is motion

    def test_name(self) -> None:
        sample = preview.overlay(video.Timer(style="subway-surfers"), "Font sample")
        assert "Font: Bungee" in sample.picture.plain

    @pytest.mark.parametrize("name", ["bungee", "Bungee", "Press Start 2P", "Skranji"])
    @pytest.mark.parametrize("offline", [False, True])
    def test_fonts(
        self,
        runner: CliRunner,
        name: str,
        monkeypatch: pytest.MonkeyPatch,
        fontlist: dict[str, str],
        offline: bool,
    ) -> None:
        if offline:

            def fail(directory: Path):
                raise MiniError("Google Fonts is offline")

            monkeypatch.setattr(wizard, "catalogue", fail)
        monkeypatch.setattr(wizard, "resolve_font", Mock(side_effect=AssertionError("Downloaded")))
        app = terminal.application()
        paths: list[str] = []

        @app.command()
        def run():
            studio = wizard._Studio(timey.Timer())
            paths.append(studio.font(""))

        result = runner.invoke(app, [], input=f"{name}\n")
        assert result.exit_code == 0, result.output
        assert ("offline font shelf" in result.output) is offline
        assert Path(paths[0]).is_file() and Path(paths[0]).stem == name.casefold().replace(" ", "")
