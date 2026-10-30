from collections.abc import Mapping
from math import cos, hypot, sin
from tomllib import loads

import pytest
from assets.terminal import sculpt


@pytest.fixture
def frames(monkeypatch: pytest.MonkeyPatch) -> list[Mapping[str, sculpt.Shape]]:
    frames: list[Mapping[str, sculpt.Shape]] = []

    def capture(
        model: Mapping[str, sculpt.Shape],
        cuts: Mapping[str, sculpt.Shape],
        grain: float = 0,
        outlines: Mapping[str, sculpt.Contour] | None = None,
    ) -> dict[str, str]:
        frames.append(model)
        return {}

    monkeypatch.setattr(sculpt, "draw", capture)
    return frames


@pytest.mark.parametrize(
    "name,action",
    [
        ("numbat", "wander"),
        ("elephant", "trundle"),
        ("penguin", "waddle"),
        ("dolphin", "riverglide"),
        ("frog", "leap"),
        ("potoroo", "bound"),
        ("huia", "flutter"),
        ("bee", "orbit"),
    ],
)
def test_motion(frames: list[Mapping[str, sculpt.Shape]], name: str, action: str) -> None:
    shapes, cuts = sculpt.animals[name]
    for phase in (0, 0.04, 0.08, 0.25, 0.5, 0.75, 1):
        sculpt.pose(name, shapes, cuts, action, phase)
    if name == "dolphin":
        assert not any(
            key.startswith("scenewaterwake") for frame in (frames[0], frames[-1]) for key in frame
        )
        assert sum(key.startswith("scenewaterwake") for key in frames[4]) == 3
    elif action in sculpt.WALKS:
        for frame in frames:
            planted = [abs(frame[key][1] - shapes[key][1]) < 1e-8 for key in ("foot1", "foot2")]
            assert any(planted)
            assert all(frame[key][1] <= shapes[key][1] + 1e-8 for key in ("foot1", "foot2"))
        assert frames[1]["foot1"][:2] == frames[2]["foot1"][:2]
        assert frames[1]["body"][0] != frames[2]["body"][0]
        assert frames[4]["scenegroundback0"][0] > shapes["scenegroundback0"][0]
    else:
        assert frames[4]["body"][1] < shapes["body"][1]
        assert all(frames[4][key][1] < shapes[key][1] for key in ("foot1", "foot2"))
    assert frames[0]["body"] == frames[-1]["body"]


def test_species() -> None:
    for name in sculpt.FLIGHTLESS:
        assert not set(sculpt.FOREST[name]["idle"].split()) & sculpt.FLIGHTS
    for name in ("orangutan", "gorilla", "bonobo"):
        assert "tail" not in sculpt.animals[name][0]
    for name in ("penguin", "auk", "kakapo"):
        assert all(key in sculpt.animals[name][0] for key in ("leg1", "leg2", "paw1"))
    assert all(f"foot{n}" in sculpt.animals["bee"][0] for n in range(1, 7))
    assert all(f"leg{n}" in sculpt.animals["crayfish"][0] for n in range(8))
    assert "fistwalk" in sculpt.FOREST["orangutan"]["idle"]


@pytest.mark.parametrize("name", sculpt.animals)
def test_attached(frames: list[Mapping[str, sculpt.Shape]], name: str) -> None:
    shapes, cuts = sculpt.animals[name]
    for action in (*sculpt.FOREST[name]["idle"].split()[:4], "look", "pet", "blink"):
        sculpt.pose(name, shapes, cuts, action, 0.37)
    for frame in frames:
        for number in range(1, 5):
            leg = f"leg{number}" if name in sculpt.BIRDS else f"paw{number}"
            if f"shin{number}" not in frame:
                continue
            x, y, rx, ry, _, _, angle = frame[leg]
            elbow = x - ry * sin(angle), y + ry * cos(angle)
            x, y, sx, sy, _, _, angle = frame[f"shin{number}"]
            knee = x + sy * sin(angle), y - sy * cos(angle)
            assert hypot(elbow[0] - knee[0], elbow[1] - knee[1]) <= rx + sx
        if "tail" in frame:
            x, y, rx, ry, _, _, angle = frame["body"]
            root = (
                x + rx * 0.7 * cos(angle) - ry * 0.15 * sin(angle),
                y + rx * 0.7 * sin(angle) + ry * 0.15 * cos(angle),
            )
            assert sculpt.surface(*root, frame["tailbase"]) is not None
            tx, ty, rx, _, _, _, angle = frame["tail"]
            end = tx - rx * 0.6 * cos(angle), ty - rx * 0.6 * sin(angle)
            assert sculpt.surface(*end, frame["tailbase"]) is not None
        assert hypot(
            frame["eye1"][0] - frame["head"][0], frame["eye1"][1] - frame["head"][1]
        ) == pytest.approx(
            hypot(shapes["eye1"][0] - shapes["head"][0], shapes["eye1"][1] - shapes["head"][1]),
            abs=0.015,
        )
    if name in ("bee", "paddlefish", "axolotl", "crayfish"):
        assert frames[-1]["eye1"][3] == shapes["eye1"][3]


