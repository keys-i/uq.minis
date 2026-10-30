"""Small deterministic theme scenes shared by live previews and streamed exports

A render owns one theme scene and bounded ambient events, indexed by
elapsed time so seeking is deterministic. The scene draws panel-sized
layers rather than retaining full video frames
"""

import math
import random
from collections.abc import Sequence
from typing import cast

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from uq_minis.core.art import blend

Point = tuple[float, float]
Colour = str | tuple[int, int, int, int]


class Scene:
    """Keep one panel, digit mask and bounded set of ambient events per render

    Coordinates use a 540 × 234 design plane and scale to the actual overlay
    Randomness is seeded once, so seeking, previewing and exporting agree
    Digits stay fixed while their material, growing edges and surroundings move
    """

    def __init__(
        self,
        kind: str,
        size: tuple[int, int],
        accent: str,
        identity: str,
        *,
        seconds: int,
        start_gap: int = 0,
    ) -> None:
        """Set up reusable material and event placement without background activity"""
        self.kind, self.size, self.accent = kind, size, accent
        self.seconds, self.start_gap = seconds, start_gap
        self.sx, self.sy = size[0] / 540, size[1] / 234
        seed = random.Random(f"{kind}:{identity}")
        self.events = tuple((seed.uniform(0, 30), seed.uniform(19, 37)) for _ in range(6))
        self.stone = tuple(
            (seed.randrange(12, 526), seed.randrange(12, 222), seed.choice((-14, 12)))
            for _ in range(45)
        )
        self.cracks = (
            tuple(
                tuple(
                    (x + step * length / 6, y + seed.uniform(-5, 5) + step * 1.7)
                    for step in range(7)
                )
                for x, y, length in self.stone[:20]
            )
            if kind == "temple-run"
            else ()
        )
        self.shards: list[tuple[Image.Image, tuple[int, int, int, int], float, float, float]] = []
        self.mask = Image.new("L", size)
        self.material = Image.new("RGBA", size)
        self.previous: Image.Image | None = None
        self.outline = Image.new("RGBA", size)
        self.changed = 0.0
        self.layer = Image.new("RGBA", size)
        self.draw = ImageDraw.Draw(self.layer)

    def points(self, points: Sequence[Point]) -> list[Point]:
        """Map design coordinates to the current panel resolution"""
        return [(x * self.sx, y * self.sy) for x, y in points]

    def line(self, points: Sequence[Point], colour: Colour, width: float = 1) -> None:
        """Draw a scaled stroke on the current layer"""
        self.draw.line(self.points(points), fill=colour, width=max(1, round(width * self.sx)))

    def box(self, bounds: tuple[float, float, float, float], colour: Colour) -> None:
        """Draw a scaled rectangular patch"""
        self.draw.rectangle(
            self.points([(bounds[0], bounds[1]), (bounds[2], bounds[3])]), fill=colour
        )

    def poly(self, points: Sequence[Point], colour: Colour) -> None:
        """Draw a scaled silhouette"""
        self.draw.polygon(self.points(points), fill=colour)

    def oval(self, bounds: tuple[float, float, float, float], colour: Colour) -> None:
        """Draw a scaled reflection or rounded detail"""
        self.draw.ellipse(
            self.points([(bounds[0], bounds[1]), (bounds[2], bounds[3])]), fill=colour
        )

    def panel(self) -> Image.Image:
        """Build a quiet world surface before adding labels and countdown digits"""
        if self.kind == "minecraft":
            self.box((62, 190, 478, 196), "#111111")
            self.box((64, 192, 476, 194), "#395B16")
            for index in range(9):
                x = 116 + index * 34
                self.box((x, 203, x + 32, 233), "#161616")
                self.box((x + 1, 204, x + 31, 232), "#777777")
                self.box((x + 3, 206, x + 29, 230), (24, 24, 24, 180))
                self.line([(x + 4, 229), (x + 28, 229), (x + 28, 207)], "#AAAAAA")
                if index in {0, 1, 2}:
                    self.sprite(
                        (
                            "00001110",
                            "00011111",
                            "00121101",
                            "00021000",
                            "00210000",
                            "02100000",
                            "21000000",
                            "10000000",
                        ),
                        {"1": "#704E2A", "2": ("#58D8CB", "#DFDFDF", "#B6A178")[index]},
                        x + 8,
                        209,
                        2,
                    )
                elif index in {3, 4, 5}:
                    self.box(
                        (x + 8, 211, x + 23, 226), ("#9A633E", "#858585", "#BFA578")[index - 3]
                    )
                    for dx, dy in ((2, 3), (9, 7), (4, 11)):
                        self.box((x + 8 + dx, 211 + dy, x + 11 + dx, 213 + dy), "#564638")
                elif index == 6:
                    self.sprite(
                        (
                            "0001000",
                            "0011100",
                            "0111110",
                            "1111111",
                            "1111111",
                            "0111110",
                            "0010100",
                        ),
                        {"1": "#E44536"},
                        x + 9,
                        210,
                        2,
                    )
                elif index == 7:
                    self.box((x + 15, 214, x + 18, 226), "#A3793A")
                    self.box((x + 13, 209, x + 20, 216), "#FFBE45")
                    self.box((x + 15, 208, x + 18, 212), "#FFF1B0")
        elif self.kind == "subway-surfers":
            self.poly(
                [
                    (24, 166),
                    (92, 145),
                    (67, 168),
                    (489, 148),
                    (516, 167),
                    (445, 181),
                    (470, 188),
                    (39, 194),
                    (78, 180),
                ],
                "#143957",
            )
            for x, y, _ in self.stone[:18]:
                self.oval((x, 163 + y % 37, x + 2, 165 + y % 37), "#3BAAB4")
            self.line([(65, 201), (390, 192)], "#F5F0D9", 2)
            self.line([(89, 208), (344, 201)], "#EE6B79", 2)
        elif self.kind == "neon":
            for side in (0, 1):
                x, direction = (8, 1) if not side else (532, -1)
                self.line([(x + 36 * direction, 29), (x, 29), (x, 88)], "#123445", 6)
                self.line([(x + 36 * direction, 29), (x, 29), (x, 88)], self.accent, 1.5)
                self.line([(x, 151), (x, 198), (x + 64 * direction, 198)], self.accent, 1.5)
            for index in range(3):
                self.line([(192 + index * 51, 213), (211 + index * 51, 213)], "#2B6875", 2)
        elif self.kind in {"super-mario", "minions", "sonic", "pac-man"}:
            self.arcade_panel()
        elif self.kind == "glass":
            self.draw.rounded_rectangle(
                self.points([(1, 1), (539, 233)]), radius=27 * self.sx, fill=(16, 31, 47, 85)
            )
            self.draw.rounded_rectangle(
                self.points([(2, 2), (538, 232)]),
                radius=26 * self.sx,
                outline=(230, 246, 255, 90),
                width=max(1, round(self.sx)),
            )
            self.box((34, 184, 496, 186), (217, 235, 255, 30))
            for inset, alpha in ((4, 85), (6, 40), (10, 22)):
                self.draw.rounded_rectangle(
                    self.points([(inset, inset), (540 - inset, 234 - inset)]),
                    radius=max(1, 27 - inset) * self.sx,
                    outline=(225, 244, 255, alpha),
                    width=max(1, round(self.sx)),
                )
            self.line([(27, 5), (505, 5), (521, 13)], (255, 253, 238, 140), 1.5)
            self.line([(20, 218), (33, 227), (505, 227)], (148, 182, 210, 90), 2)
            self.line([(8, 38), (8, 175)], (238, 250, 255, 70), 2)
        return self.layer.copy()

    def bevel(
        self, bounds: tuple[float, float, float, float], colour: str, radius: float = 5
    ) -> None:
        """Light a solid game material from the upper left"""
        x, y, right, bottom = bounds
        self.draw.rounded_rectangle(
            self.points([(x, y), (right, bottom)]),
            radius=radius * self.sx,
            fill=blend(colour, "#080D23", 0.6),
        )
        self.draw.rounded_rectangle(
            self.points([(x + 1, y + 1), (right - 2, bottom - 3)]),
            radius=max(0, radius - 1) * self.sx,
            fill=colour,
        )
        self.line(
            [(x + radius, y + 2), (right - radius, y + 2)], blend(colour, "#FFF8DC", 0.5), 1.2
        )

    def sprite(
        self, rows: Sequence[str], palette: dict[str, str], x: float, y: float, pixel: float
    ) -> None:
        """Keep HUD icons on a crisp pixel grid at every output size"""
        for row, cells in enumerate(rows):
            for column, cell in enumerate(cells):
                if cell in palette:
                    self.box(
                        (
                            x + column * pixel,
                            y + row * pixel,
                            x + (column + 1) * pixel - 0.2,
                            y + (row + 1) * pixel - 0.2,
                        ),
                        palette[cell],
                    )

    def ring(self, x: float, y: float, radius: float, colour: str, width: float) -> None:
        """Stroke an open ring without painting its transparent centre"""
        self.draw.ellipse(
            self.points([(x - radius, y - radius), (x + radius, y + radius)]),
            outline=colour,
            width=max(1, round(width * self.sx)),
        )

    def arcade_panel(self) -> None:
        """Compose recognisable game objects around open space for the countdown"""
        if self.kind == "super-mario":
            for x, y in ((32, 30), (70, 30), (438, 20), (476, 20), (400, 3)):
                self.box((x, y, x + 30, y + 30), "#753421")
                self.box((x + 2, y + 2, x + 28, y + 27), "#EAA03B")
                self.line([(x + 4, y + 4), (x + 26, y + 4)], "#FFE99A", 2)
                self.sprite(
                    ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
                    {"1": "#FFF5BD"},
                    x + 10,
                    y + 5,
                    2,
                )
            for left, right in ((18, 143), (378, 521)):
                for x in range(left, right, 25):
                    self.box((x, 221, min(x + 24, right), 233), "#A8492B")
                    self.box((x + 1, 222, min(x + 22, right), 224), "#F1A36B")
                self.line([(left, 220), (right, 220)], "#FFCE85", 2)
            self.box((29, 179, 61, 219), "#167444")
            self.box((24, 175, 66, 185), "#124F37")
            self.box((27, 176, 63, 182), "#63BD5C")
            self.box((33, 186, 38, 217), "#A1DB75")
            for level in range(3):
                for column in range(3 - level):
                    x, y = 436 + column * 25, 196 - level * 25
                    self.box((x, y, x + 24, y + 24), "#A7502C")
                    self.box((x + 2, y + 2, x + 21, y + 21), "#DE9A52")
                    self.line([(x + 3, y + 3), (x + 20, y + 3)], "#FFE2A3", 2)
        elif self.kind == "minions":
            for x in (151, 389):
                self.oval((x - 96, 13, x + 96, 207), "#202A37")
                self.oval((x - 91, 16, x + 91, 200), "#AAB7C0")
                self.oval((x - 83, 24, x + 83, 192), "#475566")
                self.oval((x - 78, 28, x + 78, 185), (14, 28, 44, 220))
                self.draw.arc(
                    self.points([(x - 88, 19), (x + 88, 197)]),
                    200,
                    325,
                    fill="#F2F2E9",
                    width=max(1, round(3 * self.sx)),
                )
                for dx in (-91, 87):
                    self.box((x + dx, 93, x + dx + 5, 120), "#D7D9CF")
            self.line([(247, 104), (293, 104)], "#353E49", 12)
            self.line([(249, 101), (291, 101)], "#AAB7C0", 3)
            self.draw.arc(
                self.points([(113, 87), (427, 234)]),
                10,
                170,
                fill="#9B6A21",
                width=max(1, round(13 * self.sx)),
            )
            self.draw.arc(
                self.points([(115, 83), (425, 230)]),
                10,
                170,
                fill="#F9D344",
                width=max(1, round(10 * self.sx)),
            )
            self.line([(120, 173), (111, 161)], "#70502B", 4)
        elif self.kind == "sonic":
            for side in (-1, 1):
                self.poly(
                    [
                        (270 + side * 92, 102),
                        (270 + side * 234, 51),
                        (270 + side * 201, 93),
                        (270 + side * 242, 78),
                        (270 + side * 200, 118),
                        (270 + side * 232, 109),
                        (270 + side * 174, 151),
                        (270 + side * 88, 146),
                    ],
                    "#164B91",
                )
                self.poly(
                    [
                        (270 + side * 102, 105),
                        (270 + side * 212, 68),
                        (270 + side * 176, 105),
                        (270 + side * 209, 91),
                        (270 + side * 170, 124),
                        (270 + side * 194, 116),
                        (270 + side * 166, 137),
                        (270 + side * 105, 138),
                    ],
                    "#EDF6E9",
                )
            for radius, colour, width in (
                (109, "#784922", 12),
                (105, "#F3BC35", 12),
                (101, "#FFEB88", 3),
                (94, "#BA7924", 2),
            ):
                self.ring(270, 116, radius, colour, width)
            self.oval((181, 31, 359, 201), (8, 33, 72, 150))
        else:
            for points in (
                [(58, 48), (32, 48), (32, 17), (168, 17), (168, 35), (137, 35)],
                [(382, 31), (382, 12), (505, 12), (505, 55), (475, 55)],
                [(21, 153), (21, 194), (45, 194)],
                [(519, 150), (519, 195), (498, 195)],
            ):
                self.line(points, "#1845CA", 5)
                self.line(points, "#78A4FF", 1)

    def arcade(self, t: float) -> None:
        """Play each world's own small sequence around a stable, readable countdown"""
        remaining = self.remaining(t)
        urgency = 1 + 0.5 * max(0, 1 - remaining / 10)
        if self.kind == "super-mario":
            for index in range(5):
                if index >= math.ceil(5 * remaining / max(1, self.seconds)):
                    continue
                x = 87 + index * 91
                life = (t * urgency + index * 0.8) % 4
                jump = math.sin(min(1, life / 0.65) * math.pi) * 12 if life < 0.65 else 0
                width = max(1, 4 * abs(math.cos(t * 3 + index)))
                self.oval((x - width, 208 - jump - 6, x + width, 208 - jump + 6), "#BB792A")
                self.oval((x - width + 0.7, 202 - jump, x + width - 0.7, 213 - jump), "#FFE17B")
                if width > 2:
                    self.line([(x, 205 - jump), (x, 210 - jump)], "#C18B31")
                if life < 0.45:
                    for direction in (-1, 1):
                        self.line(
                            [
                                (x + direction * (7 + life * 9), 205 - jump),
                                (x + direction * (9 + life * 11), 203 - jump),
                            ],
                            (255, 229, 153, round(210 * (1 - life / 0.45))),
                        )
            x = 25 + (t * 28) % 490
            stride = math.sin(t * 8) * 2
            self.bevel((x - 5, 207, x + 7, 218), "#F4D8AE", 4)
            self.oval((x - 10, 198, x + 12, 212), "#D74D40")
            for dx in (-4, 5):
                self.oval((x + dx - 2, 200, x + dx + 2, 203), "#FFF1C8")
            self.box((x - 2, 211, x - 0.5, 214), "#302D32")
            self.box((x + 3, 211, x + 4.5, 214), "#302D32")
            self.oval((x - 8 - stride, 217, x - 1 - stride, 220), "#684638")
            self.oval((x + 3 + stride, 217, x + 10 + stride, 220), "#684638")
        elif self.kind == "minions":
            x = 270 + math.sin(t * 1.3) * 11
            y = 199 + math.sin(t * 2) * 3
            self.line([(x - 12, y + 9), (x - 26, y + 3 + math.sin(t * 4) * 5)], "#F9D344", 4)
            self.line([(x + 12, y + 9), (x + 26, y + 3 - math.sin(t * 4) * 5)], "#F9D344", 4)
            self.oval((x - 13, y - 11, x + 13, y + 22), "#F9D344")
            self.box((x - 10, y + 12, x + 10, y + 22), "#376EAA")
            self.line([(x - 13, y), (x + 13, y)], "#273141", 4)
            self.oval((x - 9, y - 9, x + 9, y + 9), "#BDCAD1")
            self.oval((x - 6, y - 6, x + 6, y + 6), "#FFF3D5")
            if (t + 1.7) % 5.4 > 0.2:
                look = math.sin(t) * 2
                self.oval((x - 3 + look, y - 3, x + 3 + look, y + 3), "#735132")
                self.oval((x - 1 + look, y - 2, x + 1 + look, y + 2), "#202834")
            else:
                self.line([(x - 5, y), (x + 5, y)], "#735132", 2)
            self.line([(x - 3, y + 12), (x, y + 14), (x + 4, y + 11)], "#9B6A21")
            for dx in (-7, 5):
                self.oval((x + dx - 3, y + 21, x + dx + 4, y + 24), "#202834")
        elif self.kind == "sonic":
            self.draw.arc(
                self.points([(162, 8), (378, 224)]),
                -90,
                -90 + max(0.01, 360 * remaining / max(1, self.seconds)),
                fill="#FFF3B0",
                width=max(1, round(3 * self.sx)),
            )
            x = 28 + (t * 83 * urgency) % 478
            jump = max(0, math.sin(t * 2.2)) ** 5 * 10
            for index in range(3):
                self.line(
                    [
                        (max(25, x - 35 - index * 12), 205 + index * 4 - jump),
                        (x - 10, 205 + index * 4 - jump),
                    ],
                    (100, 209, 248, 150 - index * 35),
                    1.5,
                )
            self.oval((x - 8, 198 - jump, x + 8, 214 - jump), "#378DDE")
            self.poly(
                [
                    (x - 3, 199 - jump),
                    (x - 12, 198 - jump),
                    (x - 8, 204 - jump),
                    (x - 15, 205 - jump),
                    (x - 8, 208 - jump),
                    (x - 11, 212 - jump),
                    (x, 211 - jump),
                ],
                "#205CB1",
            )
            self.draw.arc(
                self.points([(x - 6, 200 - jump), (x + 6, 212 - jump)]),
                t * 500 % 360,
                t * 500 % 360 + 190,
                fill="#A7E6F3",
                width=max(1, round(1.3 * self.sx)),
            )
            self.oval((x - 8, 214 - jump, x + 6, 218 - jump), "#E86653")
            self.line([(x - 2, 214 - jump), (x + 1, 217 - jump)], "#FFF8D9", 2)
            for index in range(6):
                ring = 78 + index * 76
                radius = max(1, abs(math.cos(t * 3 + index)) * 4)
                self.oval((ring - radius, 18, ring + radius, 30), "#FAD878")
                if radius > 2:
                    self.oval((ring - radius + 1.6, 20, ring + radius - 1.6, 28), "#327BC4")
        else:
            powered = remaining <= min(8, self.seconds / 3)
            x = 57 + (t * 38 * urgency) % 426
            for dot in range(61, 480, 18):
                if dot > x + 10:
                    self.oval((dot - 1, 207, dot + 1, 209), "#F5D5AA")
            if t % 16 < 11:
                self.oval((479, 204, 485, 210), "#FFE6AB")
            self.oval((x - 8, 199, x + 8, 215), "#FFE37A")
            mouth = 1 + abs(math.sin(t * 9)) * 6
            self.poly([(x, 207), (x + 9, 207 - mouth), (x + 9, 207 + mouth)], (0, 0, 0, 0))
            self.oval((x - 1, 201, x + 1, 203), "#7C6238")
            for index, colour in enumerate(("#E7656A", "#EFA5C9", "#78D4E4", "#F2B16A")):
                gx = 56 + ((x - 56 - 28 - index * 25) % 428)
                if powered:
                    colour = "#426CBE" if remaining > 3 else "#B5D2EF"
                self.oval((gx - 7, 200, gx + 7, 214), colour)
                self.box((gx - 7, 207, gx + 7, 214), colour)
                for foot in (-5, 0, 5):
                    self.poly(
                        [
                            (gx + foot - 2, 215),
                            (gx + foot, 212 + 0.8 * math.sin(t * 7 + foot)),
                            (gx + foot + 2, 215),
                        ],
                        "#071027",
                    )
                for eye in (-3, 3):
                    self.oval((gx + eye - 2, 203, gx + eye + 2, 208), "#FDF2DE")
                    self.oval(
                        (
                            gx + eye + (1 if powered else -1) - 0.5,
                            204,
                            gx + eye + (1 if powered else -1) + 1,
                            207,
                        ),
                        "#233B76",
                    )

    def set(
        self, mask: Image.Image, previous: Image.Image | None = None, *, moment: float = 0
    ) -> None:
        """Prepare digit materials once per second, retaining only the previous transition"""
        self.previous = self.material if previous is not None else None
        self.changed = moment
        self.mask = mask
        self.layer = Image.new("RGBA", self.size, self.accent)
        self.draw = ImageDraw.Draw(self.layer)
        if self.kind == "temple-run":
            for y in range(234):
                self.line(
                    [(0, y), (540, y)],
                    blend(self.accent, "#61411B", 0.22 + 0.22 * math.sin(y / 23)),
                )
            for x, y, length in self.stone:
                self.line([(x, y), (x + length, y + 9), (x + length - 4, y + 16)], "#64491F")
        elif self.kind == "minecraft":
            self.box((0, 0, 540, 234), "#F1F1F1" if self.accent == "#8FDA53" else self.accent)
        elif self.kind == "subway-surfers":
            for x in range(540):
                colours = (self.accent, "#FF8269", "#F45C91", "#79E3E8", self.accent)
                segment = x / 540 * 4
                index = min(3, int(segment))
                self.line(
                    [(x, 0), (x, 234)], blend(colours[index], colours[index + 1], segment - index)
                )
            for y in (80, 83, 89):
                self.line([(0, y), (540, y)], "#FFF4D1", 1)
        elif self.kind == "neon":
            for y in range(0, 234, 4):
                self.line([(0, y), (540, y)], blend(self.accent, "#123445", 0.2))
        elif self.kind == "glass":
            for y in range(234):
                self.line(
                    [(0, y), (540, y)], blend(self.accent, "#91AFC6", 0.18 * (1 + math.cos(y / 27)))
                )
        elif self.kind in {"super-mario", "minions", "sonic", "pac-man"}:
            shade = {
                "super-mario": "#DB873A",
                "minions": "#BD8E2B",
                "sonic": "#C58A30",
                "pac-man": "#CE8A45",
            }[self.kind]
            for y in range(234):
                self.line([(0, y), (540, y)], blend(self.accent, shade, 0.12 + 0.25 * (y / 234)))
            if self.kind == "pac-man":
                self.layer.paste("#456FEF", (0, 0, *self.size))
                inset = max(3, round(3 * self.sx) * 2 + 1)
                inner = mask.filter(ImageFilter.MinFilter(inset))
                self.layer.paste("#071127", mask=inner)
                for y in range(65, 160, 11):
                    for x in range(43, 500, 11):
                        px, py = (
                            min(self.size[0] - 1, round(x * self.sx)),
                            min(self.size[1] - 1, round(y * self.sy)),
                        )
                        if cast(int, inner.getpixel((px, py))) > 200:
                            self.oval((x - 1, y - 1, x + 1, y + 1), self.accent)
            elif self.kind == "minions":
                for x, y, _ in self.stone:
                    self.line([(x, y), (x + 2, y)], "#FFF2B8")
        self.layer.putalpha(mask)
        self.material = self.layer.copy()
        self.outline = Image.new("RGBA", self.size)
        if self.kind in {
            "super-mario",
            "minions",
            "sonic",
            "pac-man",
            "minecraft",
            "subway-surfers",
        }:
            if self.kind == "subway-surfers":
                for thickness, colour in ((13, "#102B45"), (9, "#F6F1DC"), (5, "#123852")):
                    outline = Image.new("RGBA", self.size, colour)
                    outline.putalpha(
                        self.mask.filter(
                            ImageFilter.MaxFilter(max(3, round(thickness * self.sx) // 2 * 2 + 1))
                        )
                    )
                    self.outline.alpha_composite(outline)
            shadow = Image.new("RGBA", self.size, "#080F25")
            shadow.putalpha(
                ImageChops.offset(self.mask, max(1, round(2 * self.sx)), max(1, round(3 * self.sy)))
            )
            self.outline.alpha_composite(shadow)

    def minecraft(self, t: float, *, motion: bool = True) -> None:
        """Spend native HUD health and XP as time runs out, without a terrain frame"""
        fraction = self.remaining(t) / max(1, self.seconds)
        heart = ("0110110", "1222221", "1222321", "1222221", "0122210", "0012100", "0001000")
        hunger = ("0001100", "0012210", "0122210", "1222100", "1221000", "0110100", "0000110")
        for index in range(10):
            shake = round(math.sin(t * 18 + index * 3)) if motion and fraction < 0.2 else 0
            alive = index < math.ceil(10 * fraction)
            palette = {
                "1": "#160C0C",
                "2": "#E64A42" if alive else "#3A2020",
                "3": "#FFAD9D" if alive else "#3A2020",
            }
            self.sprite(heart, palette, 63 + index * 16, 169 + shake, 2)
            self.sprite(
                hunger,
                {"1": "#1E100B", "2": "#B56837" if alive else "#38261B"},
                319 + index * 16,
                169,
                2,
            )
        self.box((64, 192, 64 + 412 * fraction, 194), self.accent)
        selected = min(8, int((1 - fraction) * 9))
        x = 116 + selected * 34
        self.line(
            [(x - 1, 232), (x - 1, 202), (x + 32, 202), (x + 32, 232), (x - 1, 232)], "#ECECEC", 2
        )
        self.sprite(
            (
                "00111100",
                "01122110",
                "11222211",
                "12233221",
                "12233221",
                "11222211",
                "01122110",
                "00111100",
            ),
            {"1": "#D5A936", "2": "#608CC9", "3": "#FFF0A3"},
            397,
            209,
            2,
        )

        if motion:
            angle = t * 1.5
            self.line(
                [(405, 217), (405 + round(5 * math.sin(angle)), 217 - round(5 * math.cos(angle)))],
                "#FFF1B2",
                2,
            )

    def remaining(self, elapsed: float) -> float:
        """Use output time, including the opening gap, for every countdown reaction"""
        return max(0, self.seconds - max(0, elapsed - self.start_gap))

    def power(self, elapsed: float) -> float:
        """Spend the idol's reserve near the end and exhaust it at ten seconds"""
        if elapsed < self.start_gap:
            return 1
        return min(1, max(0, (self.remaining(elapsed) - 10) / max(10, min(90, self.seconds - 10))))

    def temple(self, t: float, *, motion: bool = True) -> None:
        """Grow, damage and repair the same stone until the idol's energy runs out"""
        power = self.power(t)
        cycle = max(0, t - self.start_gap) % 16
        repair = min(1, max(0, (cycle - 8) / 5))
        pulse = math.sin(math.pi * repair) * power
        growth = min(1, cycle / 8) * (1 - repair * power)
        stress = 1 - power
        # The source gems are bright green, so depletion must darken the artwork itself
        for x, y, rx, ry in (
            (248, 35, 7, 8),
            (293, 35, 7, 8),
            (30, 131, 13, 18),
            (510, 131, 13, 18),
        ):
            self.oval((x - rx, y - ry, x + rx, y + ry), (7, 16, 10, round(245 * stress)))
        if pulse:
            for x, y, rx, ry in (
                (248, 35, 10, 11),
                (293, 35, 10, 11),
                (30, 131, 18, 22),
                (510, 131, 18, 22),
            ):
                self.oval((x - rx, y - ry, x + rx, y + ry), (81, 255, 53, round(135 * pulse)))
            self.layer = self.layer.filter(ImageFilter.GaussianBlur(max(0.3, 3 * self.sx)))
            self.draw = ImageDraw.Draw(self.layer)
        for index, path in enumerate(self.cracks):
            damage = max(
                stress * 0.85, min(1, max(0, (cycle - index % 7) / 4)) * (1 - repair * power)
            )
            if damage <= 0:
                continue
            points = path[: max(2, round(2 + 5 * damage))]
            self.line(
                [(x + 0.8, y + 0.8) for x, y in points], (190, 175, 124, round(115 * damage)), 1.8
            )
            self.line(points, (19, 20, 12, round(230 * damage)), 1.1)
            if len(points) > 3:
                x, y = points[3]
                self.line(
                    [(x, y), (x - 5, y + 5), (x - 3, y + 9)], (18, 21, 13, round(200 * damage))
                )
            if pulse:
                index = min(len(points) - 1, round((1 - repair) * (len(points) - 1)))
                x, y = points[index]
                self.line(points[index:], (121, 255, 91, round(200 * pulse)), 1.5)
                self.oval((x - 1, y - 1, x + 1, y + 1), (216, 255, 169, round(240 * pulse)))
        for index in range(52):
            x = 57 + (index * 43) % 426
            y = (68 if index % 2 else 204) + math.sin(index * 2.7) * 6
            size = (0.6 + (index % 4) * 0.65) * (0.2 + growth + stress * 0.25)
            self.oval(
                (x - size * 2, y - size, x + size * 2, y + size), (75, 106 + index % 4 * 8, 34, 220)
            )
            self.line([(x, y), (x + size * 1.5, y - size)], "#A3AE4B")
        for side in (0, 1):
            root = 53 if not side else 487
            extent = 20 + 92 * growth
            points = [
                (root + math.sin(y / 18 + (t * 0.4 if motion else 0)) * 2, 72 + y)
                for y in range(0, round(extent), 3)
            ]
            self.line(points, "#3E5428", 1.8)
            for index, (x, y) in enumerate(points[::5]):
                direction = -1 if index % 2 else 1
                self.oval((x - 1, y - 2, x + 7, y + 1), "#728842") if direction > 0 else self.oval(
                    (x - 7, y - 2, x + 1, y + 1), "#546E30"
                )
        if not motion:
            return
        for index, (phase, period) in enumerate(self.events):
            life = (t + phase) % period / period
            x = 65 + 410 * (0.5 - 0.5 * math.cos(life * math.tau))
            y = (69 if index % 2 else 207) + 3 * math.sin(x / 29 + index)
            feet = math.sin(t * 13 + index) * 1.5
            for offset in (-2, 0, 2):
                self.line(
                    [(x - 4, y + offset + feet), (x, y + offset), (x + 4, y + offset - feet)],
                    "#1B2415",
                    0.7,
                )
            self.oval((x - 2, y - 3, x + 2, y + 2), "#17271C")
            self.oval((x - 1, y - 4.5, x + 1, y - 2), "#473F29")
            self.line([(x, y - 2), (x, y + 1)], "#74914B", 0.7)
            if index % 3 == 1:
                self.oval((x - 2.2, y + 2, x + 2.2, y + 4.8), "#4B3826")
            elif index % 3 == 2:
                self.line([(x - 1, y - 4), (x - 3, y - 7)], "#24371D", 0.7)
                self.line([(x + 1, y - 4), (x + 3, y - 7)], "#24371D", 0.7)

    def fracture(self, canvas: Image.Image, elapsed: float, *, motion: bool) -> Image.Image:
        """Split the actual artwork into interlocking rock pieces, then apply gravity"""
        age = 5 * (1 - self.remaining(elapsed) / min(5, self.seconds))
        if elapsed < self.start_gap:
            return canvas
        if age <= 0:
            return canvas
        if not self.shards:
            seed = random.Random("temple-rock")
            sites = [
                (x * 67.5 + seed.uniform(12, 55), y * 39 + seed.uniform(8, 31))
                for y in range(6)
                for x in range(8)
            ]
            for cx, cy in sites:
                polygon: list[Point] = [(0, 0), (540, 0), (540, 234), (0, 234)]
                for ox, oy in sites:
                    if (cx, cy) == (ox, oy):
                        continue
                    nx, ny = ox - cx, oy - cy
                    limit = (ox * ox + oy * oy - cx * cx - cy * cy) / 2
                    clipped: list[Point] = []
                    for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True):
                        da, db = a[0] * nx + a[1] * ny - limit, b[0] * nx + b[1] * ny - limit
                        if da <= 0:
                            clipped.append(a)
                        if (da <= 0) != (db <= 0):
                            ratio = da / (da - db)
                            clipped.append((
                                a[0] + ratio * (b[0] - a[0]),
                                a[1] + ratio * (b[1] - a[1]),
                            ))
                    polygon = clipped
                    if not polygon:
                        break
                if not polygon:
                    continue
                points = self.points(polygon)
                bounds = (
                    max(0, math.floor(min(x for x, _ in points))),
                    max(0, math.floor(min(y for _, y in points))),
                    min(self.size[0], math.ceil(max(x for x, _ in points)) + 1),
                    min(self.size[1], math.ceil(max(y for _, y in points)) + 1),
                )
                mask = Image.new("L", (bounds[2] - bounds[0], bounds[3] - bounds[1]))
                ImageDraw.Draw(mask).polygon(
                    [(x - bounds[0], y - bounds[1]) for x, y in points], fill=255
                )
                release = (
                    0.2 + min(3.1, min(cx, 540 - cx, cy, 234 - cy) / 31) + seed.uniform(0, 0.55)
                )
                self.shards.append((
                    mask,
                    bounds,
                    release,
                    seed.uniform(-14, 14),
                    seed.uniform(-24, 24),
                ))
        result = Image.new("RGBA", self.size)
        for mask, bounds, release, drift, spin in self.shards:
            falling = max(0, age - release)
            piece = canvas.crop(bounds)
            piece.putalpha(ImageChops.multiply(piece.getchannel("A"), mask))
            left, top = bounds[:2]
            if falling:
                # Acceleration and rotation begin at each fracture, with no per-frame randomness
                turn = spin * falling if motion else 0
                rotated = piece.rotate(turn, Image.Resampling.BICUBIC, expand=True)  # pyright: ignore[reportUnknownMemberType]
                left += round(drift * falling * self.sx) - (rotated.width - piece.width) // 2
                top += (
                    round(48 * falling * falling * self.sy) - (rotated.height - piece.height) // 2
                )
                piece = rotated
            result.alpha_composite(piece, (left, top))
        if motion:
            self.layer = Image.new("RGBA", self.size)
            self.draw = ImageDraw.Draw(self.layer)
            for index, (x, _, direction) in enumerate(self.stone[:32]):
                life = age - 0.25 - index % 11 * 0.36
                if not 0 < life < 1.4:
                    continue
                y = (66 if index % 2 else 205) + 42 * life * life
                x += direction * life * 0.5
                radius = 0.5 + life
                self.oval(
                    (x - radius, y - radius, x + radius, y + radius),
                    (184, 171, 128, round(115 * (1 - life / 1.4))),
                )
                if index % 4 == 0:
                    self.poly([(x, y), (x + 2, y + 3), (x - 1, y + 4)], "#82775A")
            result.alpha_composite(self.layer)
        return result

    def neon(self, t: float) -> None:
        """Run circuit packets, a restrained raster scan and a small light-cycle trace"""
        reserve = self.remaining(t) / self.seconds
        for index, x in enumerate(range(60, 491, 14)):
            if index / 31 < reserve:
                self.box((x + 1, 206, x + 6, 211), self.accent if reserve > 0.15 else "#F2A66F")
        for index, (phase, period) in enumerate(self.events[:4]):
            life = (t + phase) % (period / 4) / (period / 4)
            x = 22 + life * 492
            y = 19 if index % 2 == 0 else 215
            self.line([(max(22, x - 27), y), (x, y)], self.accent, 1.2)
            self.box((x, y - 1, x + 3, y + 1), "#D9FAFF")
        scan = 42 + (t * 11) % 126
        self.line([(20, scan), (520, scan)], (82, 224, 240, 16))
        x = 32 + (t * 24) % 464
        self.line([(max(24, x - 52), 206), (x, 206)], "#F6A753")
        self.box((x - 3, 201, x + 6, 205), "#163445")
        self.oval((x - 3, 205, x, 208), "#FFD695")
        self.oval((x + 3, 205, x + 6, 208), "#FFD695")
        for x, y in ((18, 39), (522, 141), (48, 19), (492, 214)):
            self.oval(
                (x - 1, y - 1, x + 1, y + 1), (132, 230, 243, round(70 + 45 * math.sin(t + x)))
            )

    def subway(self, t: float) -> None:
        """Move a train along the lower rail while paint strokes write and fade at the edges"""
        self.line([(20, 219), (520, 219)], "#263A45", 2)
        depletion = 1 - self.remaining(t) / max(1, self.seconds)
        for index in range(9):
            x = 58 + index * 50
            column = min(self.size[0] - 1, round(x * self.sx))
            for y in range(161, 85, -3):
                if (
                    cast(
                        int, self.mask.getpixel((column, min(self.size[1] - 1, round(y * self.sy))))
                    )
                    > 180
                ):
                    length = 3 + depletion * (9 + index % 3 * 6)
                    colour = (self.accent, "#F45C91", "#79E3E8")[index % 3]
                    self.line([(x, y - 1), (x, y + length)], colour, 2)
                    self.oval((x - 1.5, y + length - 1, x + 1.5, y + length + 2), colour)
                    break
        life = t % 17 / 17
        x = -155 + life * 850
        for carriage in range(3):
            left = x + carriage * 49
            self.box((left, 199, left + 45, 214), "#A2BAC4")
            self.box((left, 210, left + 45, 213), "#EF9750")
            for window in (5, 19, 33):
                self.box((left + window, 202, left + window + 8, 208), "#18455B")
                self.line([(left + window, 202), (left + window + 4, 205)], "#78A7B7")
            for wheel in (9, 34):
                self.oval((left + wheel - 3, 213, left + wheel + 3, 219), "#273B48")
        for index, (phase, period) in enumerate(self.events[:4]):
            life = (t + phase) % period / period
            x = 24 + index * 146
            y = 17 if index % 2 == 0 else 190
            points = [
                (x, y + 5),
                (x + 10, y - 3),
                (x + 25, y + 5),
                (x + 18, y + 11),
                (x + 33, y + 4),
            ]
            count = max(2, min(5, math.ceil(life * 10)))
            colour = ("#6EDDB4", "#EF92CA", "#FFC856", "#91CDED")[index]
            self.line(points[:count], "#284651", 5)
            self.line(points[:count], colour, 2)
            self.line([(x + 18, y + 11), (x + 18, y + 11 + 5 * life)], colour)
            for dot in range(5):
                self.oval((x + dot * 9, y - 6, x + dot * 9 + 0.8, y - 5.2), colour)

    def glass(self, t: float) -> None:
        """Sweep liquid caustics and meniscus reflections around a transparent surface"""
        reflection = Image.new("RGBA", self.size)
        draw = ImageDraw.Draw(reflection)
        for phase in (0, 2.8):
            points = [
                (x, 108 + 28 * math.sin(x / 110 + t * 0.5 + phase)) for x in range(20, 521, 4)
            ]
            draw.line(
                self.points(points), fill=(246, 254, 255, 45), width=max(1, round(2 * self.sx))
            )
        reflection = reflection.filter(ImageFilter.GaussianBlur(max(0.3, self.sx)))
        reflection.putalpha(ImageChops.multiply(reflection.getchannel("A"), self.mask))
        self.layer.alpha_composite(reflection)
        for edge in (0, 1):
            y = 9 if edge == 0 else 225
            points = [(x, y + 2 * math.sin(x / 70 + t * 0.7)) for x in range(30, 511, 4)]
            self.line(points, (211, 236, 255, 65 if edge == 0 else 35), 1.2)
        for phase, period in self.events[:3]:
            life = (t + phase) % period / period
            x = 27 + life * 482
            alpha = round(80 * math.sin(math.pi * life) ** 2)
            self.line([(x - 12, 15), (x + 14, 15)], (245, 253, 255, alpha), 2)
            self.line([(538, 40 + life * 154), (535, 50 + life * 154)], (225, 245, 255, alpha), 1.5)

    def paint(self, canvas: Image.Image, elapsed: float | None = None) -> Image.Image:
        """Composite the same material and ambient scene in previews and exports

        ``None`` produces the still/reduced-motion state without ambient activity
        The working images are panel-sized and replaced rather than accumulated
        """
        canvas = canvas.copy()
        moment = self.changed if elapsed is None else elapsed
        fraction = max(0, elapsed - self.changed) if elapsed is not None else 1
        material = (
            Image.blend(self.previous, self.material, min(1, fraction / 0.18))
            if self.previous is not None and fraction < 0.18 and self.remaining(moment) > 0
            else self.material
        )
        canvas.alpha_composite(self.outline)
        if self.kind != "temple-run" or self.remaining(moment) >= 5:
            canvas.alpha_composite(material)
        if elapsed is None and self.kind not in {
            "temple-run",
            "minecraft",
            "super-mario",
            "minions",
            "sonic",
            "pac-man",
            "subway-surfers",
        }:
            return canvas
        self.layer = Image.new("RGBA", self.size)
        self.draw = ImageDraw.Draw(self.layer)
        if self.kind == "minecraft":
            self.minecraft(moment, motion=elapsed is not None)
        elif self.kind == "temple-run":
            self.temple(moment, motion=elapsed is not None)
        elif self.kind == "neon":
            self.neon(moment)
        elif self.kind == "subway-surfers":
            self.subway(moment)
        elif self.kind == "glass":
            self.glass(moment)
        elif self.kind in {"super-mario", "minions", "sonic", "pac-man"}:
            self.arcade(moment)
        else:
            x = 30 + (moment * 16) % 480
            self.line([(x, 3), (x + 16, 3)], (220, 237, 243, 65))
        if self.kind in {"temple-run", "glass"}:
            self.layer.putalpha(
                ImageChops.multiply(self.layer.getchannel("A"), canvas.getchannel("A"))
            )
        canvas.alpha_composite(self.layer)
        if self.kind == "temple-run" and self.remaining(moment) < 5:
            canvas = self.fracture(canvas, moment, motion=elapsed is not None)
            # Keep the last seconds legible while their stone support falls away
            canvas.alpha_composite(material)
        return canvas


def liquid(canvas: Image.Image, bounds: tuple[int, int, int, int], elapsed: float) -> None:
    """Refract the preview background with the same field used by the native export filter"""
    x, y, width, height = bounds
    patch = canvas.crop((x, y, x + width, y + height))
    scale = width / 540
    mesh: list[tuple[tuple[int, int, int, int], tuple[float, ...]]] = []
    for row in range(4):
        for column in range(8):
            left, right = round(column * width / 8), round((column + 1) * width / 8)
            top, bottom = round(row * height / 4), round((row + 1) * height / 4)
            if right <= left or bottom <= top:
                continue
            vertices: list[float] = []
            for a, b in ((left, top), (left, bottom), (right, bottom), (right, top)):
                vertices.extend((
                    min(
                        width - 1,
                        max(0, a + scale * 3 * math.sin(b / max(1, height) * 8 + elapsed * 0.7)),
                    ),
                    min(
                        height - 1,
                        max(0, b + scale * 2 * math.sin(a / max(1, width) * 7 + elapsed * 0.5)),
                    ),
                ))
            mesh.append(((left, top, right, bottom), tuple(vertices)))
    patch = patch.transform(patch.size, Image.Transform.MESH, mesh, Image.Resampling.BILINEAR)  # pyright: ignore[reportUnknownMemberType]
    patch = patch.filter(ImageFilter.GaussianBlur(max(0.2, scale * 1.5)))
    mask = Image.new("L", patch.size)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=27 * scale, fill=255
    )
    canvas.paste(patch, (x, y), mask)
