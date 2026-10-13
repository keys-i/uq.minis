"""Shared dot sculptures and bounded terminal image previews"""

import gzip
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache, lru_cache
from importlib.resources import files

from rich.text import Text

FPS = 12


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
        """Let each routine finish at its baked movement cadence"""
        return len(poses(self.animal)[pose]) / FPS

    def region(
        self, frame: int, pose: str, x: int, y: int, size: tuple[int, int] = (40, 16)
    ) -> str | None:
        """Keep pointer targets attached to the animal and object as they move"""
        rows = self.drawing(frame, pose, size)["hit"].splitlines()
        if 0 <= y < len(rows) and 2 <= x < len(rows[y]) + 2:
            return {"1": "ears", "2": "pet", "3": "object"}.get(rows[y][x - 2])
        return None

    @lru_cache(maxsize=144)
    def drawing(
        self, frame: int = 0, pose: str = "idle", size: tuple[int, int] = (40, 16)
    ) -> dict[str, str]:
        """Keep the detailed sculpture and its compact pointer map in the same frame"""
        drawing = {"art": self.art, "shade": self.shade, "tone": self.tone, "hit": self.hit}
        if pose != "idle":
            sequence = poses(self.animal)[pose]
            drawing = sequence[min(frame, len(sequence) - 1)]
        if size == (64, 24):
            return drawing
        source = {key: value.splitlines() for key, value in drawing.items()}
        width, height = len(source["shade"][0]), len(source["shade"])
        columns, lines = size
        bits = ((1, 8), (2, 16), (4, 32), (64, 128))
        result: dict[str, list[str]] = {key: [] for key in source}
        for y in range(lines):
            rows: dict[str, list[str]] = {key: [] for key in source}
            for x in range(columns):
                dots = 0
                samples: list[tuple[int, int]] = []
                for dy in range(4):
                    sy = int((y * 4 + dy + 0.5) * height / lines)
                    for dx in range(2):
                        sx = int((x * 2 + dx + 0.5) * width / columns)
                        row = source["art"][sy // 4]
                        glyph = row[sx // 2] if sx // 2 < len(row) else " "
                        if (
                            0x2800 <= ord(glyph) <= 0x28FF
                            and (ord(glyph) - 0x2800) & bits[sy % 4][sx % 2]
                        ):
                            dots |= bits[dy][dx]
                            samples.append((sy // 4, sx // 2))
                rows["art"].append(chr(0x2800 + dots) if dots else " ")
                for key in ("shade", "tone", "hit"):
                    values = [source[key][yy][xx] for yy, xx in samples]
                    rows[key].append(
                        str(round(sum(map(int, values)) / len(values)))
                        if key == "shade" and values
                        else "7"
                        if key == "tone" and "7" in values
                        else max(sorted(set(values)), key=values.count)
                        if values
                        else "0"
                    )
            for key, row in rows.items():
                result[key].append("".join(row))
        return {key: "\n".join(rows) for key, rows in result.items()}

    @cache
    def colours(self) -> tuple[tuple[str, ...], ...]:
        """Keep fur, markings, foliage and water distinct under the same light"""
        palettes: list[tuple[str, ...]] = []
        flags = tuple(dict.fromkeys(self.flag.replace("|", " ").split())) or (self.primary,)
        for material, colour in enumerate((
            self.fur,
            "#f8f1e3",
            "#19212d",
            self.leaf,
            self.water,
            self.flower,
            self.ground,
            "#fffaf1",
        )):
            flag = flags[material % len(flags)]
            if material in (3, 4, 5, 6):
                colour = blend(colour, flag, 0.24 if material != 6 else 0.12)
            light = "#" + "".join(
                f"{min(255, round(int(colour[i : i + 2], 16) * 1.25 + 16)):02x}" for i in (1, 3, 5)
            )
            if material != 2:
                light = blend(light, flag, 0.20 if material < 3 else 0.40)
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
    def picture(self, frame: int = 0, pose: str = "idle", size: tuple[int, int] = (40, 16)) -> Text:
        """Draw a shaded movement frame from the mini's bundled sculpture"""
        colours = self.colours()
        picture = Text()
        drawing = self.drawing(frame, pose, size)
        for row, shades, tones in zip(
            drawing["art"].splitlines(),
            drawing["shade"].splitlines(),
            drawing["tone"].splitlines(),
            strict=True,
        ):
            picture.append("  ")
            for dot, depth, tone in zip(row.ljust(len(shades)), shades, tones, strict=True):
                picture.append(
                    dot,
                    colours[int(tone)][int(depth)] if dot != " " else None,
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
    path = files("uq_minis.assets").joinpath(f"terminal/{animal}.toml.gz")
    return tomllib.loads(gzip.decompress(path.read_bytes()).decode())