def test_grid() -> None:
    drawing = sculpt.draw({}, {})
    assert {len(value.splitlines()) for value in drawing.values()} == {sculpt.HEIGHT // 4}
    encoded = sculpt.fields(drawing)
    assert sculpt.fields(loads(encoded)) == encoded


@pytest.mark.parametrize(
    "points",
    [
        (),
        ((0, 0),) * 3,
        ((-1, 0), (0, 0), (1, 0)),
        ((0, 0), (float("nan"), 0), (0, 1)),
        ((0, 0), (2, 0), (0, 1)),
    ],
)
def test_contour(points: sculpt.Contour) -> None:
    with pytest.raises(ValueError):
        sculpt.contour(points)


def test_edges() -> None:
    outline = sculpt.CONTOURS["triangle"]
    model = sculpt.shape(0.5, 0.5, 0.1, 0.1)
    assert sculpt.surface(0.5, 0.42, model, outline) is not None
    assert sculpt.surface(0.57, 0.42, model, outline) is None
    # Two separate spans retain a notch rather than filling its bounding ellipse
    notch = (
        (-1.0, -1.0),
        (-0.2, -1.0),
        (-0.2, 0.5),
        (0.2, 0.5),
        (0.2, -1.0),
        (1.0, -1.0),
        (1.0, 1.0),
        (-1.0, 1.0),
    )
    assert sculpt.spans(notch, 0) == [(-1, -0.2), (0.2, 1)]
    assert all("body" in sculpt.OUTLINES[name] for name in sculpt.animals)
    assert sculpt.OUTLINES["saola"]["horn1"] != sculpt.OUTLINES["tahr"]["horn1"]
    assert sculpt.OUTLINES["whale"]["paw2"] != sculpt.OUTLINES["vaquita"]["paw2"]
    turtle = sculpt.animals["turtle"][0]
    assert all(f"paw{n}" in turtle for n in range(1, 5))
    assert not any(key.startswith("foot") for key in turtle)


@pytest.mark.parametrize("side", [-1, 1])
@pytest.mark.parametrize("end", [(0.3, 0.1), (0.1, 0.3), (-0.3, 0.1)])
def test_hinge(side: int, end: tuple[float, float]) -> None:
    joint = sculpt.hinge((0, 0), end, 0.2, 0.2, side)
    assert hypot(*joint) == pytest.approx(0.2)
    assert hypot(end[0] - joint[0], end[1] - joint[1]) == pytest.approx(0.2)


@pytest.mark.parametrize(
    "name,action",
    [
        ("saola", "ears"),
        ("tahr", "ears"),
        ("whale", "finsweep"),
        ("vaquita", "tailglide"),
        ("paddlefish", "finroll"),
    ],
)
def test_rigid(frames: list[Mapping[str, sculpt.Shape]], name: str, action: str) -> None:
    shapes, cuts = sculpt.animals[name]
    sculpt.pose(name, shapes, cuts, action, 0.37)
    frame = frames[-1]
    part, root = ("horn1", "head") if "horn1" in shapes else ("paw2", "body")
    assert frame[part][6] - frame[root][6] == pytest.approx(shapes[part][6] - shapes[root][6])
    assert hypot(frame[part][0] - frame[root][0], frame[part][1] - frame[root][1]) == pytest.approx(
        hypot(shapes[part][0] - shapes[root][0], shapes[part][1] - shapes[root][1]), abs=0.003
    )


@pytest.mark.parametrize(
    "name,action",
    [
        ("tahr", "amble"),
        ("numbat", "wander"),
        ("whale", "tailglide"),
        ("turtle", "reefglide"),
        ("huia", "flutter"),
    ],
)
def test_whole(frames: list[Mapping[str, sculpt.Shape]], name: str, action: str) -> None:
    shapes, cuts = sculpt.animals[name]
    for phase in (0.32, 0.34):
        sculpt.pose(name, shapes, cuts, action, phase)
    changed = {key for key in shapes if frames[0][key] != frames[1][key]}
    assert {"body", "head", "tail"} <= changed
    assert len(changed) >= 8
    assert (
        max(
            hypot(frames[0][key][0] - frames[1][key][0], frames[0][key][1] - frames[1][key][1])
            for key in changed
        )
        < 0.08
    )


def test_clip() -> None:
    body = sculpt.shape(0.5, 0.5, 0.15, 0.1)
    shapes = {"body": body, "white0": sculpt.shape(0.5, 0.5, 0.015, 0.2, 0.01, 0.2)}
    drawing = sculpt.draw(shapes, {}, outlines={"body": sculpt.CONTOURS["cat"]})
    # Markings cannot add dots beyond their host's silhouette
    base = sculpt.draw({"body": body}, {}, outlines={"body": sculpt.CONTOURS["cat"]})
    assert drawing["art"] == base["art"]


@pytest.mark.parametrize(
    "name,action",
    [
        ("huia", "flutter"),
        ("pigeon", "pigeon-soar"),
        ("eagle", "eagle-soar"),
        ("vulture", "vulture-soar"),
    ],
)
def test_wings(frames: list[Mapping[str, sculpt.Shape]], name: str, action: str) -> None:
    def ends(model: sculpt.Shape) -> tuple[tuple[float, float], tuple[float, float]]:
        x, y, rx, ry, _, _, angle = model
        half = ry - rx * 0.3
        return (x + half * sin(angle), y - half * cos(angle)), (
            x - half * sin(angle),
            y + half * cos(angle),
        )

    shapes, cuts = sculpt.animals[name]
    for phase in (0.21, 0.27, 0.32):
        sculpt.pose(name, shapes, cuts, action, phase)
    for frame in frames:
        for number in (1, 2):
            upper, lower = f"paw{number}", f"wing{number}"
            shoulder, elbow = ends(frame[upper])
            assert elbow == pytest.approx(ends(frame[lower])[0])
            wrist = ends(frame[lower])[1]
            for feather in range(7):
                assert ends(frame[f"primary{number}_{feather}"])[0] == pytest.approx(wrist)
            assert hypot(elbow[0] - shoulder[0], elbow[1] - shoulder[1]) == pytest.approx(
                2 * (shapes[upper][3] - shapes[upper][2] * 0.3)
            )
    assert frames[0]["wing1"][6] - frames[0]["paw1"][6] != pytest.approx(
        frames[1]["wing1"][6] - frames[1]["paw1"][6]
    )
    assert sculpt.ANATOMY["wings"]["pigeon"]["fan"] < sculpt.ANATOMY["wings"]["vulture"]["fan"]


def test_trot(frames: list[Mapping[str, sculpt.Shape]]) -> None:
    shapes, cuts = sculpt.animals["dog"]
    for phase in (0.18, 0.22, 0.26, 0.3):
        sculpt.pose("dog", shapes, cuts, "trot", phase)
    for frame in frames:
        lift = [frame[f"foot{n}"][1] - shapes[f"foot{n}"][1] for n in range(1, 5)]
        assert lift[0] == pytest.approx(lift[3])
        assert lift[1] == pytest.approx(lift[2])
    assert any(frame["foot1"][1] < shapes["foot1"][1] for frame in frames)


def test_feet() -> None:
    assert sculpt.OUTLINES["saola"]["foot1"] != sculpt.OUTLINES["horse"]["foot1"]
    assert sculpt.OUTLINES["penguin"]["foot1"] != sculpt.OUTLINES["pigeon"]["foot1"]
    assert sculpt.OUTLINES["gorilla"]["foot1"] != sculpt.OUTLINES["dog"]["foot1"]
    assert sculpt.OUTLINES["numbat"]["paw1"] != sculpt.OUTLINES["numbat"]["paw2"]
