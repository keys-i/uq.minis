"""Shared dot sculptures and bounded terminal image previews

Bundled animal, flag and habitat data supplies both terminal previews and
browser artwork. Rendering is bounded by the available terminal dimensions
and does not require a network request or an image-library import at startup
"""

import gzip
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cache, lru_cache
from importlib.resources import files
from math import floor

from rich.text import Text

FPS = 24
COLOURS = {
    "accent": "#ffb66f",
    "success": "#6cddb0",
    "warning": "#f4d66b",
    "error": "#ff879a",
    "ink": "#20262d",
    "peach": "#ffb68d",
    "mint": "#83dfcf",
    "surface": "#262c34",
    "text": "#f1eee9",
}
RESIDENTS = {
    "planny": "otter",
    "buzzy": "huia",
    "scrappy": "bee",
    "clubby": "otter",
    "event": "mink",
    "timey": "quoll",
    "auth": "saola",
    "agent": "huia",
}


@dataclass(frozen=True, slots=True)
class Preview:
    """A terminal image, text alternative and optional size-aware renderers

    ``picture`` supplies the initial still and ``description`` remains readable
    without colour or images; ``render`` redraws for a panel size and ``live``
    adds time-dependent effects without changing the selected value
    """

    picture: Text
    description: str
    render: Callable[[int, int], Text] | None = None
    live: Callable[[int, int, float], Text] | None = None
    _sizes: dict[tuple[int, int], Text] = field(default_factory=dict, compare=False, repr=False)
    _frames: dict[tuple[int, int, int], Text] = field(
        default_factory=dict, compare=False, repr=False
    )

    def fit(self, size: tuple[int, int], *, elapsed: float | None = None) -> Text:
        """Render to a (column, row) budget without refetching the source

        Cache at most three still sizes or one live frame quantised to 8 Hz
        Omit ``elapsed`` for a still preview, including when motion is paused
        A preview without a renderer returns its original Rich text
        """
        if self.live and elapsed is not None:
            key = (*size, int(elapsed * 8))
            if key not in self._frames:
                self._frames.clear()
                self._frames[key] = self.live(*size, key[2] / 8)
            return self._frames[key]
        if self.render is None:
            return self.picture
        if size not in self._sizes:
            if len(self._sizes) == 3:
                self._sizes.pop(next(iter(self._sizes)))
            self._sizes[size] = self.render(*size)
        return self._sizes[size]


def blend(first: str, second: str, amount: float) -> str:
    """Mix trusted RGB theme colours without an extra rendering dependency"""
    channels = [
        round(int(first[i : i + 2], 16) * (1 - amount) + int(second[i : i + 2], 16) * amount)
        for i in (1, 3, 5)
    ]
    return "#" + "".join(f"{value:02x}" for value in channels)


@dataclass(frozen=True, slots=True)
class Flag:
    """An offline colour map preserving a national flag's spatial layout"""

    code: str
    ratio: float
    colours: tuple[str, ...]
    rows: tuple[str, ...]

    def colour(self, x: float, y: float, *, readable: bool = False) -> str:
        """Sample the actual flag layout with optional foreground contrast"""
        column = min(len(self.rows[0]) - 1, max(0, floor(x * len(self.rows[0]))))
        row = min(len(self.rows) - 1, max(0, floor(y * len(self.rows))))
        colour = self.colours[int(self.rows[row][column], 16)]
        if readable:
            brightest = max(int(colour[i : i + 2], 16) for i in (1, 3, 5))
            colour = blend(colour, "#ffffff", max(0, (160 - brightest) / 255))
        return colour

    @cache
    def picture(self) -> Text:
        """Use twelve mascot-sized dot rows, rounding proportions to the nearest dot"""
        width = max(1, round(12 * self.ratio))
        result = Text()
        bits = ((1, 8), (2, 16), (4, 32), (64, 128))
        for y in (0, 4, 8):
            if y:
                result.append("\n")
            for x in range(0, width, 2):
                colours = [
                    self.colour((x + column + 0.5) / width, (y + row + 0.5) / 12)
                    if x + column < width
                    else "#111116"
                    for row in range(4)
                    for column in range(2)
                ]
                visible = [colour for colour in colours if colour != "#111116"]
                if not visible:
                    result.append(" ")
                    continue
                # Keep every coloured dot; only transparent outlines leave gaps
                colours_by_area = sorted(
                    set(visible), key=lambda value: (-visible.count(value), value)
                )
                colour = colours_by_area[0]
                dots = sum(
                    bits[index // 2][index % 2]
                    for index, pixel in enumerate(colours)
                    if pixel != "#111116"
                )
                result.append(chr(0x2800 + dots), colour)
        return result


@cache
def flags() -> dict[str, Flag]:
    """Load small bundled flag maps without Pillow or a network request"""
    path = files("uq_minis.assets").joinpath("terminal/flags.toml")
    return {
        country: Flag(data["code"], data["ratio"], tuple(data["colours"]), tuple(data["rows"]))
        for country, data in tomllib.loads(path.read_text()).items()
    }


def image(rows: Sequence[Sequence[tuple[int, int, int]]], description: str) -> Preview:
    """Draw bounded RGB rows with two pixels per terminal cell"""
    if (
        not rows
        or not 0 < len(rows[0]) <= 512
        or len(rows) > 512
        or any(len(row) != len(rows[0]) for row in rows)
        or any(
            len(pixel) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in pixel)
            for row in rows
            for pixel in row
        )
    ):
        raise ValueError("Terminal previews must fit within 512 × 512 pixels")
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

    @lru_cache(maxsize=144)
    def countries(self, width: int = 80, *, compact: bool = False) -> Text:
        """Place static twelve-dot flags beside status, country and habitat"""
        aliases = {
            "Western Australia": "Australia",
            "Northern Australia": "Australia",
            "Torres Strait / Australia": "Australia",
            "Christmas Island / Australia": "Australia",
            "Tasmania / Australia": "Australia",
            "Tasmania": "Australia",
            "Aotearoa / New Zealand": "New Zealand",
        }
        pictures: list[list[Text]] = []
        name = Text()
        for index, country in enumerate(self.country.split(" · ")):
            if index:
                name.append(" · ", self.secondary)
            flag = flags().get(aliases.get(country, country))
            for column, letter in enumerate(country):
                x = (column + 0.5) / len(country)
                name.append(letter, flag.colour(x, 0.5, readable=True) if flag else self.water)
            if flag:
                pictures.append(list(flag.picture().split("\n")))
        if compact:
            return name
        if not pictures:
            return (
                Text(self.status + "\n", self.secondary) + name + Text("\n" + self.place, self.leaf)
            )
        flag_width = sum(rows[0].cell_len for rows in pictures) + len(pictures) - 1
        label_width = max(1, width - flag_width - 2)
        status = Text(self.status, self.secondary)
        place = Text(self.place, self.leaf)
        status.truncate(label_width, overflow="ellipsis")
        name.truncate(label_width, overflow="ellipsis")
        place.truncate(label_width, overflow="ellipsis")
        result = Text()
        for y, label in enumerate((status, name, place)):
            if y:
                result.append("\n")
            for index, rows in enumerate(pictures):
                if index:
                    result.append(" ")
                result.append(rows[y])
            result.append("  ")
            result.append(label)
        return result

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
        source = {key: value.splitlines() for key, value in drawing.items()}
        width, height = len(source["shade"][0]), len(source["shade"])
        if size == (width, height):
            return drawing
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
                    if key == "hit":
                        values = [value for value in values if value != "0"] or values
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
