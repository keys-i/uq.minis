"""Timey timer behaviour and failure paths"""

from contextlib import nullcontext
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from tests.fixtures import Clip
from uq_minis.core.common import MiniError
from uq_minis.minis import timey
from uq_minis.minis.timey import video


class TestTimer:
    @pytest.mark.parametrize(
        "settings",
        [
            {"seconds": 0},
            {"seconds": 86401},
            {"seconds": True},
            {"start_gap": -1},
            {"end_gap": 3601},
            {"accent": "red"},
            {"label": "bad\nlabel"},
            {"size": float("nan")},
            {"size": 3.1},
            {"size": 10**999},
            {"width": float("nan")},
            {"width": 0.01},
            {"height": 1.1},
            {"height": True},
            {"x": 0.4},
            {"x": 0.4, "y": float("nan")},
            {"x": -0.1, "y": 0},
            {"x": 1, "y": 1.1},
            {"loop_blend": float("inf")},
            {"loop_blend": -0.1},
        ],
        ids=lambda settings: next(iter(settings)),
    )
    def test_invalid(self, settings: dict[str, Any]) -> None:
        with pytest.raises(MiniError):
            timey.Timer(**settings)

    def test_defaults(self) -> None:
        assert timey.Timer(seconds=3, start_gap=2, end_gap=4).total == 9
        assert timey.clock(0, hours=True) == "00:00:00"
        assert timey.clock(3661) == "01:01:01"
        assert timey.Timer().position == "centre"
        assert timey.Timer().size == 2.4 and timey.Timer().label == ""
        assert timey.placement(timey.Timer(), 1920, 1080)[2] == pytest.approx(
            timey.placement(timey.Timer(size=1.4), 1920, 1080)[2] * (2.4 / 1.4)
        )

    @pytest.mark.parametrize("dimensions", [(960, 540), (304, 540), (1920, 1080)])
    def test_custom_placement_stays_in_frame(self, dimensions: tuple[int, int]) -> None:
        width, height = dimensions
        for x, y in ((0, 0), (0.3, 0.8), (1, 1)):
            left, top, scale = timey.placement(timey.Timer(x=x, y=y), width, height)
            margin = max(1, round(min(width, height) * 0.025))
            assert margin <= left <= width - round(540 * scale) - margin
            assert margin <= top <= height - round(234 * scale) - margin

    @pytest.mark.parametrize("style", ["minimal", "temple-run", "glass"])
    def test_independent_dimensions_reach_previews_and_exports(
        self, style: str, clip: Clip, tmp_path: Path
    ) -> None:

        timer = timey.Timer(
            seconds=1,
            start_gap=0,
            end_gap=0,
            style=style,
            width=0.6,
            height=0.25,
            motion=False,
            loop_blend=0,
        )
        with Image.open(BytesIO(next(timey.frames(timer, 320, 180, preview=True)))) as panel:
            assert panel.size == (192, 45)
        assert timey.placement(timer, 320, 180)[:2] == (64, 67)
        source = clip(f"{style}.mp4", "color=c=blue:s=320x180:r=10", 1)
        output = tmp_path / f"{style}-resized.mp4"
        timey.render(source, output, timer, fps=24)
        assert video.inspect(output)[:2] == (320, 180)
        assert video.inspect(output)[3] == pytest.approx(1, abs=0.1)

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("600", 600),
            ("10m", 600),
            ("25:00", 1500),
            ("1:02:03", 3723),
            ("1h 30m", 5400),
            ("0s", 0),
            ("", None),
            ("1:60", None),
            ("-10", None),
            ("1.5m", None),
            ("10 days", None),
            ("2m 1h", None),
        ],
        ids=[
            "raw",
            "minutes",
            "clock",
            "hours",
            "units",
            "zero",
            "empty",
            "seconds",
            "negative",
            "fraction",
            "unit",
            "order",
        ],
    )
    def test_duration(self, value: str, expected: None | int) -> None:
        with pytest.raises(MiniError) if expected is None else nullcontext():
            assert timey.duration(value) == expected
