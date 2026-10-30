from dataclasses import replace
from io import BytesIO
from itertools import islice

import pytest
from PIL import Image, ImageChops

from uq_minis.core.common import MiniError
from uq_minis.minis.timey import preview, video
from uq_minis.minis.timey.scene import Scene, liquid


@pytest.mark.parametrize("kind", video.STYLES)
def test_scene(kind: str) -> None:
    timer = video.Timer(style=kind, seconds=2, start_gap=1, end_gap=1)
    frames = list(video.frames(timer, 480, 270, fps=24))
    assert len(frames) == timer.total * 24
    assert frames[6] != frames[15]
    assert frames == list(video.frames(timer, 480, 270, fps=24))
    still = list(video.frames(replace(timer, motion=False), 480, 270, fps=24))
    assert len(still) == timer.total
    assert len({Image.open(BytesIO(frame)).size for frame in frames}) == 1
    sample = preview.overlay(timer, kind)
    assert sample.fit((72, 36), elapsed=0).plain == sample.fit((72, 36), elapsed=0.5).plain
    assert sample.fit((72, 36), elapsed=0).spans != sample.fit((72, 36), elapsed=0.5).spans
    # A long inactive interval seeks directly and still ends on the final state
    assert sample.fit((72, 36), elapsed=10000).spans


@pytest.mark.parametrize("kind", video.STYLES)
def test_material(kind: str) -> None:
    timer = video.Timer(style=kind, seconds=12, start_gap=0, end_gap=0)
    canvas, mask = next(video.layers(timer, 480, 270))
    scene = Scene(kind, canvas.size, "#aaddff", "font", seconds=timer.seconds)
    scene.set(mask)
    assert scene.material.getchannel("A").tobytes() == mask.tobytes()
    assert scene.paint(canvas).tobytes() == scene.paint(canvas).tobytes()
    colours = scene.material.crop(mask.getbbox()).getcolors(canvas.width * canvas.height)
    assert colours and (kind == "minecraft" or len(colours) > 2)


@pytest.mark.parametrize(
    "kind",
    [
        "minecraft",
        "super-mario",
        "minions",
        "sonic",
        "pac-man",
        "subway-surfers",
        "minimal",
        "neon",
    ],
)
def test_open_overlay(kind: str) -> None:
    timer = video.Timer(style=kind, seconds=30, start_gap=0, end_gap=1)
    canvas, mask = next(video.layers(timer, 960, 540))
    scene = Scene(kind, canvas.size, "#8FDA53", "hud", seconds=timer.seconds)
    scene.set(mask)
    healthy, depleted = scene.paint(canvas, 1), scene.paint(canvas, 28)
    alpha = healthy.getchannel("A")
    assert sum(value == 0 for value in alpha.tobytes()) > canvas.width * canvas.height * 0.35
    assert healthy.tobytes() != depleted.tobytes()
    assert mask.getbbox() and mask.getextrema()[1] == 255
    if kind == "minecraft":
        assert (
            healthy.crop((0, round(canvas.height * 0.72), *canvas.size)).tobytes()
            != depleted.crop((0, round(canvas.height * 0.72), *canvas.size)).tobytes()
        )


def test_seek() -> None:
    timer = video.Timer(seconds=12, start_gap=2, end_gap=3)
    for offset in (0, 1, 4, 14, 16):
        expected = next(islice(video.layers(timer, 480, 270), offset, None))
        actual = next(video.layers(timer, 480, 270, offset=offset))
        assert [part.tobytes() for part in actual] == [part.tobytes() for part in expected]
        assert len(list(video.layers(timer, 480, 270, offset=offset))) == timer.total - offset


@pytest.mark.parametrize("size", [(1, 1), (64, 32), (540, 234)])
def test_liquid(size: tuple[int, int]) -> None:
    canvas = Image.linear_gradient("L").resize(size).convert("RGBA")  # pyright: ignore[reportUnknownMemberType]
    other = canvas.copy()
    liquid(other, (0, 0, *size), 1)
    assert other.size == canvas.size and other.mode == "RGBA"
    if min(size) > 1:
        assert ImageChops.difference(canvas, other).getchannel("R").getbbox()


