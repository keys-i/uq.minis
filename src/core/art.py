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


def image(rows: Sequence[Sequence[tuple[int, int, int]]], description: str) -> Preview:
    """Draw bounded RGB rows with two pixels per terminal cell"""
    if (
        not rows
        or not 0 < len(rows[0]) <= 26
        or len(rows) > 18
        or any(len(row) != len(rows[0]) for row in rows)
        or any(
            len(pixel) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in pixel)
            for row in rows
            for pixel in row
        )
    ):
        raise ValueError("Terminal previews must fit within 26 × 18 pixels")
    picture = Text()
    for top in range(0, len(rows), 2):
        for x, colour in enumerate(rows[top]):
            fg = "#" + "".join(f"{channel:02x}" for channel in colour)
            bottom = rows[min(top + 1, len(rows) - 1)][x]
            bg = "#" + "".join(f"{channel:02x}" for channel in bottom)
            picture.append("▀", f"{fg} on {bg}")
        picture.append("\n")
    caption = Text(description)
    caption.truncate(26, overflow="ellipsis")
    picture.append(caption)
    return Preview(picture, description)


@dataclass(frozen=True, slots=True)
class Habitat:
    """A mini's animal, useful object and colours within the shared forest"""

    animal: str
    object: str
    primary: str
    secondary: str
    idle: str
    art: str
    shade: str

    def styles(self) -> dict[str, str]:
        """Keep headings, choices and progress in the same visual family"""
        return {
            "accent": self.primary,
            "bar.complete": self.primary,
            "bar.finished": self.secondary,
            "bar.pulse": self.primary,
        }

    @lru_cache(maxsize=144)
    def picture(self, frame: int = 0, pose: str = "idle") -> Text:
        """Draw a shaded movement frame from the mini's bundled sculpture"""
        stops = ("#53647a", self.primary, "#f1eee9")
        colours = []
        for level in range(8):
            position = level / 7 * 2
            lower = min(int(position), 1)
            blend = position - lower
            channels = [
                round(
                    int(stops[lower][i : i + 2], 16) * (1 - blend)
                    + int(stops[lower + 1][i : i + 2], 16) * blend
                )
                for i in (1, 3, 5)
            ]
            colours.append("#" + "".join(f"{value:02x}" for value in channels))
        picture = Text()
        drawing = {"art": self.art, "shade": self.shade}
        if pose != "idle":
            sequence = _poses(self.animal)[pose]
            drawing = sequence[min(frame, len(sequence) - 1)]
        for row, shades in zip(
            drawing["art"].splitlines(),
            drawing["shade"].splitlines(),
            strict=True,
        ):
            picture.append("  ")
            for dot, depth in zip(row.ljust(len(shades)), shades, strict=True):
                picture.append(dot, colours[int(depth)] if dot != " " else None)
            picture.append("\n")
        return picture


@cache
def _habitats() -> dict[str, Habitat]:
    """Load the small bundled forest once, after a mini is opened"""
    path = files("uq_minis.assets").joinpath("terminal/forest.toml")
    return {
        name: Habitat(animal=name, **values)
        for name, values in tomllib.loads(path.read_text()).items()
    }


@lru_cache(maxsize=6)
def _poses(animal: str) -> dict:
    """Load an animal's movement only when its portrait is shown"""
    path = files("uq_minis.assets").joinpath(f"terminal/{animal}.toml")
    return tomllib.loads(path.read_text())
