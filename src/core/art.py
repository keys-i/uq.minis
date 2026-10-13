"""Shared dot sculptures and bounded terminal image previews"""

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache, lru_cache
from importlib.resources import files

from rich.text import Text


@dataclass(frozen=True, slots=True)
class Preview:
    """A small terminal picture with a readable text alternative"""

    picture: Text
    description: str


def blend(first: str, second: str, amount: float) -> str:
    """Mix trusted RGB theme colours without an extra rendering dependency"""
    channels = [
        round(int(first[i : i + 2], 16) * (1 - amount) + int(second[i : i + 2], 16) * amount)
        for i in (1, 3, 5)
    ]
    return "#" + "".join(f"{value:02x}" for value in channels)


def image(rows: Sequence[Sequence[tuple[int, int, int]]], description: str) -> Preview:
    """Draw bounded RGB rows with two pixels per terminal cell"""
    if (
        not rows
        or not 0 < len(rows[0]) <= 40
        or len(rows) > 32
        or any(len(row) != len(rows[0]) for row in rows)
        or any(
            len(pixel) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in pixel)
            for row in rows
            for pixel in row
        )
    ):
        raise ValueError("Terminal previews must fit within 40 × 32 pixels")
    picture = Text()
    for top in range(0, len(rows), 2):
        for x, colour in enumerate(rows[top]):
            fg = "#" + "".join(f"{channel:02x}" for channel in colour)
            bottom = rows[min(top + 1, len(rows) - 1)][x]
            bg = "#" + "".join(f"{channel:02x}" for channel in bottom)
            picture.append("▀", f"{fg} on {bg}")
        picture.append("\n")
    caption = Text(description)
    picture.append(caption)
    return Preview(picture, description)


@dataclass(frozen=True, slots=True)
class Habitat:
    """A mini's animal, useful object and colours within the shared forest"""

    animal: str
    name: str
    status: str
    country: str
    flag: str
    place: str
    object: str
    primary: str
    secondary: str
    fur: str
    leaf: str
    water: str
    ground: str
    flower: str
    idle: str
    art: str
    shade: str
    hit: str
    tone: str
    head: str
    body: str
    quip: str
    source: str
    head_moves: str
    body_moves: str
    object_moves: str

    def styles(self) -> dict[str, str]:
        """Keep headings, choices and progress in the same visual family"""
        return {
            "accent": self.primary,
            "bar.complete": self.primary,
            "bar.finished": self.secondary,
            "bar.pulse": self.primary,
        }

    def seconds(self, pose: str) -> float:
        """Let each routine finish at the shared eight-frame cadence"""
        return len(poses(self.animal)[pose]) / 8

    def region(self, frame: int, pose: str, x: int, y: int) -> str | None:
        """Keep pointer targets attached to the animal and object as they move"""
        rows = self.hit.splitlines()
        if pose != "idle":
            frames = poses(self.animal)[pose]
            rows = frames[min(frame, len(frames) - 1)]["hit"].splitlines()
        if 0 <= y < len(rows) and 2 <= x < len(rows[y]) + 2:
            return {"1": "ears", "2": "pet", "3": "object"}.get(rows[y][x - 2])
        return None

    @cache
    def colours(self) -> tuple[tuple[str, ...], ...]:
        """Keep fur, markings, foliage and water distinct under the same light"""
        palettes: list[tuple[str, ...]] = []
        for colour in (
            self.fur,
            "#f8f1e3",
            "#19212d",
            self.leaf,
            self.water,
            self.flower,
            self.ground,
            "#fffaf1",
        ):
            light = "#" + "".join(
                f"{min(255, round(int(colour[i : i + 2], 16) * 1.25 + 16)):02x}" for i in (1, 3, 5)
            )
            shadow = blend(colour, "#000000", 0.65)
            stops = (shadow, colour, light)
            palette: list[str] = []
            for level in range(8):
                position = level / 7 * 2
                lower = min(int(position), 1)
                ratio = position - lower
                palette.append(blend(stops[lower], stops[lower + 1], ratio))
            palettes.append(tuple(palette))
        return tuple(palettes)

    @lru_cache(maxsize=144)
    def picture(self, frame: int = 0, pose: str = "idle") -> Text:
        """Draw a shaded movement frame from the mini's bundled sculpture"""
        colours = self.colours()
        picture = Text()
        drawing = {"art": self.art, "shade": self.shade, "tone": self.tone}
        if pose != "idle":
            sequence = poses(self.animal)[pose]
            drawing = sequence[min(frame, len(sequence) - 1)]
        light = (0, 0, 1, 1, 1, 0, 0, -1, -1, -1, 0, 0, 1, 1, 0, 0)[frame % 16]
        for row, shades, tones in zip(
            drawing["art"].splitlines(),
            drawing["shade"].splitlines(),
            drawing["tone"].splitlines(),
            strict=True,
        ):
            picture.append("  ")
            for dot, depth, tone in zip(row.ljust(len(shades)), shades, tones, strict=True):
                level = int(depth) + (light if pose != "idle" and tone in "345" else 0)
                picture.append(
                    dot,
                    colours[int(tone)][min(7, max(0, level))] if dot != " " else None,
                )
            picture.append("\n")
        return picture


@cache
def habitats() -> dict[str, Habitat]:
    """Load the small bundled forest once, after a mini is opened"""
    path = files("uq_minis.assets").joinpath("terminal/forest.toml")
    return {
        name: Habitat(animal=name, **values)
        for name, values in tomllib.loads(path.read_text()).items()
    }


@lru_cache(maxsize=6)
def poses(animal: str) -> dict[str, list[dict[str, str]]]:
    """Load an animal's movement only when its portrait is shown"""
    path = files("uq_minis.assets").joinpath(f"terminal/{animal}.toml")
    return tomllib.loads(path.read_text())
