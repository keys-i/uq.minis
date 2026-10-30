"""Timey style behaviour and failure paths"""

import asyncio
import json
import os
import shutil
import subprocess
import time
from contextlib import nullcontext
from dataclasses import replace
from functools import partial
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image, ImageChops, ImageFont, ImageStat

from tests.fixtures import Clip
from uq_minis.assets import ROOT as ASSETS
from uq_minis.core import cache
from uq_minis.core.common import MiniError
from uq_minis.minis import timey
from uq_minis.minis.timey import style, video


class TestStyle:
    def test_cancel(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        closed: list[bool] = []

        async def run() -> None:
            started = asyncio.Event()

            async def response(request: httpx.Request) -> httpx.Response:
                started.set()
                try:
                    await asyncio.sleep(10)
                    return httpx.Response(200)
                finally:
                    closed.append(True)

            client = httpx.AsyncClient
            monkeypatch.setattr(
                httpx, "AsyncClient", partial(client, transport=httpx.MockTransport(response))
            )
            task = asyncio.create_task(
                style.specimen("https://fonts.google.com/specimen/Open+Sans", tmp_path)
            )
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(run())
        assert closed == [True] and not list(tmp_path.iterdir())

    @pytest.mark.parametrize(
        "state", ["fresh", "cached", "stale", "broken", "large", "offline", "malformed"]
    )
    def test_catalogue(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str) -> None:
        payload = json.dumps({
            "familyMetadataList": [
                {"family": "Open Sans", "category": "Sans Serif"},
                {"family": "Noto Sans Devanagari", "category": "Sans Serif"},
            ]
        }).encode()
        path = tmp_path / "catalogue.json"
        if state in {"cached", "stale", "broken"}:
            path.write_bytes(b"bad" if state == "broken" else payload)
            if state == "stale":
                os.utime(path, (1, 1))
        requests: list[str] = []

        def reply(request: httpx.Request):
            requests.append(str(request.url))
            if state in {"offline", "stale"}:
                raise httpx.ConnectError("Offline")
            data = payload
            if state == "large":
                data = b"x" * (cache.SNAPSHOT + 1)
            elif state == "malformed":
                data = b'{"familyMetadataList":[{"family":"bad\\u001b","category":"Serif"}]}'
            return httpx.Response(200, content=data)

        with httpx.Client(transport=httpx.MockTransport(reply)) as client:
            monkeypatch.setattr(httpx, "stream", client.stream)
            if state in {"offline", "large", "malformed"}:
                with pytest.raises(MiniError, match="catalogue"):
                    style.catalogue(tmp_path)
                assert not path.exists()
            else:
                families = style.catalogue(tmp_path)
                assert "Open Sans" in style.fonts("open sans", families)
                assert "Noto Sans Devanagari" in style.fonts("devanagari", families)
                assert "Creepster" in style.fonts("spook", families)
                assert path.read_bytes() == payload
        assert len(requests) == (0 if state == "cached" else 1)
        assert not list(tmp_path.glob(".cache-*"))

    @pytest.mark.parametrize(
        "query,family",
        [
            ("spook", "Creepster"),
            ("ariel", "Arimo"),
            ("Ciznel", "Cinzel"),
            ("sci fi", "Orbitron"),
        ],
    )
    def test_fonts(self, query: str, family: str) -> None:
        assert family in style.fonts(query)
        assert family in style.fonts(query)[family]
        assert not style.fonts("random nonsense")
        with pytest.raises(MiniError, match="200"):
            style.fonts("x" * 201)

    @pytest.mark.parametrize(
        "status,message", [(400, "did not recognise"), (503, "Could not download")]
    )
    def test_font_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int, message: str
    ) -> None:
        if ImageFont is None:
            pytest.skip("Pillow is an optional Timey dependency")
        client = httpx.AsyncClient
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            partial(
                client, transport=httpx.MockTransport(Mock(return_value=httpx.Response(status)))
            ),
        )
        with pytest.raises(MiniError, match=message):
            style.font("https://fonts.google.com/specimen/spook", tmp_path)
        assert not list(tmp_path.iterdir())

    @pytest.mark.parametrize(
        "path,value",
        [
            (("shapes", 0, "points"), [[0, 0], [600, 20]]),
            (("shapes", 0, "points"), [[0, 0], [400, 240]]),
            (("shapes", 0, "points"), [[400, 20], [30, 10]]),
            (("shapes", 0, "points"), [[0, 0], [float("nan"), 20]]),
            (("shapes", 0, "points"), [[0, 0], [10**500, 20]]),
            (("shapes", 0, "points"), "coordinates"),
            (("shapes", 0, "colour"), "red"),
            (("shapes", 0, "kind"), "triangle"),
            (("shapes", 0, "width"), True),
            (("shapes", 2, "points"), [[0, 0], [20, 20]]),
            (("text", "timer", "point"), [0, 60]),
            (("name",), "x" * 100),
            (("name",), "bad\nname"),
            (("name",), 42),
            (("bar", "segments"), 1.5),
            (("font",), "unknown"),
            (("code",), "print('unsafe')"),
        ],
        ids=[
            "width",
            "height",
            "order",
            "nan",
            "overflow",
            "coordinates",
            "colour",
            "shape",
            "bool",
            "polygon",
            "text-position",
            "name-length",
            "control",
            "name-type",
            "segments",
            "font",
            "code",
        ],
    )
    def test_invalid(
        self,
        art: dict[str, Any],
        path: tuple[str, int, str] | tuple[str, str, str] | tuple[str, str] | tuple[str],
        value: Any,
    ) -> None:
        target: Any = art
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(MiniError):
            style.validate(art)

    @pytest.mark.parametrize("agent", ["codex", "claude"])
    def test_generate(
        self, tmp_path: Path, art: dict[str, Any], designer: SimpleNamespace, agent: str
    ) -> None:
        progress: list[tuple[float | None, str]] = []
        generated, saved = style.design(
            "Hollow Knight mask and soul vessel",
            tmp_path,
            agent=agent,
            progress=lambda done, stage: progress.append((done, stage)),
        )
        assert generated == style.read(saved) == art
        assert len(designer.calls) == 1 and progress[-1][0] == 1
        assert not list(tmp_path.glob(".design-*"))

    @pytest.mark.parametrize(
        "agent,response,status,error",
        [
            ("codex", "{broken", 0, "valid structured data"),
            ("codex", "x" * 65537, 0, "too much structured data"),
            ("codex", "{}", 1, "could not finish"),
            ("claude", "{broken", 0, "valid structured data"),
            ("claude", "{}", 0, "valid structured data"),
            (
                "claude",
                '{"is_error":true,"result":"not signed in"}',
                0,
                "not signed in",
            ),
        ],
        ids=["json", "size", "exit", "claude-json", "claude-fields", "claude-error"],
    )
    def test_response(
        self,
        tmp_path: Path,
        designer: SimpleNamespace,
        agent: str,
        response: Any,
        status: int,
        error: str,
    ) -> None:
        designer.output[agent], designer.status = response, status
        original = tmp_path / "saved.json"
        original.write_text("keep")
        with pytest.raises(MiniError, match=error):
            style.design("A custom theme", tmp_path, agent=agent)
        assert original.read_text() == "keep"
        assert not list(tmp_path.glob(".design-*"))

    @pytest.mark.skipif(Image is None, reason="Pillow is an optional Timey dependency")
    @pytest.mark.parametrize("font", ["serif", "pixel"])
    def test_custom(self, art: dict[str, Any], font: str) -> None:
        art["font"] = font
        timer = timey.Timer(seconds=2, start_gap=0, end_gap=0, style=art["name"], artwork=art)
        assert len(list(timey.frames(timer, 1920, 1080))) == 2
        assert next(timey.frames(replace(timer, seconds=3600), 720, 1280, preview=True))

    @pytest.mark.parametrize("force", [False, True], ids=["terminate", "kill"])
    def test_timeout(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        designer: SimpleNamespace,
        force: bool,
    ) -> None:
        from unittest.mock import Mock

        process = Mock(stdin=BytesIO())
        process.poll.side_effect = [None, None]
        process.wait.side_effect = [subprocess.TimeoutExpired("agent", 5), 0] if force else [0]
        monkeypatch.setattr(subprocess, "Popen", Mock(return_value=process))
        monkeypatch.setattr(time, "monotonic", Mock(side_effect=[0, 301]))
        with pytest.raises(MiniError, match="timed out"):
            style.design("A custom theme", tmp_path, agent="codex")
        process.terminate.assert_called_once()
        assert process.kill.call_count == int(force)
        assert process.stdin.closed and not list(tmp_path.glob(".design-*"))

    @pytest.mark.parametrize(
        "chosen,available,expected",
        [
            ("auto", ("codex", "claude"), "codex"),
            ("auto", ("claude",), "claude"),
            ("codex", ("codex",), "codex"),
            ("auto", (), None),
            ("claude", (), None),
            ("unknown", ("codex",), None),
        ],
        ids=["preferred", "fallback", "explicit", "none", "missing", "invalid"],
    )
    def test_designer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        chosen: str,
        available: tuple[str, ...],
        expected: None | str,
    ) -> None:
        def which(name: str) -> str | None:
            return f"/bin/{name}" if name in available else None

        monkeypatch.setattr(shutil, "which", which)
        with nullcontext() if expected else pytest.raises(MiniError):
            assert style.designer(chosen) == expected

    @pytest.mark.parametrize(
        "title,expected",
        [("Temple_Run gameplay", "temple-run"), ("Unknown game", "minimal")],
    )
    def test_suggest(self, title: str, expected: str) -> None:
        assert timey.suggest_style(title) == expected

    @pytest.mark.parametrize("name", timey.STYLES)
    @pytest.mark.parametrize(
        "width,height", [(1920, 1080), (720, 1280)], ids=["landscape", "portrait"]
    )
    def test_layouts(self, name: str, width: int, height: int) -> None:
        if Image is None:
            pytest.skip("Pillow is an optional Timey dependency")
        timer = timey.Timer(seconds=2, start_gap=2, end_gap=2, style=name, position="bottom-centre")
        images = list(timey.frames(timer, width, height))
        assert len(images) == 6
        assert images[0] == images[1] and images[-1] == images[-2]
        assert len({images[0], images[2], images[3], images[4]}) == 4
        with Image.open(BytesIO(images[0])) as panel:
            x, y, _ = timey.placement(timer, width, height)
            assert 0 <= x < x + panel.width <= width
            assert 0 <= y < y + panel.height <= height
            assert panel.mode == "RGBA"

    @pytest.mark.skipif(Image is None, reason="Pillow is an optional Timey dependency")
    @pytest.mark.parametrize("name", ["super-mario", "minions", "sonic", "pac-man"])
    def test_arcade(self, name: str) -> None:
        from uq_minis.minis.timey.scene import Scene

        scene = Scene(name, (540, 234), "#FFE16B", "preview", seconds=30)
        panel = scene.panel()
        still = scene.paint(panel).tobytes()
        assert scene.paint(panel, 0.1).tobytes() != scene.paint(panel, 0.4).tobytes()
        assert scene.paint(panel, 0.1).tobytes() == scene.paint(panel, 0.1).tobytes()
        assert scene.paint(panel).tobytes() == still

    @pytest.mark.skipif(Image is None, reason="Pillow is an optional Timey dependency")
    def test_preview(self) -> None:
        timer = timey.Timer(seconds=86400, start_gap=3600, end_gap=3600)
        assert len(list(timey.frames(timer, 1920, 1080, preview=True))) == 1

    def test_art(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        if Image is None:
            pytest.skip("Pillow is an optional Timey dependency")
        original = video._temple_digits
        glyphs = original()
        assert set(glyphs) == set("0123456789:")
        assert len({glyph.tobytes() for glyph in glyphs.values()}) == 11
        assert all(
            glyph.mode == "RGBA" and glyph.getchannel("A").getextrema() == (0, 255)
            for glyph in glyphs.values()
        )
        calls: list[int] = []

        def load(height: int):
            calls.append(height)
            return original(height)

        monkeypatch.setattr(video, "_temple_digits", load)
        timer = timey.Timer(seconds=30, start_gap=1, end_gap=1, style="temple-run", size=1)
        images = list(timey.frames(timer, 3840, 2160))
        assert len(images) == 32 and calls == [176]
        intro = Image.open(BytesIO(images[0]))
        live = Image.open(BytesIO(images[1]))
        bounds = ImageChops.difference(intro, live).convert("RGB").getbbox()
        assert bounds is not None
        left, top, right, bottom = bounds
        assert 210 <= left < right <= 871 and 376 <= top < bottom <= 409
        with Image.open((ASSETS / "timey/art") / "plate.png") as stone:
            backdrop = stone.convert("RGBA").resize(  # pyright: ignore[reportUnknownMemberType]
                live.size, Image.Resampling.LANCZOS
            )
            assert (
                ImageChops
                .difference(live, backdrop)
                .convert("RGB")
                .crop((400, 358, 680, 380))
                .getbbox()
                is None
            )
        _, edge = video.surface(images[0], timer)
        with edge as panel:
            alpha = panel.getchannel("A")
            assert alpha.crop((150, 175, 930, 358)).getbbox() is None
            assert alpha.crop((20, 230, 100, 310)).getbbox() is not None
            assert alpha.crop((215, 386, 865, 396)).getbbox() is None
        previews = [
            Image.open(
                BytesIO(
                    next(timey.frames(replace(timer, seconds=seconds), 3840, 2160, preview=True))
                )
            )
            for seconds in (86400, 3661)
        ]
        bounds = ImageChops.difference(*previews).convert("RGB").getbbox()
        assert bounds is not None
        left, top, right, bottom = bounds
        assert 150 <= left < right <= 930 and 186 <= top < bottom <= 358
        custom = replace(timer, font=str((ASSETS / "timey/fonts") / "skranji.ttf"))
        calls.clear()
        custom_frame = next(timey.frames(custom, 3840, 2160, preview=True))
        assert not calls and custom_frame != images[1]
        next(timey.frames(replace(timer, label="Focus time"), 3840, 2160, preview=True))
        assert calls == [124]

    def test_motion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clip: Clip) -> None:
        source = clip("source.mp4", "color=c=black:s=640x360:r=30:d=1")
        timer = timey.Timer(
            seconds=86400,
            start_gap=3600,
            end_gap=3600,
            style="temple-run",
            size=2,
            loop_blend=0,
        )
        original = video.frames
        counts: list[bool] = []

        def frames(*args: Any, **kwargs: Any):
            for png in original(*args, **kwargs):
                counts.append(True)
                yield png

        monkeypatch.setattr(video, "frames", frames)
        for fps, motion in ((24, True), (30, True), (60, True), (30, False)):
            counts.clear()
            output = tmp_path / f"{fps}-{motion}.mp4"
            timey.render(source, output, replace(timer, motion=motion), sample=True, fps=fps)
            assert len(counts) == 10 * (fps if motion else 1) and timer.start_gap == 3600
            metadata = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "csv=p=0",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            assert float(metadata) == pytest.approx(10, abs=0.04)
            selected = "+".join(f"eq(n,{round(moment * fps)})" for moment in (1.75, 2.083333, 2.5))
            pixels = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(output),
                    "-vf",
                    f"select='{selected}',crop=240:42:200:173,format=rgb24",
                    "-fps_mode",
                    "passthrough",
                    "-f",
                    "rawvideo",
                    "pipe:1",
                ],
                capture_output=True,
                check=True,
            ).stdout
            chunk = 240 * 42 * 3
            assert len(pixels) == chunk * 3
            before, middle, settled = [
                Image.frombytes("RGB", (240, 42), pixels[i : i + chunk])
                for i in range(0, len(pixels), chunk)
            ]
            distance_before = sum(ImageStat.Stat(ImageChops.difference(before, middle)).mean) / 3
            distance_after = sum(ImageStat.Stat(ImageChops.difference(settled, middle)).mean) / 3
            assert distance_before > 0.5
            assert distance_after > 0.5 if motion else distance_after < 0.5
        with pytest.raises(MiniError, match="still preview or a motion sample"):
            timey.render(source, tmp_path / "invalid.png", timer, preview=True, sample=True)

    def test_font(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        if Image is None:
            pytest.skip("Pillow is an optional Timey dependency")
        font_path = video.typeface("mono", 16).path
        assert isinstance(font_path, (str, bytes, Path))
        payload = Path(
            font_path.decode() if isinstance(font_path, bytes) else font_path
        ).read_bytes()
        requested: list[str] = []
        real_client = httpx.AsyncClient

        def response(request: httpx.Request):
            requested.append(str(request.url))
            if request.url.host == "fonts.googleapis.com":
                return httpx.Response(
                    200,
                    text="@font-face {src: url(https://fonts.gstatic.com/s/test/font.ttf)}",
                )
            return httpx.Response(200, content=payload)

        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            partial(real_client, transport=httpx.MockTransport(response)),
        )
        cached = style.font("https://fonts.google.com/specimen/Press+Start+2P", tmp_path)
        assert Path(cached).read_bytes() == payload
        assert "family=Press+Start+2P" in requested[0]
        assert style.font("https://fonts.google.com/specimen/Press+Start+2P", tmp_path) == cached
        assert len(requested) == 2
        for link in (
            "http://fonts.google.com/specimen/Roboto",
            "https://fonts.google.com.evil.test/specimen/Roboto",
            "https://evil@fonts.google.com/specimen/Roboto",
            "https://fonts.google.com:444/specimen/Roboto",
        ):
            with pytest.raises(MiniError, match="HTTPS Google Fonts"):
                style.font(link, tmp_path)
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            partial(
                real_client,
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        302, headers={"location": "https://evil.test/font.ttf"}
                    )
                ),
            ),
        )
        with pytest.raises(MiniError, match="HTTPS Google Fonts"):
            style.font("https://fonts.gstatic.com/s/test/redirect.ttf", tmp_path)


def test_design_discussion(
    tmp_path: Path, art: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    generate = Mock(
        side_effect=[
            {"questions": ["Should the leaves grow as time passes?"], "artwork": None},
            {"questions": [], "artwork": art},
        ]
    )
    monkeypatch.setattr(style, "generate", generate)
    questions, artwork, saved = style.discuss("Ask me about a leafy clock", tmp_path)
    assert questions and artwork is None and saved is None and not list(tmp_path.glob("*.json"))
    questions, artwork, saved = style.discuss("Yes, grow the leaves", tmp_path, base=art)
    assert not questions and artwork == art and saved is not None and style.read(saved) == art
    assert "Refine this existing design" in generate.call_args.args[0]