@pytest.mark.parametrize("fps", [0, 61, True])
def test_rate(fps: int) -> None:
    with pytest.raises(MiniError, match="frame rate"):
        next(video.frames(video.Timer(), 480, 270, fps=fps))


@pytest.mark.parametrize("offset", [-1, 611, True])
def test_offset(offset: int) -> None:
    with pytest.raises(MiniError, match="offset"):
        next(video.layers(video.Timer(), 480, 270, offset=offset))


@pytest.mark.skipif(Image is None, reason="Pillow is an optional Timey dependency")
class TestTemple:
    def test_digits_stay_whole_above_falling_stone(self) -> None:
        from PIL import ImageDraw

        scene = Scene("temple-run", (540, 234), "#E4C36E", "digits", seconds=30)
        mask = Image.new("L", scene.size)
        ImageDraw.Draw(mask).rectangle((100, 80, 440, 160), fill=255)
        scene.set(mask, moment=29)
        empty = Image.new("RGBA", scene.size)
        rendered = scene.paint(empty, 29.25)
        assert (
            rendered.crop(mask.getbbox()).tobytes() == scene.material.crop(mask.getbbox()).tobytes()
        )
        assert sum(rendered.getchannel("A").tobytes()) < sum(mask.tobytes()) * 1.05

    def test_timeline(self) -> None:

        scene = Scene("temple-run", (540, 234), "#E4C36E", "timeline", seconds=30, start_gap=3)
        assert scene.remaining(0) == scene.remaining(3) == 30
        assert scene.power(0) == scene.power(3) == 1
        assert 0 < scene.power(18) < 1
        assert scene.remaining(23) == 10 and scene.power(23) == 0
        assert scene.remaining(28) == 5 and scene.power(28) == 0
        assert scene.remaining(40) == 0

    def test_seek_matches_export(self) -> None:

        timer = video.Timer(seconds=30, start_gap=2, end_gap=1, style="temple-run")
        full = video.frames(timer, 480, 270, fps=4)
        seek = video.frames(timer, 480, 270, fps=4, offset=29)
        try:
            assert next(islice(full, 29 * 4 + 1, None)) == next(islice(seek, 1, None))
        finally:
            full.close()
            seek.close()

    def test_depletion_repair_and_collapse(self) -> None:
        from PIL import ImageStat

        from uq_minis.assets import ROOT as ASSETS

        with Image.open(ASSETS / "timey/art/plate.png") as art:
            plate = art.convert("RGBA").resize((540, 234))  # pyright: ignore[reportUnknownMemberType]
        scene = Scene("temple-run", plate.size, "#E4C36E", "repair", seconds=30)
        healthy = scene.paint(plate, 0)
        repaired = scene.paint(plate, 10)
        exhausted = scene.paint(plate, 20)
        assert (
            ImageStat.Stat(healthy.crop((241, 28, 254, 42))).mean[1]
            > ImageStat.Stat(exhausted.crop((241, 28, 254, 42))).mean[1] * 2
        )
        assert repaired.tobytes() == scene.paint(plate, 10).tobytes()
        assert repaired.tobytes() != healthy.tobytes()
        border = scene.paint(plate, 25).getchannel("A")
        broken = scene.paint(plate, 29).getchannel("A")
        assert sum(broken.tobytes()) < sum(border.tobytes()) * 0.75
        assert len(scene.shards) == 48
        assert scene.paint(plate, 29).tobytes() == scene.paint(plate, 29).tobytes()
        assert len(scene.shards) == 48
        assert scene.paint(plate, 10).tobytes() == repaired.tobytes()


@pytest.mark.parametrize(
    "kind", ["minecraft", "super-mario", "minions", "sonic", "pac-man", "subway-surfers"]
)
def test_game_motion_seeks_to_the_same_state(kind: str) -> None:
    timer = video.Timer(style=kind, seconds=12, start_gap=1, end_gap=1)
    full = video.frames(timer, 480, 270, fps=4)
    seek = video.frames(timer, 480, 270, fps=4, offset=3)
    try:
        assert next(islice(full, 13, None)) == next(islice(seek, 1, None))
    finally:
        full.close()
        seek.close()
