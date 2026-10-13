from collections.abc import Mapping

import pytest
from docs.assets.terminal import sculpt


@pytest.mark.parametrize(
    "name,action",
    [
        ("numbat", "wander"),
        ("elephant", "trundle"),
        ("penguin", "waddle"),
        ("dolphin", "riverglide"),
    ],
)
def test_motion(monkeypatch: pytest.MonkeyPatch, name: str, action: str) -> None:
    shapes, cuts = sculpt.animals[name]
    frames: list[Mapping[str, sculpt.Shape]] = []

    def capture(
        model: Mapping[str, sculpt.Shape], cuts: Mapping[str, sculpt.Shape], grain: float = 0
    ) -> dict[str, str]:
        frames.append(model)
        return {}

    monkeypatch.setattr(sculpt, "draw", capture)
    for phase in (0, 0.25, 0.5, 0.75, 1):
        sculpt.pose(name, shapes, cuts, action, phase)
    if name == "dolphin":
        assert not any(
            key.startswith("scenewaterwake") for frame in (frames[0], frames[-1]) for key in frame
        )
        assert sum(key.startswith("scenewaterwake") for key in frames[2]) == 3
    else:
        for frame in frames:
            planted = [abs(frame[key][1] - shapes[key][1]) < 1e-8 for key in ("foot1", "foot2")]
            assert any(planted)
            assert all(frame[key][1] <= shapes[key][1] + 1e-8 for key in ("foot1", "foot2"))
    assert frames[0]["body"] == frames[-1]["body"]
