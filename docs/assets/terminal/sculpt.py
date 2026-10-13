"""Bake shaded braille habitats without a runtime graphics dependency"""

import sys
import tomllib
from collections.abc import Iterable, Mapping
from math import cos, pi, sin, sqrt
from pathlib import Path

WIDTH, HEIGHT = 80, 64
BITS = ((1, 8), (2, 16), (4, 32), (64, 128))
ROOT = Path(__file__).parent
FOREST = tomllib.loads((ROOT / "forest.toml").read_text())
type Shape = tuple[float, float, float, float, float, float, float]
type Model = dict[str, Shape]


def shape(x: float, y: float, rx: float, ry: float, depth: float = 0.15, front: float = 0) -> Shape:
    """Keep editable ellipsoid geometry in normalised habitat coordinates"""
    return x, y, rx, ry, depth, front, 0


def surface(x: float, y: float, model: Shape) -> float | None:
    """Find the visible depth of a rotated ellipsoid"""
    cx, cy, rx, ry, depth, front, angle = model
    dx, dy = x - cx, y - cy
    radius = ((dx * cos(angle) + dy * sin(angle)) / rx) ** 2 + (
        (dy * cos(angle) - dx * sin(angle)) / ry
    ) ** 2
    return front + depth * sqrt(1 - radius) if radius < 1 else None


def draw(shapes: Mapping[str, Shape], cuts: Mapping[str, Shape]) -> dict[str, str]:
    """Bake braille dots, depth, materials and pointer targets from one model"""
    pixels: list[list[float | None]] = []
    regions: list[list[str]] = []
    tones: list[list[str]] = []
    for row in range(HEIGHT):
        depths: list[float | None] = []
        areas: list[str] = []
        materials: list[str] = []
        for col in range(WIDTH):
            x, y = (col + 0.5) / WIDTH, (row + 0.5) / HEIGHT
            surfaces = [
                (z, key) for key, model in shapes.items() if (z := surface(x, y, model)) is not None
            ]
            z, key = max(surfaces) if surfaces else (None, "")
            if any(surface(x, y, model) is not None for model in cuts.values()):
                z, key = None, ""
            depths.append(z)
            areas.append(
                "0"
                if not key or key.startswith("scene")
                else "3"
                if key.startswith("prop")
                else "1"
                if key.startswith(("head", "ear", "horn", "beak", "face", "eye", "nose", "antenna"))
                else "2"
            )
            materials.append(
                "3"
                if key.startswith(("sceneleaf", "propleaf"))
                else "4"
                if key.startswith("scenewater")
                else "5"
                if key.startswith(("propflower", "facewattle", "colour"))
                else "6"
                if key.startswith(("prop", "scenerock", "sceneground", "scenetree"))
                else "7"
                if key.startswith("eyelight")
                else "1"
                if key.startswith(("white", "facewhite"))
                else "2"
                if key.startswith(("dark", "eye", "nose", "facemouth"))
                else "0"
            )
        pixels.append(depths)
        regions.append(areas)
        tones.append(materials)
    result: dict[str, list[str]] = {key: [] for key in ("art", "shade", "hit", "tone")}
    for row in range(0, HEIGHT, 4):
        glyphs: list[str] = []
        levels: list[str] = []
        targets: list[str] = []
        colours: list[str] = []
        for col in range(0, WIDTH, 2):
            samples = [
                (dy, dx)
                for dy in range(4)
                for dx in range(2)
                if pixels[row + dy][col + dx] is not None
            ]
            glyphs.append(chr(0x2800 + sum(BITS[dy][dx] for dy, dx in samples)) if samples else " ")
            yy, xx = min(row + 2, HEIGHT - 2), min(col + 1, WIDTH - 2)
            z, brightness = pixels[yy][xx], 3
            if z is not None:
                nx = -((pixels[yy][xx + 1] or z) - (pixels[yy][xx - 1] or z)) * WIDTH / 2
                ny = -((pixels[yy + 1][xx] or z) - (pixels[yy - 1][xx] or z)) * HEIGHT / 2
                brightness = 2 + 5 * max(
                    0,
                    (-0.6 * nx - 0.8 * ny + 1.2) / sqrt(nx * nx + ny * ny + 1) / sqrt(2.44),
                )
            levels.append(str(min(7, max(0, round(brightness)))))
            for field, output in ((regions, targets), (tones, colours)):
                values = [field[row + dy][col + dx] for dy, dx in samples]
                if field is tones and (
                    "7" in values or values.count("1") >= 2 or values.count("2") >= 3
                ):
                    # Preserve small eye glints and markings within a single-colour braille cell
                    output.append("7" if "7" in values else "1" if values.count("1") >= 2 else "2")
                else:
                    output.append(max(sorted(set(values)), key=values.count) if values else "0")
        for key, values in zip(result, (glyphs, levels, targets, colours), strict=True):
            result[key].append("".join(values).rstrip() if key == "art" else "".join(values))
    return {key: "\n".join(rows) for key, rows in result.items()}


# Model the silhouette and markings before applying movement
animals: dict[str, tuple[Model, Model]] = {}
for name in FOREST:
    shapes = {
        "body": shape(0.48, 0.68, 0.23, 0.13, 0.20),
        "head": shape(0.25, 0.49, 0.115, 0.10, 0.18, 0.06),
        "neck": shape(0.32, 0.59, 0.09, 0.12, 0.16),
        "ear1": shape(0.20, 0.38, 0.028, 0.065, 0.09),
        "ear2": shape(0.31, 0.39, 0.025, 0.058, 0.08),
        "face": shape(0.16, 0.54, 0.08, 0.04, 0.09, 0.14),
        "paw1": shape(0.31, 0.80, 0.025, 0.09, 0.08, 0.04),
        "paw2": shape(0.64, 0.80, 0.035, 0.09, 0.08, 0.03),
        "foot1": shape(0.29, 0.88, 0.05, 0.02, 0.07, 0.05),
        "foot2": shape(0.64, 0.88, 0.055, 0.022, 0.07, 0.04),
        "tail": shape(0.77, 0.64, 0.105, 0.11, 0.10),
        "eye1": shape(0.22, 0.47, 0.021, 0.023, 0.02, 0.245),
        "eyelight": shape(0.215, 0.46, 0.006, 0.007, 0.01, 0.27),
        "nose": shape(0.09, 0.54, 0.015, 0.015, 0.02, 0.24),
        "prop": shape(0.83, 0.89, 0.12, 0.04, 0.06),
    }
    cuts: Model = {}
    if name == "numbat":
        shapes["tail"] = shape(0.77, 0.57, 0.13, 0.16, 0.13)
        shapes["facewhite"] = shape(0.21, 0.51, 0.075, 0.014, 0.015, 0.24)
        for n in range(5):
            shapes[f"white{n}"] = shape(0.44 + n * 0.045, 0.66, 0.009, 0.105, 0.015, 0.22)
        cuts["log"] = shape(0.82, 0.89, 0.07, 0.006)
    elif name in ("saola", "tahr", "horse"):
        shapes.update({
            "body": shape(0.51, 0.62, 0.23, 0.145, 0.20),
            "head": shape(0.26, 0.40, 0.075, 0.14, 0.18, 0.06),
            "neck": shape(0.32, 0.55, 0.06, 0.145, 0.15),
            "ear1": shape(0.15, 0.35, 0.07, 0.032, 0.08),
            "ear2": shape(0.35, 0.35, 0.06, 0.03, 0.08),
            "horn1": shape(0.225, 0.18, 0.012, 0.16, 0.08),
            "horn2": shape(0.285, 0.18, 0.012, 0.16, 0.08),
            "face": shape(0.22, 0.49, 0.06, 0.045, 0.09, 0.14),
            "facewhite": shape(0.25, 0.39, 0.016, 0.11, 0.015, 0.245),
            "eye1": shape(0.21, 0.38, 0.017, 0.021, 0.02, 0.255),
            "eyelight": shape(0.205, 0.37, 0.006, 0.006, 0.01, 0.28),
            "nose": shape(0.18, 0.50, 0.018, 0.013, 0.02, 0.25),
            "paw1": shape(0.33, 0.78, 0.018, 0.12, 0.08),
            "paw2": shape(0.66, 0.78, 0.022, 0.12, 0.08),
            "foot1": shape(0.32, 0.90, 0.03, 0.017, 0.05),
            "foot2": shape(0.66, 0.90, 0.032, 0.017, 0.05),
            "tail": shape(0.725, 0.67, 0.025, 0.095, 0.04),
            "prop": shape(0.11, 0.83, 0.06, 0.018, 0.02),
        })
        for n in range(3):
            shapes[f"propleaf{n}"] = shape(0.10 + n * 0.04, 0.81 - n * 0.045, 0.035, 0.022, 0.03)
        if name == "tahr":
            shapes["horn1"] = shape(0.25, 0.27, 0.045, 0.06, 0.07)
            shapes["horn2"] = shape(0.32, 0.28, 0.035, 0.05, 0.05)
            shapes.pop("facewhite")
            shapes["white0"] = shape(0.54, 0.63, 0.09, 0.065, 0.03, 0.21)
            shapes["prop"] = shape(0.85, 0.87, 0.11, 0.065, 0.05)
        elif name == "horse":
            for key in ("horn1", "horn2", "facewhite"):
                shapes.pop(key)
            shapes["head"] = shape(0.25, 0.39, 0.075, 0.14, 0.18, 0.06)
            shapes["ear1"] = shape(0.22, 0.24, 0.019, 0.07, 0.07)
            shapes["ear2"] = shape(0.30, 0.24, 0.019, 0.06, 0.07)
            shapes["darkmane"] = shape(0.34, 0.39, 0.023, 0.13, 0.06)
            shapes["tail"] = shape(0.76, 0.75, 0.025, 0.12, 0.05)
    elif name in (
        "huia",
        "bustard",
        "florican",
        "vulture",
        "dodo",
        "pigeon",
        "parakeet",
        "kakapo",
        "eagle",
    ):
        shapes.update({
            "body": shape(0.46, 0.59, 0.15, 0.23, 0.20),
            "head": shape(0.31, 0.31, 0.105, 0.10, 0.18, 0.04),
            "neck": shape(0.37, 0.43, 0.085, 0.12, 0.16),
            "ear1": shape(0.31, 0.23, 0.055, 0.025, 0.06),
            "ear2": shape(0.36, 0.26, 0.025, 0.025, 0.05),
            "face": shape(0.22, 0.36, 0.08, 0.018, 0.05, 0.10),
            "beak1": shape(0.15, 0.40, 0.05, 0.026, 0.04),
            "beak2": shape(0.12, 0.44, 0.021, 0.045, 0.04),
            "facewattle": shape(0.28, 0.38, 0.03, 0.034, 0.05, 0.20),
            "eye1": shape(0.27, 0.30, 0.018, 0.02, 0.02, 0.25),
            "eyelight": shape(0.265, 0.293, 0.006, 0.006, 0.01, 0.28),
            "nose": shape(0.105, 0.475, 0.007, 0.006, 0.02),
            "paw1": shape(0.39, 0.61, 0.06, 0.16, 0.10, 0.06),
            "paw2": shape(0.54, 0.60, 0.055, 0.15, 0.08),
            "foot1": shape(0.42, 0.85, 0.045, 0.023, 0.04),
            "foot2": shape(0.52, 0.85, 0.045, 0.023, 0.04),
            "tail": shape(0.61, 0.72, 0.075, 0.15, 0.06),
            "white0": shape(0.61, 0.84, 0.07, 0.025, 0.02, 0.09),
            "prop": shape(0.50, 0.89, 0.40, 0.016, 0.04),
        })
        if name != "huia":
            for key in ("ear1", "ear2", "beak2", "facewattle", "white0"):
                shapes.pop(key, None)
            shapes["face"] = shape(0.23, 0.345, 0.055, 0.028, 0.06, 0.14)
            shapes["beak1"] = shape(0.19, 0.35, 0.055, 0.017, 0.04, 0.18)
            shapes["nose"] = shape(0.14, 0.35, 0.009, 0.008, 0.02, 0.22)
            if name in ("bustard", "florican"):
                shapes["body"] = shape(0.50, 0.59, 0.20, 0.13, 0.20)
                shapes["neck"] = shape(0.36, 0.46, 0.045, 0.20, 0.13)
                shapes["head"] = shape(0.32, 0.26, 0.07, 0.055, 0.16, 0.04)
                shapes["face"] = shape(0.26, 0.28, 0.045, 0.018, 0.04, 0.14)
                shapes["eye1"] = shape(0.30, 0.255, 0.012, 0.012, 0.02, 0.23)
                shapes["eyelight"] = shape(0.296, 0.25, 0.004, 0.004, 0.01, 0.26)
                shapes["beak1"] = shape(0.235, 0.28, 0.05, 0.015, 0.04, 0.10)
                shapes["nose"] = shape(0.185, 0.28, 0.006, 0.006, 0.015, 0.13)
                shapes["paw1"] = shape(0.45, 0.55, 0.11, 0.07, 0.07, 0.17)
                shapes["paw2"] = shape(0.53, 0.75, 0.012, 0.12, 0.05)
                shapes["leg1"] = shape(0.42, 0.74, 0.012, 0.12, 0.05)
                shapes["tail"] = shape(0.70, 0.59, 0.10, 0.04, 0.06)
                shapes["white0"] = shape(0.42, 0.64, 0.11, 0.03, 0.025, 0.22)
                if name == "florican":
                    shapes["body"] = shape(0.48, 0.59, 0.15, 0.12, 0.19)
                    shapes["darkneck"] = shape(0.355, 0.44, 0.04, 0.18, 0.02, 0.15)
                    shapes["white1"] = shape(0.48, 0.55, 0.09, 0.04, 0.03, 0.23)
            elif name == "dodo":
                shapes["body"] = shape(0.49, 0.62, 0.23, 0.23, 0.23)
                shapes["beak1"] = shape(0.16, 0.34, 0.10, 0.045, 0.07, 0.14)
                shapes["beak2"] = shape(0.08, 0.37, 0.03, 0.03, 0.06, 0.15)
                shapes["paw1"] = shape(0.41, 0.62, 0.055, 0.095, 0.065, 0.19)
                shapes["tail"] = shape(0.70, 0.64, 0.065, 0.07, 0.09)
                shapes["white0"] = shape(0.72, 0.65, 0.06, 0.07, 0.03, 0.08)
            elif name in ("pigeon", "parakeet"):
                shapes["body"] = shape(0.47, 0.58, 0.14, 0.18, 0.19)
                shapes["tail"] = shape(0.65, 0.76, 0.085, 0.15, 0.08)
                shapes["paw1"] = shape(0.48, 0.55, 0.085, 0.13, 0.07, 0.16)
                shapes["paw2"] = shape(0.39, 0.78, 0.014, 0.07, 0.05)
                shapes["colourbreast"] = shape(0.36, 0.57, 0.05, 0.13, 0.03, 0.20)
                if name == "parakeet":
                    shapes["facewattle"] = shape(0.31, 0.31, 0.105, 0.10, 0.02, 0.225)
                    shapes["eye1"] = shape(0.27, 0.30, 0.015, 0.018, 0.02, 0.26)
                    shapes["eyelight"] = shape(0.265, 0.294, 0.005, 0.005, 0.01, 0.29)
                    shapes["beak1"] = shape(0.215, 0.36, 0.038, 0.032, 0.035, 0.245)
            elif name == "kakapo":
                shapes["body"] = shape(0.50, 0.63, 0.23, 0.19, 0.23)
                shapes["head"] = shape(0.29, 0.39, 0.11, 0.105, 0.18, 0.06)
                shapes["facewhite"] = shape(0.275, 0.39, 0.09, 0.08, 0.03, 0.225)
                shapes["eye1"] = shape(0.235, 0.37, 0.015, 0.019, 0.02, 0.26)
                shapes["eyelight"] = shape(0.23, 0.366, 0.005, 0.006, 0.01, 0.29)
                shapes["face"] = shape(0.265, 0.43, 0.025, 0.025, 0.025, 0.255)
                shapes["beak1"] = shape(0.26, 0.44, 0.025, 0.025, 0.03, 0.25)
                shapes["tail"] = shape(0.72, 0.68, 0.12, 0.055, 0.08)
                for n in range(8):
                    shapes[f"dark{n}"] = shape(
                        0.40 + n * 0.036,
                        0.64 + 0.07 * sin(n),
                        0.013,
                        0.009,
                        0.014,
                        0.24,
                    )
            else:
                shapes["beak1"] = shape(0.21, 0.36, 0.045, 0.036, 0.04, 0.17)
                shapes["white0"] = shape(0.40, 0.58, 0.06, 0.16, 0.025, 0.225)
                if name == "vulture":
                    shapes["neck"] = shape(0.34, 0.45, 0.045, 0.12, 0.12)
                    shapes["facewhite"] = shape(0.35, 0.47, 0.095, 0.028, 0.03, 0.19)
                    shapes["head"] = shape(0.31, 0.31, 0.075, 0.08, 0.15, 0.04)
                else:
                    for n in range(5):
                        shapes[f"ear{n}"] = shape(
                            0.32 + n * 0.022, 0.22 + 0.02 * sin(n), 0.008, 0.06, 0.05
                        )
        for n in range(3):
            cuts[f"feather{n}"] = shape(0.40 + n * 0.025, 0.66, 0.003, 0.09)
    elif name in ("mink", "otter"):
        shapes.update({
            "body": shape(0.49, 0.72, 0.24, 0.095, 0.17),
            "head": shape(0.25, 0.60, 0.105, 0.08, 0.16, 0.04),
            "neck": shape(0.33, 0.68, 0.09, 0.09, 0.14),
            "ear1": shape(0.19, 0.535, 0.026, 0.026, 0.08),
            "ear2": shape(0.29, 0.53, 0.024, 0.026, 0.08),
            "face": shape(0.16, 0.64, 0.07, 0.035, 0.08, 0.12),
            "facewhite": shape(0.15, 0.66, 0.06, 0.012, 0.02, 0.23),
            "eye1": shape(0.21, 0.59, 0.017, 0.02, 0.02, 0.22),
            "eyelight": shape(0.205, 0.583, 0.005, 0.006, 0.01, 0.25),
            "nose": shape(0.105, 0.635, 0.017, 0.013, 0.02, 0.24),
            "paw1": shape(0.31, 0.81, 0.023, 0.06, 0.06),
            "paw2": shape(0.63, 0.82, 0.03, 0.05, 0.06),
            "tail": shape(0.80, 0.75, 0.16, 0.026, 0.06),
            "prop": shape(0.83, 0.84, 0.09, 0.026, 0.04),
        })
        cuts["whisker"] = shape(0.14, 0.63, 0.055, 0.004)
        if name == "otter":
            shapes["body"] = shape(0.49, 0.71, 0.25, 0.12, 0.20)
            shapes["head"] = shape(0.25, 0.59, 0.11, 0.095, 0.17, 0.04)
            shapes["white0"] = shape(0.31, 0.69, 0.04, 0.07, 0.02, 0.20)
            shapes["tail"] = shape(0.79, 0.77, 0.17, 0.04, 0.08)
    elif name == "bee":
        shapes.pop("neck")
        shapes.update({
            "body": shape(0.47, 0.57, 0.17, 0.11, 0.18),
            "head": shape(0.28, 0.48, 0.08, 0.08, 0.16, 0.07),
            "face": shape(0.24, 0.54, 0.04, 0.025, 0.08, 0.12),
            "ear1": shape(0.245, 0.38, 0.009, 0.06, 0.04),
            "ear2": shape(0.31, 0.39, 0.009, 0.06, 0.04),
            "antenna1": shape(0.24, 0.32, 0.014, 0.012, 0.04),
            "antenna2": shape(0.31, 0.33, 0.014, 0.012, 0.04),
            "paw1": shape(0.37, 0.39, 0.12, 0.12, 0.035, -0.02),
            "paw2": shape(0.55, 0.40, 0.11, 0.13, 0.03, -0.02),
            "foot1": shape(0.42, 0.72, 0.008, 0.06, 0.04),
            "foot2": shape(0.55, 0.72, 0.008, 0.06, 0.04),
            "eye1": shape(0.255, 0.475, 0.017, 0.023, 0.02, 0.24),
            "eyelight": shape(0.25, 0.468, 0.006, 0.007, 0.01, 0.27),
            "nose": shape(0.23, 0.54, 0.008, 0.008, 0.02, 0.22),
            "prop": shape(0.81, 0.80, 0.009, 0.14, 0.02),
            "propflower": shape(0.81, 0.66, 0.075, 0.028, 0.03),
            "propflowercore": shape(0.81, 0.66, 0.025, 0.027, 0.04, 0.03),
            "dark0": shape(0.43, 0.57, 0.02, 0.09, 0.015, 0.205),
            "dark1": shape(0.53, 0.58, 0.02, 0.085, 0.015, 0.205),
            "facewattle": shape(0.48, 0.59, 0.025, 0.055, 0.015, 0.215),
        })
        shapes.pop("tail")
        for n in range(2):
            cuts[f"vein{n}"] = shape(0.36 + n * 0.17, 0.38, 0.045, 0.003)
    elif name == "quoll":
        shapes["tail"] = shape(0.81, 0.73, 0.15, 0.025, 0.055)
        shapes["ear1"] = shape(0.18, 0.39, 0.045, 0.045, 0.09)
        shapes["ear2"] = shape(0.30, 0.40, 0.037, 0.04, 0.08)
        for n, (x, y) in enumerate((
            (0.38, 0.62),
            (0.47, 0.64),
            (0.56, 0.62),
            (0.64, 0.66),
            (0.42, 0.73),
            (0.52, 0.75),
            (0.60, 0.74),
        )):
            shapes[f"white{n}"] = shape(x, y, 0.012, 0.014, 0.015, 0.22)
        shapes["prop"] = shape(0.83, 0.87, 0.10, 0.055, 0.09)
    elif name in ("pangolin", "indipangolin", "solenodon"):
        shapes.update({
            "body": shape(0.48, 0.68, 0.22, 0.18, 0.22),
            "head": shape(0.23, 0.56, 0.10, 0.08, 0.14, 0.04),
            "neck": shape(0.31, 0.64, 0.09, 0.08, 0.14),
            "face": shape(0.13, 0.61, 0.10, 0.025, 0.06, 0.10),
            "ear1": shape(0.20, 0.50, 0.02, 0.024, 0.05),
            "ear2": shape(0.29, 0.52, 0.017, 0.02, 0.05),
            "eye1": shape(0.19, 0.55, 0.014, 0.016, 0.02, 0.21),
            "eyelight": shape(0.185, 0.545, 0.004, 0.005, 0.01, 0.24),
            "nose": shape(0.045, 0.61, 0.011, 0.008, 0.02, 0.21),
            "tail": shape(0.78, 0.77, 0.20, 0.045, 0.10),
        })
        if name == "solenodon":
            shapes["tail"] = shape(0.81, 0.78, 0.16, 0.017, 0.04)
            shapes["ear1"] = shape(0.20, 0.50, 0.035, 0.035, 0.08)
        else:
            for row in range(4):
                for col in range(5):
                    x, y = 0.30 + col * 0.065 + (row % 2) * 0.025, 0.57 + row * 0.055
                    if surface(x, y, shapes["body"]) is not None:
                        shapes[f"scale{row}{col}"] = shape(x, y, 0.024, 0.012, 0.012, 0.225)
    elif name in ("auk", "penguin"):
        shapes.update({
            "body": shape(0.48, 0.63, 0.18, 0.24, 0.22),
            "white0": shape(0.42, 0.66, 0.10, 0.18, 0.025, 0.225),
            "head": shape(0.39, 0.30, 0.11, 0.105, 0.18, 0.05),
            "neck": shape(0.43, 0.44, 0.10, 0.12, 0.18),
            "face": shape(0.25, 0.34, 0.10, 0.043, 0.09, 0.07),
            "ear1": shape(0.40, 0.23, 0.06, 0.03, 0.07),
            "ear2": shape(0.46, 0.29, 0.025, 0.03, 0.05),
            "facewhite": shape(0.355, 0.295, 0.035, 0.045, 0.02, 0.245),
            "eye1": shape(0.35, 0.30, 0.017, 0.018, 0.02, 0.27),
            "eyelight": shape(0.345, 0.293, 0.006, 0.006, 0.01, 0.30),
            "nose": shape(0.16, 0.35, 0.01, 0.02, 0.02),
            "paw1": shape(0.55, 0.61, 0.065, 0.115, 0.09, 0.11),
            "paw2": shape(0.58, 0.58, 0.06, 0.10, 0.07),
            "foot1": shape(0.41, 0.88, 0.065, 0.024, 0.05),
            "foot2": shape(0.54, 0.88, 0.06, 0.024, 0.05),
            "tail": shape(0.66, 0.77, 0.07, 0.03, 0.07),
            "prop": shape(0.83, 0.87, 0.12, 0.06, 0.10),
        })
        for n in range(3):
            cuts[f"bill{n}"] = shape(0.20 + n * 0.035, 0.34, 0.003, 0.025)
        if name == "penguin":
            cuts.clear()
            shapes["face"] = shape(0.29, 0.34, 0.055, 0.025, 0.05, 0.12)
            shapes["nose"] = shape(0.24, 0.34, 0.025, 0.012, 0.035, 0.18)
            shapes["facewhite"] = shape(0.39, 0.31, 0.035, 0.08, 0.02, 0.24)
            shapes["darkband"] = shape(0.48, 0.64, 0.105, 0.017, 0.015, 0.245)
    elif name in ("potoroo", "melomys"):
        shapes.update({
            "body": shape(0.50, 0.66, 0.19, 0.20, 0.22),
            "neck": shape(0.34, 0.58, 0.09, 0.12, 0.16),
            "ear1": shape(0.19, 0.38, 0.040, 0.058, 0.10),
            "ear2": shape(0.31, 0.39, 0.035, 0.05, 0.08),
            "paw1": shape(0.33, 0.72, 0.025, 0.08, 0.09, 0.04),
            "paw2": shape(0.61, 0.78, 0.08, 0.09, 0.13, 0.04),
            "foot1": shape(0.31, 0.83, 0.06, 0.025, 0.07, 0.06),
            "foot2": shape(0.54, 0.88, 0.09, 0.025, 0.08, 0.06),
            "tail": shape(0.75, 0.79, 0.18, 0.025, 0.04),
            "white0": shape(0.39, 0.70, 0.05, 0.12, 0.025, 0.22),
            "prop": shape(0.83, 0.87, 0.05, 0.03, 0.06),
        })
        if name == "potoroo":
            shapes["propflower"] = shape(0.83, 0.84, 0.075, 0.025, 0.06)
        else:
            shapes["body"] = shape(0.48, 0.70, 0.20, 0.14, 0.20)
            shapes["paw2"] = shape(0.62, 0.80, 0.032, 0.06, 0.08)
            shapes["foot2"] = shape(0.62, 0.86, 0.055, 0.02, 0.07)
            shapes["prop"] = shape(0.84, 0.89, 0.055, 0.023, 0.03, 0.12)
    elif name == "skink":
        shapes.update({
            "body": shape(0.49, 0.71, 0.25, 0.07, 0.16),
            "head": shape(0.22, 0.66, 0.09, 0.065, 0.14, 0.05),
            "neck": shape(0.30, 0.69, 0.075, 0.05, 0.13),
            "face": shape(0.15, 0.69, 0.055, 0.027, 0.08, 0.12),
            "eye1": shape(0.20, 0.65, 0.016, 0.018, 0.02, 0.22),
            "eyelight": shape(0.195, 0.644, 0.006, 0.006, 0.01, 0.25),
            "nose": shape(0.105, 0.686, 0.009, 0.008, 0.02, 0.23),
            "paw1": shape(0.33, 0.78, 0.038, 0.045, 0.06, 0.05),
            "paw2": shape(0.66, 0.78, 0.045, 0.045, 0.06, 0.05),
            "foot1": shape(0.30, 0.82, 0.045, 0.01, 0.04, 0.04),
            "foot2": shape(0.68, 0.82, 0.05, 0.01, 0.04, 0.04),
            "tail": shape(0.82, 0.73, 0.18, 0.026, 0.07),
            "white0": shape(0.48, 0.67, 0.24, 0.01, 0.014, 0.17),
            "prop": shape(0.78, 0.88, 0.15, 0.032, 0.04),
        })
        for key in ("ear1", "ear2"):
            shapes.pop(key)
        for n in range(5):
            shapes[f"scale{n}"] = shape(0.34 + n * 0.07, 0.71, 0.022, 0.012, 0.008, 0.16)
    elif name == "paddlefish":
        shapes = {
            "body": shape(0.52, 0.54, 0.22, 0.11, 0.20),
            "head": shape(0.31, 0.52, 0.10, 0.09, 0.16, 0.06),
            "face": shape(0.17, 0.49, 0.16, 0.019, 0.06, 0.13),
            "eye1": shape(0.30, 0.51, 0.016, 0.018, 0.02, 0.24),
            "eyelight": shape(0.295, 0.504, 0.006, 0.006, 0.01, 0.27),
            "nose": shape(0.035, 0.49, 0.012, 0.008, 0.02, 0.22),
            "white0": shape(0.51, 0.59, 0.20, 0.027, 0.02, 0.21),
            "paw1": shape(0.44, 0.66, 0.06, 0.065, 0.07),
            "paw2": shape(0.61, 0.40, 0.055, 0.08, 0.07),
            "tail": shape(0.82, 0.54, 0.12, 0.022, 0.08),
            "tailupper": shape(0.89, 0.46, 0.038, 0.11, 0.06),
            "taillower": shape(0.89, 0.60, 0.03, 0.065, 0.055),
            "prop": shape(0.78, 0.90, 0.13, 0.055, 0.07),
            "propleaf": shape(0.83, 0.75, 0.014, 0.12, 0.025),
        }
        cuts["gill"] = shape(0.36, 0.53, 0.003, 0.055)
    elif name == "frog":
        shapes = {
            "body": shape(0.53, 0.66, 0.18, 0.16, 0.20),
            "head": shape(0.32, 0.54, 0.14, 0.105, 0.17, 0.06),
            "neck": shape(0.40, 0.63, 0.10, 0.09, 0.15),
            "face": shape(0.27, 0.60, 0.13, 0.035, 0.08, 0.17),
            "eye1": shape(0.25, 0.49, 0.025, 0.031, 0.025, 0.23),
            "eyelight": shape(0.245, 0.482, 0.008, 0.008, 0.01, 0.28),
            "nose": shape(0.16, 0.576, 0.009, 0.008, 0.02, 0.26),
            "paw1": shape(0.35, 0.73, 0.025, 0.10, 0.07, 0.10),
            "paw2": shape(0.64, 0.74, 0.11, 0.11, 0.12, 0.07),
            "foot1": shape(0.30, 0.84, 0.08, 0.014, 0.05, 0.07),
            "foot2": shape(0.66, 0.84, 0.13, 0.018, 0.06, 0.09),
            "white0": shape(0.43, 0.71, 0.05, 0.06, 0.015, 0.215),
            "prop": shape(0.84, 0.87, 0.09, 0.025, 0.03),
            "propleaf": shape(0.85, 0.85, 0.11, 0.024, 0.04),
        }
        for n in range(5):
            shapes[f"dark{n}"] = shape(0.43 + n * 0.045, 0.62, 0.01, 0.014, 0.012, 0.22)
    elif name == "crayfish":
        shapes = {
            "body": shape(0.51, 0.67, 0.20, 0.095, 0.18),
            "head": shape(0.31, 0.62, 0.09, 0.07, 0.13, 0.05),
            "face": shape(0.24, 0.60, 0.065, 0.018, 0.06, 0.12),
            "eye1": shape(0.27, 0.565, 0.016, 0.020, 0.03, 0.22),
            "eyelight": shape(0.264, 0.559, 0.006, 0.006, 0.01, 0.26),
            "antenna1": shape(0.16, 0.52, 0.105, 0.006, 0.02),
            "antenna2": shape(0.17, 0.64, 0.12, 0.005, 0.02),
            "paw1": shape(0.22, 0.73, 0.08, 0.026, 0.07, 0.05),
            "paw2": shape(0.25, 0.48, 0.07, 0.026, 0.07, 0.04),
            "claw1": shape(0.12, 0.73, 0.09, 0.052, 0.08, 0.07),
            "claw2": shape(0.16, 0.47, 0.08, 0.05, 0.08, 0.06),
            "tail": shape(0.76, 0.71, 0.11, 0.055, 0.09),
            "prop": shape(0.85, 0.84, 0.12, 0.03, 0.07),
        }
        for n in range(3):
            shapes[f"leg{n}"] = shape(0.39 + n * 0.09, 0.79, 0.007, 0.09, 0.04)
            shapes[f"scale{n}"] = shape(0.58 + n * 0.045, 0.70, 0.008, 0.06, 0.01, 0.18)
        cuts["pincer1"] = shape(0.07, 0.73, 0.055, 0.012)
        cuts["pincer2"] = shape(0.11, 0.47, 0.05, 0.011)
        cuts["burrow"] = shape(0.85, 0.845, 0.09, 0.012)
    elif name in ("tiger", "panda", "dog", "leopard", "lynx", "thylacine"):
        shapes["tail"] = shape(0.79, 0.71, 0.17, 0.032, 0.07)
        shapes["ear1"] = shape(0.19, 0.39, 0.035, 0.036, 0.08)
        shapes["ear2"] = shape(0.30, 0.40, 0.032, 0.034, 0.07)
        shapes["facewhite"] = shape(0.15, 0.55, 0.07, 0.032, 0.035, 0.23)
        if name == "tiger":
            shapes["body"] = shape(0.49, 0.67, 0.25, 0.15, 0.22)
            for n in range(6):
                shapes[f"dark{n}"] = shape(0.40 + n * 0.048, 0.67, 0.010, 0.11, 0.02, 0.225)
            shapes["white0"] = shape(0.43, 0.74, 0.14, 0.04, 0.02, 0.23)
            shapes["darkbrow"] = shape(0.27, 0.43, 0.045, 0.011, 0.02, 0.24)
            shapes["prop"] = shape(0.84, 0.88, 0.09, 0.028, 0.06)
        elif name == "panda":
            shapes["body"] = shape(0.48, 0.67, 0.21, 0.16, 0.21)
            shapes["tail"] = shape(0.79, 0.74, 0.18, 0.07, 0.10)
            shapes["facewhite"] = shape(0.24, 0.50, 0.11, 0.065, 0.025, 0.25)
            shapes["eye1"] = shape(0.20, 0.47, 0.019, 0.023, 0.02, 0.29)
            shapes["eyelight"] = shape(0.195, 0.465, 0.006, 0.007, 0.01, 0.32)
            shapes["nose"] = shape(0.115, 0.55, 0.018, 0.013, 0.02, 0.30)
            for n in range(4):
                shapes[f"dark{n}"] = shape(0.70 + n * 0.06, 0.74, 0.014, 0.06, 0.02, 0.12)
            shapes["prop"] = shape(0.84, 0.85, 0.07, 0.02, 0.05)
            shapes["propleaf"] = shape(0.84, 0.81, 0.10, 0.02, 0.04)
        elif name == "dog":
            shapes["body"] = shape(0.50, 0.65, 0.23, 0.12, 0.19)
            shapes["ear1"] = shape(0.18, 0.36, 0.045, 0.07, 0.10)
            shapes["ear2"] = shape(0.30, 0.37, 0.041, 0.065, 0.09)
            shapes["paw1"] = shape(0.32, 0.79, 0.018, 0.10, 0.08)
            shapes["paw2"] = shape(0.65, 0.79, 0.022, 0.10, 0.08)
            shapes["tail"] = shape(0.77, 0.72, 0.11, 0.035, 0.06)
            shapes["white0"] = shape(0.84, 0.72, 0.04, 0.034, 0.02, 0.08)
            for n, (x, y) in enumerate(((0.39, 0.61), (0.48, 0.71), (0.58, 0.63), (0.65, 0.68))):
                shapes[f"dark{n}"] = shape(x, y, 0.035, 0.030, 0.02, 0.195)
            shapes["white1"] = shape(0.55, 0.65, 0.027, 0.042, 0.02, 0.20)
        else:
            for n in range(12):
                shapes[f"dark{n}"] = shape(
                    0.37 + (n % 6) * 0.06,
                    0.62 + (n // 6) * 0.085,
                    0.013,
                    0.012,
                    0.02,
                    0.22,
                )
            if name == "lynx":
                shapes["tail"] = shape(0.76, 0.70, 0.055, 0.033, 0.05)
                shapes["ear1"] = shape(0.19, 0.38, 0.03, 0.06, 0.09)
                shapes["ear2"] = shape(0.30, 0.39, 0.028, 0.055, 0.08)
                shapes["ear3"] = shape(0.19, 0.315, 0.007, 0.04, 0.04)
                shapes["ear4"] = shape(0.30, 0.33, 0.007, 0.035, 0.04)
                shapes["facewhite"] = shape(0.29, 0.56, 0.055, 0.06, 0.035, 0.23)
            elif name == "thylacine":
                for n in range(12):
                    shapes.pop(f"dark{n}")
                for n in range(6):
                    shapes[f"dark{n}"] = shape(0.53 + n * 0.03, 0.65, 0.008, 0.09, 0.018, 0.21)
                shapes["tail"] = shape(0.81, 0.75, 0.17, 0.022, 0.055)
                shapes["face"] = shape(0.145, 0.54, 0.095, 0.033, 0.085, 0.14)
    elif name == "rhino":
        shapes.update({
            "body": shape(0.53, 0.63, 0.26, 0.18, 0.23),
            "head": shape(0.23, 0.55, 0.14, 0.13, 0.18, 0.04),
            "neck": shape(0.34, 0.58, 0.10, 0.13, 0.17),
            "face": shape(0.13, 0.63, 0.09, 0.04, 0.07, 0.14),
            "nose": shape(0.08, 0.62, 0.017, 0.017, 0.025, 0.235),
            "horn1": shape(0.10, 0.51, 0.023, 0.08, 0.07),
            "ear1": shape(0.23, 0.39, 0.025, 0.05, 0.07),
            "ear2": shape(0.32, 0.42, 0.025, 0.045, 0.07),
            "eye1": shape(0.22, 0.53, 0.017, 0.019, 0.02, 0.245),
            "eyelight": shape(0.215, 0.525, 0.005, 0.006, 0.01, 0.275),
            "tail": shape(0.80, 0.74, 0.013, 0.09, 0.04),
            "prop": shape(0.85, 0.88, 0.12, 0.024, 0.03),
        })
        for n in range(3):
            shapes[f"darkfold{n}"] = shape(0.40 + n * 0.10, 0.66, 0.007, 0.12, 0.01, 0.235)
    elif name == "elephant":
        shapes = {
            "body": shape(0.55, 0.62, 0.24, 0.18, 0.23),
            "head": shape(0.28, 0.53, 0.14, 0.14, 0.20, 0.04),
            "neck": shape(0.36, 0.59, 0.10, 0.12, 0.17),
            "ear1": shape(0.35, 0.55, 0.075, 0.12, 0.07, 0.20),
            "ear2": shape(0.35, 0.42, 0.065, 0.05, 0.08),
            "face": shape(0.17, 0.62, 0.045, 0.085, 0.12, 0.08),
            "nose": shape(0.14, 0.76, 0.027, 0.145, 0.08, 0.10),
            "nosetip": shape(0.115, 0.87, 0.045, 0.027, 0.065, 0.11),
            "eye1": shape(0.235, 0.505, 0.018, 0.021, 0.02, 0.26),
            "eyelight": shape(0.23, 0.50, 0.006, 0.006, 0.01, 0.29),
            "facewhite": shape(0.17, 0.68, 0.055, 0.013, 0.04, 0.22),
            "paw1": shape(0.39, 0.81, 0.038, 0.09, 0.08),
            "paw2": shape(0.69, 0.81, 0.043, 0.09, 0.08),
            "foot1": shape(0.39, 0.90, 0.043, 0.015, 0.07),
            "foot2": shape(0.69, 0.90, 0.048, 0.015, 0.07),
            "tail": shape(0.785, 0.74, 0.016, 0.10, 0.05),
            "prop": shape(0.85, 0.88, 0.10, 0.027, 0.04),
            "propleaf": shape(0.85, 0.855, 0.085, 0.020, 0.03),
        }
    elif name in (
        "orangutan",
        "gorilla",
        "bonobo",
        "lemur",
        "aye",
        "tamarin",
        "macaque",
    ):
        shapes = {
            "body": shape(0.49, 0.62, 0.15, 0.20, 0.22),
            "head": shape(0.38, 0.32, 0.105, 0.10, 0.18, 0.05),
            "neck": shape(0.43, 0.43, 0.08, 0.10, 0.17),
            "face": shape(0.35, 0.345, 0.075, 0.065, 0.035, 0.22),
            "eye1": shape(0.32, 0.31, 0.018, 0.018, 0.02, 0.27),
            "eyelight": shape(0.315, 0.305, 0.006, 0.006, 0.01, 0.30),
            "nose": shape(0.31, 0.36, 0.025, 0.013, 0.02, 0.28),
            "ear1": shape(0.27, 0.32, 0.02, 0.03, 0.05),
            "ear2": shape(0.475, 0.32, 0.02, 0.03, 0.05),
            "shoulder1": shape(0.39, 0.48, 0.10, 0.09, 0.16),
            "shoulder2": shape(0.59, 0.48, 0.10, 0.08, 0.15),
            "paw1": shape(0.29, 0.62, 0.034, 0.23, 0.10),
            "paw2": shape(0.66, 0.61, 0.032, 0.22, 0.10),
            "foot1": shape(0.28, 0.84, 0.045, 0.035, 0.08),
            "foot2": shape(0.65, 0.83, 0.045, 0.035, 0.08),
            "leg1": shape(0.43, 0.82, 0.05, 0.06, 0.10),
            "leg2": shape(0.56, 0.82, 0.055, 0.055, 0.10),
            "prop": shape(0.85, 0.81, 0.016, 0.10, 0.03),
            "propflower": shape(0.85, 0.70, 0.05, 0.038, 0.04),
        }
        for n in range(3):
            cuts[f"finger{n}"] = shape(0.255 + n * 0.017, 0.86, 0.003, 0.024)
        if name in ("gorilla", "bonobo"):
            shapes["body"] = shape(0.49, 0.63, 0.19 if name == "gorilla" else 0.14, 0.21, 0.23)
            shapes["head"] = shape(0.38, 0.33, 0.115, 0.12, 0.19, 0.05)
            shapes["darkface"] = shape(0.35, 0.345, 0.085, 0.065, 0.04, 0.215)
            shapes["nose"] = shape(0.32, 0.36, 0.03, 0.023, 0.025, 0.275)
            shapes["eye1"] = shape(0.31, 0.31, 0.017, 0.018, 0.02, 0.275)
            shapes["eyelight"] = shape(0.305, 0.305, 0.005, 0.006, 0.01, 0.31)
            if name == "gorilla":
                shapes["white0"] = shape(0.56, 0.54, 0.075, 0.15, 0.02, 0.22)
        elif name != "orangutan":
            cuts.clear()
            for key in ("leg1", "leg2"):
                shapes.pop(key)
            shapes.update({
                "body": shape(0.49, 0.68, 0.20, 0.125, 0.21),
                "head": shape(0.25, 0.50, 0.10, 0.10, 0.18, 0.05),
                "neck": shape(0.33, 0.59, 0.085, 0.11, 0.15),
                "face": shape(0.17, 0.565, 0.07, 0.03, 0.065, 0.16),
                "eye1": shape(0.22, 0.49, 0.018, 0.021, 0.02, 0.25),
                "eyelight": shape(0.215, 0.485, 0.005, 0.006, 0.01, 0.28),
                "nose": shape(0.11, 0.56, 0.016, 0.014, 0.02, 0.245),
                "ear1": shape(0.20, 0.40, 0.025, 0.038, 0.07),
                "ear2": shape(0.32, 0.43, 0.025, 0.034, 0.07),
                "shoulder1": shape(0.34, 0.67, 0.065, 0.09, 0.15),
                "shoulder2": shape(0.61, 0.68, 0.065, 0.08, 0.14),
                "paw1": shape(0.33, 0.78, 0.024, 0.085, 0.08),
                "paw2": shape(0.65, 0.78, 0.027, 0.08, 0.08),
                "foot1": shape(0.30, 0.855, 0.047, 0.021, 0.065),
                "foot2": shape(0.65, 0.85, 0.046, 0.022, 0.065),
            })
            shapes["tail"] = shape(0.78, 0.61, 0.045, 0.22, 0.08)
            if name == "lemur":
                for n in range(7):
                    shapes[f"darktail{n}"] = shape(
                        0.78, 0.43 + n * 0.058, 0.043, 0.013, 0.02, 0.085
                    )
                shapes["facewhite"] = shape(0.24, 0.53, 0.09, 0.07, 0.025, 0.24)
                shapes["eye1"] = shape(0.22, 0.49, 0.018, 0.021, 0.02, 0.28)
                shapes["eyelight"] = shape(0.215, 0.485, 0.005, 0.006, 0.01, 0.31)
            elif name == "aye":
                shapes["ear1"] = shape(0.16, 0.41, 0.055, 0.07, 0.08)
                shapes["ear2"] = shape(0.34, 0.43, 0.05, 0.07, 0.08)
                shapes["finger0"] = shape(0.285, 0.79, 0.008, 0.07, 0.025, 0.06)
                shapes["tail"] = shape(0.80, 0.69, 0.13, 0.075, 0.10)
                shapes["prop"] = shape(0.85, 0.84, 0.11, 0.026, 0.04)
                cuts["hollow"] = shape(0.85, 0.84, 0.07, 0.008)
            elif name == "tamarin":
                shapes["head"] = shape(0.25, 0.50, 0.13, 0.14, 0.13, 0.025)
                shapes["darkface"] = shape(0.23, 0.53, 0.07, 0.065, 0.035, 0.23)
                shapes["eye1"] = shape(0.22, 0.49, 0.018, 0.021, 0.02, 0.28)
                shapes["eyelight"] = shape(0.215, 0.485, 0.005, 0.006, 0.01, 0.31)
            elif name == "macaque":
                shapes["facewhite"] = shape(0.25, 0.51, 0.13, 0.13, 0.07, 0.08)
                shapes["darkface"] = shape(0.23, 0.53, 0.075, 0.065, 0.035, 0.24)
                shapes["eye1"] = shape(0.22, 0.49, 0.018, 0.021, 0.02, 0.285)
                shapes["eyelight"] = shape(0.215, 0.485, 0.005, 0.006, 0.01, 0.315)
                shapes["darktailtip"] = shape(0.78, 0.82, 0.045, 0.045, 0.04, 0.08)
    elif name in ("seacow", "vaquita", "whale", "dolphin"):
        shapes = {
            "body": shape(0.49, 0.56, 0.29, 0.14, 0.23),
            "head": shape(0.23, 0.54, 0.13, 0.105, 0.18, 0.04),
            "face": shape(0.13, 0.565, 0.065, 0.035, 0.06, 0.15),
            "nose": shape(0.09, 0.565, 0.014, 0.014, 0.02, 0.22),
            "eye1": shape(0.20, 0.51, 0.017, 0.019, 0.02, 0.23),
            "eyelight": shape(0.196, 0.505, 0.005, 0.006, 0.01, 0.26),
            "paw1": shape(0.37, 0.70, 0.045, 0.11, 0.09, 0.02),
            "paw2": shape(0.45, 0.45, 0.03, 0.06, 0.07, -0.025),
            "tail": shape(0.78, 0.57, 0.15, 0.05, 0.09),
            "tailupper": shape(0.89, 0.51, 0.06, 0.07, 0.06),
            "taillower": shape(0.89, 0.63, 0.06, 0.07, 0.06),
            "prop": shape(0.85, 0.87, 0.11, 0.025, 0.045),
            "propleaf": shape(0.85, 0.79, 0.027, 0.10, 0.035),
        }
        if name == "dolphin":
            shapes["beak1"] = shape(0.10, 0.56, 0.095, 0.017, 0.045, 0.10)
            shapes["nose"] = shape(0.018, 0.56, 0.008, 0.008, 0.01, 0.17)
            shapes["paw2"] = shape(0.48, 0.41, 0.034, 0.05, 0.075)
        elif name == "vaquita":
            shapes["darkeye"] = shape(0.20, 0.51, 0.035, 0.029, 0.02, 0.215)
            shapes["paw2"] = shape(0.50, 0.40, 0.045, 0.09, 0.08)
            shapes["white0"] = shape(0.46, 0.65, 0.21, 0.04, 0.025, 0.235)
        elif name == "whale":
            shapes["head"] = shape(0.24, 0.545, 0.19, 0.11, 0.18, 0.04)
            shapes["face"] = shape(0.10, 0.59, 0.07, 0.024, 0.05, 0.14)
            shapes["paw2"] = shape(0.70, 0.425, 0.025, 0.04, 0.05)
            for n in range(4):
                shapes[f"white{n}"] = shape(
                    0.39 + n * 0.07, 0.57 + 0.025 * sin(n), 0.017, 0.013, 0.014, 0.24
                )
        else:
            shapes["body"] = shape(0.49, 0.57, 0.30, 0.19, 0.235)
            shapes.pop("paw2")
            shapes["face"] = shape(0.13, 0.585, 0.07, 0.05, 0.07, 0.14)
            shapes["propleaf"] = shape(0.85, 0.77, 0.035, 0.14, 0.04)
    elif name in ("gharial", "axolotl", "turtle"):
        shapes = {
            "body": shape(0.49, 0.67, 0.23, 0.105, 0.20),
            "head": shape(0.23, 0.61, 0.10, 0.07, 0.15, 0.04),
            "neck": shape(0.31, 0.65, 0.09, 0.05, 0.12),
            "face": shape(0.145, 0.63, 0.06, 0.025, 0.05, 0.13),
            "eye1": shape(0.22, 0.595, 0.014, 0.018, 0.025, 0.215),
            "eyelight": shape(0.216, 0.59, 0.005, 0.005, 0.01, 0.245),
            "nose": shape(0.10, 0.63, 0.012, 0.008, 0.02, 0.20),
            "paw1": shape(0.33, 0.76, 0.07, 0.035, 0.09, 0.03),
            "paw2": shape(0.65, 0.77, 0.07, 0.035, 0.085, 0.025),
            "foot1": shape(0.29, 0.79, 0.045, 0.023, 0.07, 0.04),
            "foot2": shape(0.68, 0.79, 0.045, 0.024, 0.07, 0.035),
            "tail": shape(0.78, 0.69, 0.20, 0.03, 0.09),
            "prop": shape(0.85, 0.88, 0.11, 0.028, 0.04),
        }
        if name == "gharial":
            shapes["face"] = shape(0.115, 0.63, 0.115, 0.018, 0.05, 0.12)
            shapes["nose"] = shape(0.025, 0.625, 0.025, 0.019, 0.035, 0.19)
            for n in range(7):
                shapes[f"scale{n}"] = shape(0.36 + n * 0.05, 0.58, 0.018, 0.018, 0.04, 0.09)
        elif name == "axolotl":
            shapes["head"] = shape(0.22, 0.60, 0.14, 0.105, 0.17, 0.04)
            shapes["tail"] = shape(0.77, 0.63, 0.20, 0.065, 0.09)
            shapes["propflower"] = shape(0.85, 0.81, 0.04, 0.04, 0.03)
            for n in range(3):
                shapes[f"ear{n}"] = shape(
                    0.32 + n * 0.021, 0.45 + n * 0.034, 0.055, 0.009, 0.04, 0.075
                )
                shapes[f"ear{n + 3}"] = shape(
                    0.13 - n * 0.019, 0.45 + n * 0.034, 0.038, 0.009, 0.04, 0.075
                )
        else:
            shapes["body"] = shape(0.50, 0.61, 0.24, 0.17, 0.235)
            shapes["tail"] = shape(0.75, 0.70, 0.06, 0.014, 0.035)
            shapes["paw1"] = shape(0.34, 0.76, 0.06, 0.11, 0.08)
            shapes["paw2"] = shape(0.69, 0.73, 0.09, 0.07, 0.08)
            shapes["face"] = shape(0.14, 0.63, 0.055, 0.029, 0.055, 0.14)
            for row in range(3):
                for col in range(4):
                    shapes[f"dark{row}{col}"] = shape(
                        0.37 + col * 0.075,
                        0.52 + row * 0.075,
                        0.028,
                        0.008,
                        0.013,
                        0.24,
                    )
            shapes["propflower"] = shape(0.85, 0.80, 0.05, 0.045, 0.04)
    water = name in (
        "seacow",
        "vaquita",
        "whale",
        "dolphin",
        "gharial",
        "axolotl",
        "turtle",
    )
    grass = name in ("bustard", "florican", "horse", "tahr")
    if water or name in (
        "mink",
        "otter",
        "auk",
        "melomys",
        "paddlefish",
        "crayfish",
        "penguin",
    ):
        for n in range(3):
            shapes[f"scenewater{n}"] = shape(0.23 + n * 0.3, 0.94, 0.10, 0.005, 0.01, -0.12)
    if water:
        for n in range(4):
            shapes[f"scenewatercurrent{n}"] = shape(
                0.17 + n * 0.22, 0.28 + 0.025 * sin(n), 0.065, 0.005, 0.01, -0.15
            )
        for n in range(3):
            shapes[f"sceneleafkelp{n}"] = shape(
                0.92 + n * 0.018, 0.77 - n * 0.06, 0.014, 0.10, 0.025, -0.12
            )
    elif grass:
        for n in range(6):
            shapes[f"sceneleafgrass{n}"] = shape(
                0.76 + n * 0.035, 0.77 - 0.035 * sin(n), 0.005, 0.10, 0.025, -0.14
            )
        if name == "tahr":
            shapes["scenerock"] = shape(0.81, 0.82, 0.18, 0.09, 0.035, -0.12)
    elif name in ("auk", "melomys", "paddlefish", "penguin", "lynx"):
        shapes["scenerock"] = shape(0.87, 0.72, 0.08, 0.06, 0.025, -0.15)
    elif name in ("mink", "otter", "bee", "crayfish"):
        for n in range(3):
            shapes[f"sceneleafreed{n}"] = shape(
                0.06 + n * 0.03, 0.72 - n * 0.05, 0.007, 0.10, 0.02, -0.12
            )
    else:
        shapes["scenetreebranch"] = shape(0.78, 0.20, 0.19, 0.009, 0.015, -0.15)
        shapes["scenetreetrunk"] = shape(0.965, 0.43, 0.018, 0.24, 0.02, -0.18)
        dry = name in ("numbat", "quoll", "potoroo", "dog")
        for n in range(7):
            shapes[f"sceneleafcanopy{n}"] = shape(
                0.61 + n * 0.05,
                0.18 + 0.04 * sin(n * 2),
                0.024 if dry else 0.037,
                0.045 if dry else 0.025,
                0.025,
                -0.12,
            )
        for n in range(3):
            shapes[f"sceneleafground{n}"] = shape(
                0.89 + n * 0.035,
                0.76 + n * 0.04,
                0.045 if dry else 0.032,
                0.012 if dry else 0.026,
                0.02,
                -0.12,
            )
    if name != "huia":
        shapes["sceneground"] = shape(0.51, 0.93, 0.46, 0.013, 0.02, -0.18)
    if name == "bee":
        shapes["foot3"] = shape(0.35, 0.68, 0.009, 0.055, 0.035, -0.02)
        for n in range(3):
            shapes[f"propflowerpetal{n}"] = shape(
                0.775 + n * 0.035, 0.64 + 0.018 * sin(n * 2), 0.028, 0.025, 0.035
            )
    x, y, rx, ry, depth, front, _ = shapes["eye1"]
    shapes["eye1"] = shape(x, y, rx * 1.45, ry * 1.45, depth, front)
    x, y, rx, ry, depth, front, _ = shapes["eyelight"]
    dot = (
        (round(x * WIDTH - 0.5) + 0.5) / WIDTH,
        (round(y * HEIGHT - 0.5) + 0.5) / HEIGHT,
    )
    if surface(*dot, shapes["eyelight"]) is None:
        # Keep sub-pixel eye glints visible on the fixed braille grid
        shapes["eyelight"] = shape(x, y, max(rx, 0.009), max(ry, 0.011), depth, front)
    if name not in (
        "bee",
        "huia",
        "auk",
        "penguin",
        "crayfish",
        "bustard",
        "florican",
        "vulture",
        "dodo",
        "pigeon",
        "parakeet",
        "kakapo",
        "eagle",
    ):
        x, y, rx, ry, depth, front, _ = shapes["face"]
        shapes["facemouth"] = shape(x, y + ry * 0.5, rx * 0.6, 0.004, 0.015, front + depth + 0.005)
        x, y, _, _, _, front, _ = shapes["eye1"]
        shapes["eye2"] = shape(x + 0.065, y + 0.006, 0.017, 0.023, 0.015, front - 0.015)
        shapes["eyelight2"] = shape(x + 0.060, y, 0.005, 0.006, 0.01, front + 0.015)
    animals[name] = shapes, cuts


def pose(name: str, shapes: Model, cuts: Model, action: str, phase: float) -> dict[str, str]:
    """Move attached features around joints before sampling the whole sculpture"""
    original = shapes | cuts
    moved = dict(original)
    strength = (1 - cos(phase * pi)) / 2 if action in ("look", "listen") else sin(phase * pi) ** 2
    if action in FOREST[name]["idle"].split()[:4]:
        strength = sin(phase * pi) ** 0.6
    action = action.partition("-")[2] or action

    def move(
        keys: Iterable[str], dx: float = 0, dy: float = 0, sx: float = 1, sy: float = 1
    ) -> None:
        for key in keys:
            if key in moved:
                x, y, rx, ry, depth, front, angle = moved[key]
                moved[key] = (
                    x + dx * strength,
                    y + dy * strength,
                    rx * (1 + (sx - 1) * strength),
                    ry * (1 + (sy - 1) * strength),
                    depth,
                    front,
                    angle,
                )

    def turn(keys: Iterable[str], pivot: tuple[float, float], angle: float) -> None:
        angle *= strength
        for key in keys:
            if key in moved:
                x, y, rx, ry, depth, front, old = moved[key]
                dx, dy = x - pivot[0], y - pivot[1]
                moved[key] = (
                    pivot[0] + dx * cos(angle) - dy * sin(angle),
                    pivot[1] + dx * sin(angle) + dy * cos(angle),
                    rx,
                    ry,
                    depth,
                    front,
                    old + angle,
                )

    head = [
        key
        for key in original
        if key.startswith((
            "head",
            "ear",
            "horn",
            "face",
            "eye",
            "nose",
            "antenna",
            "beak",
            "whisker",
            "bill",
        ))
    ]
    body = [key for key in original if not key.startswith(("prop", "scene"))]
    pivot = (
        (0.32, 0.55)
        if name == "saola"
        else (0.36, 0.43)
        if name == "huia"
        else (0.45, 0.43)
        if name == "auk"
        else shapes["neck"][:2]
        if "neck" in shapes
        else shapes["head"][:2]
    )
    if action in ("blink", "pet", "nap") and name != "bee":
        move(("eye1", "eyelight", "eye2", "eyelight2"), sy=0.15)
    if action == "blink" and name == "bee":
        turn(("ear1", "antenna1"), (0.25, 0.43), -0.4)
    if action in ("look", "listen", "peek"):
        turn(
            head,
            pivot,
            0.10 if action == "look" else 0.07 if action == "listen" else -0.12,
        )
    elif action == "ears":
        for key, angle in (
            ("ear1", -0.30),
            ("ear2", 0.25),
            ("horn1", -0.08),
            ("horn2", -0.08),
        ):
            if key in moved:
                x, y, _, ry, *_ = moved[key]
                turn((key,), (x, y + ry), angle)
        turn(("antenna1",), (0.25, 0.43), -0.4)
    elif action == "pet":
        turn(head, pivot, -0.16)
        move(("tail",), dy=-0.035)
    elif action == "nap":
        move(body, dy=0.035, sy=0.87)
        move(head, dy=0.025)
    elif action in ("play", "object"):
        if name not in ("saola", "auk", "bee"):
            turn(("paw1", "foot1"), (0.31, 0.72), 0.25)
        move(("tail",), dx=0.03, dy=-0.035)
        turn(head, pivot, -0.18)
    elif action == "breathe":
        move(body, dy=-0.012 if name == "bee" else -0.009, sy=1.01)
        move([key for key in shapes if key.startswith("sceneleaf")], dx=0.008)
    elif action in ("wander", "stalk", "prowl", "amble", "waddle"):
        move(body, dx=-0.12, dy=-0.016 * cos(phase * 6 * pi))
        turn(
            ("paw1", "foot1"),
            (0.31 - 0.12 * strength, 0.72),
            0.30 * sin(phase * 8 * pi),
        )
        turn(
            ("paw2", "foot2"),
            (0.64 - 0.12 * strength, 0.72),
            -0.25 * sin(phase * 8 * pi),
        )
        turn(("tail",), (0.66 - 0.12 * strength, 0.68), 0.20 * sin(phase * 4 * pi))
        if name == "auk":
            move(("paw1",), dx=0.04, dy=-0.025 * sin(phase * 8 * pi))
    elif action in ("forage", "probe", "browse", "sniff", "dig"):
        turn(
            head,
            pivot,
            -0.18 - 0.09 * sin(phase * 8 * pi) if name != "saola" else -0.85,
        )
        move(("paw1",), dx=0.04, dy=-0.04 * sin(phase * 10 * pi))
        move(("tail",), dy=-0.04)
        if name == "solenodon" and action == "dig":
            move(("paw2",), dx=0.065, dy=-0.075 * sin(phase * 8 * pi), sy=0.6)
    elif action == "flutter":
        move(body, dx=-0.08, dy=-0.10)
        turn(
            ("paw1", "feather0", "feather1", "feather2"),
            (0.43 - 0.08 * strength, 0.50 - 0.10 * strength),
            -0.9 * sin(phase * 8 * pi),
        )
        turn(
            ("paw2",),
            (0.51 - 0.08 * strength, 0.50 - 0.10 * strength),
            0.9 * sin(phase * 8 * pi),
        )
    elif action in ("slide", "swim"):
        move(body, dx=-0.10 - 0.045 * sin(phase * 2 * pi), dy=0.065)
        turn(head, pivot, -0.12)
        move(("body", "white0"), sx=1.2, sy=0.75)
        move(("tail",), dx=0.04, dy=0.025 * sin(phase * 8 * pi))
    elif action in ("groom", "wash"):
        turn(head, pivot, -0.18)
        move(("paw1",), dx=0.025, dy=-0.15 - 0.03 * sin(phase * 8 * pi), sy=0.65)
        move(("tail",), dx=0.03 * sin(phase * 8 * pi))
    elif action == "orbit":
        move(body, dx=-0.12 * cos(phase * 2 * pi), dy=-0.05 - 0.04 * sin(phase * 2 * pi))
        move(("paw1",), sx=0.8, sy=0.65 + 0.2 * sin(phase * 12 * pi))
        move(("paw2",), sx=0.8, sy=0.65 - 0.2 * sin(phase * 12 * pi))
    elif action == "land":
        move(body, dx=0.20, dy=0.02)
        move(("paw1", "paw2"), sx=0.55, sy=0.65)
        move(head, dx=0.035 * sin(phase * 6 * pi), dy=0.015)
    elif action == "curl":
        turn(head, (0.42, 0.68), -1.1)
        move(("body",), sx=0.85, sy=1.15)
        move(("tail",), dx=-0.16, dy=-0.06, sx=0.6, sy=2)
        move(("paw1", "paw2", "foot1", "foot2"), dx=0.08, dy=-0.055, sy=0.6)
    elif action in ("sunbathe", "wriggle", "bob"):
        turn(body, (0.48, 0.73), 0.12 * sin(phase * 6 * pi))
        turn(head, pivot, 0.12)
        move(("tail",), dy=0.025 * sin(phase * 8 * pi))
    elif action in ("shake", "shakeoff", "tailfan"):
        turn(body, (0.48, 0.70), 0.10 * sin(phase * 12 * pi))
        turn(("tail",), (0.64, 0.70), 0.35 * sin(phase * 10 * pi))
    elif action in ("retreat", "climb", "hop"):
        move(body, dx=0.07 * phase, dy=-0.05 * sin(phase * pi))
        turn(head, pivot, 0.15 * sin(phase * 6 * pi))
        turn(
            ("paw1", "foot1"),
            (0.31 + 0.07 * phase * strength, 0.72),
            0.35 * sin(phase * 6 * pi),
        )
    elif action in ("earturn", "inspect", "sniffrock", "root"):
        turn(head, pivot, 0.22 * sin(phase * 6 * pi))
        turn(("tail",), (0.64, 0.70), -0.2 * sin(phase * 4 * pi))
        turn(("face", "nose", "facemouth"), (0.22, 0.55), 0.1 * sin(phase * 12 * pi))
    elif action in ("dive", "unroll"):
        move(body, dx=-0.13 * phase, dy=0.05 * sin(phase * pi))
        turn(head, pivot, -0.2 * sin(phase * 4 * pi))
        turn(("tail",), (0.64 - 0.13 * phase * strength, 0.70), 0.3 * sin(phase * 6 * pi))
    elif action in ("clean", "fan"):
        turn(("ear1", "antenna1"), (0.25, 0.43), -0.65 * sin(phase * 6 * pi))
        turn(("ear2", "antenna2"), (0.31, 0.43), 0.65 * sin(phase * 6 * pi))
        move(("paw1", "paw2"), sy=0.65 + 0.25 * sin(phase * 12 * pi))
    elif action == "preen":
        turn(head, pivot, -0.45 * sin(phase * 4 * pi))
        turn(("paw1",), (0.51, 0.52), -0.15)
    elif action in ("bound", "scamper", "scuttle"):
        move(
            body,
            dx=-0.11,
            dy=-0.09 * abs(sin(phase * 4 * pi)) if name == "potoroo" else 0,
        )
        turn(("paw1", "foot1"), (0.33, 0.74), 0.4 * sin(phase * 10 * pi))
        turn(("paw2", "foot2"), (0.61, 0.78), -0.35 * sin(phase * 10 * pi))
        move(("tail",), dy=0.035 * sin(phase * 8 * pi))
    elif action in ("scratch", "sniffseed", "nibble", "nest"):
        turn(head, pivot, -0.22 - 0.10 * sin(phase * 10 * pi))
        move(("paw1", "foot1"), dx=-0.025, dy=-0.055 * sin(phase * 12 * pi))
        if action == "nest":
            move(body, dx=0.07, dy=0.035, sy=0.86)
        if action == "nibble":
            turn(("face", "nose", "facemouth"), (0.22, 0.55), 0.15 * sin(phase * 16 * pi))
    elif action in ("stretch", "dust", "bask", "coil"):
        move(body, sx=1.10 if action in ("stretch", "bask") else 0.93, sy=0.90)
        turn(("tail",), (0.70, 0.74), 0.5 * sin(phase * 4 * pi))
        turn(head, pivot, 0.14 * sin(phase * 6 * pi))
    elif action == "tongue":
        move(("face", "nose", "facemouth"), dx=-0.022 * sin(phase * 12 * pi))
        turn(head, (0.30, 0.69), -0.12)
    elif action in ("cruise", "finroll", "turn", "eddy"):
        move(body, dx=-0.08 * sin(phase * pi), dy=-0.08 * sin(phase * 2 * pi))
        turn(
            ("tail", "tailupper", "taillower"),
            (0.71, 0.54),
            0.35 * sin(phase * 10 * pi),
        )
        turn(("paw1", "paw2"), (0.53, 0.54), 0.20 * sin(phase * 8 * pi))
        if action in ("turn", "eddy"):
            turn(body, (0.52, 0.54), 0.18 * sin(phase * 2 * pi))
        if action == "finroll":
            move(("paw1", "paw2"), sx=0.7, sy=1.3)
    elif action in ("crouch", "leap", "croak", "settle"):
        if action == "leap":
            move(body, dx=-0.08, dy=-0.19)
            turn(("paw2", "foot2"), (0.60, 0.71), -0.55)
        elif action == "croak":
            move(("face", "white0"), sy=1.25 + 0.20 * sin(phase * 8 * pi))
        else:
            move(body, dy=0.03, sy=0.90)
            turn(head, (0.40, 0.63), 0.09 * sin(phase * 6 * pi))
            move(("paw1", "foot1"), dx=0.035 * sin(phase * 8 * pi))
    elif action in ("emerge", "excavate", "clawwave", "tuck"):
        move(body, dx=0.08 if action == "tuck" else -0.08 * sin(phase * pi))
        for key in ("paw1", "claw1", "pincer1"):
            turn((key,), (0.29, 0.72), 0.5 * sin(phase * 8 * pi))
        for key in ("paw2", "claw2", "pincer2"):
            turn((key,), (0.30, 0.52), -0.35 * sin(phase * 6 * pi))
        move(("leg0", "leg1", "leg2"), dy=0.035 * sin(phase * 12 * pi))
        if action == "excavate":
            move(("claw1", "pincer1"), dx=-0.035 * sin(phase * 10 * pi))
    elif action in ("pad", "stalkgrass", "stretchcat", "tailflick"):
        move(body, dx=-0.09 if action in ("pad", "stalkgrass") else 0, sy=0.93)
        turn(head, pivot, -0.12 * sin(phase * 6 * pi))
        turn(("tail",), (0.68, 0.71), 0.45 * sin(phase * 8 * pi))
        turn(("paw1", "foot1"), (0.31, 0.73), 0.25 * sin(phase * 8 * pi))
        if action == "stretchcat":
            move(("paw1", "foot1"), dx=-0.08, dy=0.015)
            move(("body",), sx=1.10, sy=0.86)
    elif action in ("trundle", "trunkcurl", "earfan", "graze"):
        move(body, dx=-0.08 if action == "trundle" else 0)
        turn(("nose", "nosetip"), (0.16, 0.64), 0.35 * sin(phase * 4 * pi))
        if action == "earfan":
            move(("ear1", "ear2"), sx=1.15, sy=1.08)
        elif action == "graze":
            turn(head, (0.36, 0.59), -0.14)
            move(("nosetip",), dx=0.04 * sin(phase * 6 * pi))
        else:
            move(("paw1", "foot1"), dy=-0.035 * sin(phase * 8 * pi))
            move(("paw2", "foot2"), dy=0.035 * sin(phase * 8 * pi))
    elif action in ("branchwalk", "bamboobite", "tailwrap", "pawclean"):
        move(body, dx=-0.09 if action == "branchwalk" else 0)
        turn(head, pivot, -0.20 * sin(phase * 4 * pi))
        turn(
            ("tail", "dark0", "dark1", "dark2", "dark3"),
            (0.66, 0.72),
            0.32 * sin(phase * 6 * pi),
        )
        if action == "tailwrap":
            move(("tail",), dx=-0.04, sy=1.35)
        else:
            move(("paw1",), dx=0.03, dy=-0.10 * abs(sin(phase * 6 * pi)))
    elif action in ("trot", "playbow", "perk", "packcall"):
        move(body, dx=-0.11 if action == "trot" else 0)
        turn(("ear1",), (0.18, 0.42), -0.35 * sin(phase * 6 * pi))
        turn(head, pivot, 0.18 * sin(phase * 4 * pi))
        if action == "playbow":
            move(head, dy=0.05)
            move(("paw1", "foot1"), dx=-0.05, sy=0.80)
        else:
            turn(("paw1", "foot1"), (0.32, 0.72), 0.35 * sin(phase * 10 * pi))
            turn(("paw2", "foot2"), (0.65, 0.72), -0.35 * sin(phase * 10 * pi))
    elif action in ("reach", "swing", "fruit", "knucklewalk"):
        move(body, dx=-0.07, dy=-0.04 if action == "swing" else 0)
        turn(
            ("paw1", "foot1", "finger0", "finger1", "finger2"),
            (0.35, 0.47),
            0.65 * sin(phase * 4 * pi),
        )
        turn(("paw2", "foot2"), (0.60, 0.48), -0.6 * sin(phase * 4 * pi))
        turn(head, (0.43, 0.43), 0.15 * sin(phase * 6 * pi))
        if action == "fruit":
            move(("paw1", "foot1"), dx=0.08, dy=-0.07)
    elif action in ("paddle", "roll", "greet", "bankwalk"):
        move(body, dx=-0.08 * sin(phase * pi), dy=0.04 * sin(phase * 4 * pi))
        turn(("tail",), (0.66, 0.72), 0.30 * sin(phase * 8 * pi))
        turn(head, pivot, 0.20 * sin(phase * 4 * pi))
        if action == "roll":
            move(("body", "white0"), sy=0.78, sx=1.05)
        else:
            move(("paw1", "foot1"), dy=-0.04 * sin(phase * 10 * pi))
    elif action in ("catpad", "catpounce", "catstretch", "scent", "jawyawn"):
        if action == "catpounce":
            move(body, dx=-0.10, dy=-0.14 * abs(sin(phase * 3 * pi)))
            turn(("paw1", "foot1"), (0.31, 0.72), -0.4 * sin(phase * 6 * pi))
        elif action == "catstretch":
            move(("body",), sx=1.12, sy=0.88)
            move(("paw1", "foot1"), dx=-0.065)
        else:
            move(body, dx=-0.085 if action == "catpad" else 0)
            turn(head, pivot, 0.18 * sin(phase * 6 * pi))
            if action == "jawyawn":
                move(("face", "facemouth"), dy=0.035, sy=1.6)
        turn(("tail",), (0.69, 0.70), 0.24 * sin(phase * 8 * pi))
    elif action in (
        "mudroll",
        "heavywalk",
        "earcheck",
        "maneshake",
        "hoofscrape",
        "hillscan",
        "rockstep",
    ):
        if action == "mudroll":
            move(body, dy=0.04, sy=0.82)
            turn(body, (0.48, 0.70), 0.15 * sin(phase * 6 * pi))
        elif action in ("heavywalk", "rockstep", "hoofscrape"):
            move(
                body,
                dx=-0.08 if action != "hoofscrape" else 0,
                dy=-0.045 if action == "rockstep" else 0,
            )
            turn(("paw1", "foot1"), shapes["paw1"][:2], 0.30 * sin(phase * 8 * pi))
            turn(("paw2", "foot2"), shapes["paw2"][:2], -0.25 * sin(phase * 8 * pi))
        else:
            turn(head, pivot, 0.16 * sin(phase * 6 * pi))
            turn(("ear1", "ear2"), shapes["head"][:2], 0.18 * sin(phase * 8 * pi))
            turn(("darkmane",), shapes["head"][:2], 0.10 * sin(phase * 10 * pi))
    elif action in (
        "chestdrum",
        "leafpick",
        "socialgroom",
        "branchreach",
        "branchleap",
        "sunpose",
        "tailwave",
        "woodtap",
        "cheekclean",
    ):
        if action in ("branchreach", "branchleap"):
            move(body, dx=-0.055, dy=-0.11 if action == "branchleap" else -0.025)
            turn(("paw1", "foot1"), shapes["shoulder1"][:2], 0.65 * sin(phase * 4 * pi))
            turn(("paw2", "foot2"), shapes["shoulder2"][:2], -0.45 * sin(phase * 4 * pi))
        elif action == "sunpose":
            turn(("paw1", "foot1"), shapes["shoulder1"][:2], 0.6)
            turn(("paw2", "foot2"), shapes["shoulder2"][:2], -0.6)
            turn(head, pivot, 0.20 * sin(phase * 2 * pi))
        else:
            turn(head, pivot, 0.15 * sin(phase * 4 * pi))
            move(
                ("paw1", "foot1", "finger0"),
                dx=0.025,
                dy=-0.12 - 0.035 * sin(phase * (14 if action == "woodtap" else 8) * pi),
            )
            if action == "chestdrum":
                move(("paw2", "foot2"), dx=-0.035, dy=-0.17 - 0.03 * sin(phase * 10 * pi))
        turn(
            [key for key in shapes if key.startswith(("tail", "darktail"))],
            (0.78, 0.70),
            0.25 * sin(phase * 6 * pi),
        )
    elif action in (
        "grassstride",
        "billtap",
        "neckdisplay",
        "dustbath",
        "leapdisplay",
        "soar",
        "neckscan",
        "wingdry",
        "doddle",
        "fruitpeck",
        "seedpeck",
        "branchhop",
        "crestshake",
        "tailshake",
        "boom",
        "mossbite",
        "wingshuffle",
        "splash",
    ):
        if action in ("soar", "leapdisplay", "branchhop"):
            move(
                body,
                dx=-0.06,
                dy=-0.16 if action == "soar" else -0.08 * abs(sin(phase * 4 * pi)),
            )
            turn(("paw1",), shapes["paw1"][:2], 0.6 * sin(phase * 8 * pi))
            turn(("paw2",), shapes["paw2"][:2], -0.4 * sin(phase * 8 * pi))
        elif action in ("doddle", "grassstride", "splash"):
            move(body, dx=-0.08, dy=0.014 * sin(phase * 8 * pi))
            move(("foot1",), dy=-0.035 * sin(phase * 8 * pi))
            move(("foot2",), dy=0.035 * sin(phase * 8 * pi))
            turn(head, pivot, 0.11 * sin(phase * 6 * pi))
        elif action in ("neckdisplay", "boom"):
            move(("neck", "white0"), sx=1.25, sy=1.05)
            turn(head, pivot, 0.20 * sin(phase * 4 * pi))
            move(("body",), sx=1.04)
        elif action in ("billtap", "fruitpeck", "seedpeck", "mossbite"):
            turn(head, pivot, -0.25 - 0.15 * sin(phase * 8 * pi))
            move(body, dx=-0.04)
        else:
            turn(head, pivot, 0.16 * sin(phase * 6 * pi))
            turn(("paw1", "paw2"), shapes["body"][:2], 0.18 * sin(phase * 8 * pi))
            turn(("tail",), shapes["body"][:2], 0.18 * sin(phase * 6 * pi))
            if action == "dustbath":
                move(body, dy=0.035, sy=0.92)
    elif action in (
        "riverglide",
        "echoturn",
        "surface",
        "finsweep",
        "kelpgraze",
        "tailglide",
        "reefglide",
        "shellturn",
        "deepturn",
        "gillfan",
        "lakewalk",
        "tailswish",
        "hover",
        "grounddig",
    ):
        aquatic = action != "grounddig"
        travel = min(
            0.09,
            max(
                0,
                min(shapes[key][0] - shapes[key][2] for key in body if key in shapes) - 0.015,
            ),
        )
        move(
            body,
            dx=-travel * sin(phase * pi),
            dy=-0.07 * sin(phase * 2 * pi) if aquatic else 0,
        )
        turn(head, pivot, 0.13 * sin(phase * 4 * pi))
        turn(
            ("tail", "tailupper", "taillower"),
            shapes["body"][:2],
            0.17 * sin(phase * 8 * pi),
        )
        turn(("paw1", "foot1"), shapes["body"][:2], 0.18 * sin(phase * 8 * pi))
        turn(("paw2", "foot2"), shapes["body"][:2], -0.14 * sin(phase * 8 * pi))
        if action == "surface":
            move(body, dy=-0.11)
        elif action in ("shellturn", "deepturn", "echoturn"):
            turn(body, shapes["body"][:2], 0.15 * sin(phase * 2 * pi))
        elif action == "gillfan":
            turn(
                [key for key in shapes if key.startswith("ear")],
                shapes["head"][:2],
                0.22 * sin(phase * 10 * pi),
            )
        elif action in ("kelpgraze", "grounddig"):
            turn(head, pivot, -0.24)
    if name == "bee" and action in ("ears", "pet", "play", "object", "breathe"):
        move(("paw1",), sy=0.6)
        move(("paw2",), sy=0.7)
        move(body, dy=-0.022)
    if name in ("huia", "auk", "penguin") and action in ("pet", "play", "ears"):
        move(("paw1",), dx=-0.025, sy=1.15)
    if name == "pangolin" and action == "pet":
        turn(head, pivot, -0.2)
        move(("tail",), dx=-0.055, sy=1.5)
    if action in ("ears", "pet", "play", "object"):
        if name == "saola":
            turn(head, pivot, 0.08)
            turn(("ear1",), (0.20, 0.35), -0.25)
            move(body, dx=0.018)
        elif name == "numbat":
            turn(("face", "nose", "facemouth"), (0.22, 0.54), 0.15 * sin(phase * 8 * pi))
            move(("tail",), dy=-0.045, sy=0.9)
        elif name == "quoll":
            turn(head, pivot, -0.1 * sin(phase * 6 * pi))
            turn(("ear1",), (0.20, 0.40), -0.25)
        elif name == "solenodon":
            turn(("face", "nose", "facemouth"), (0.20, 0.61), 0.2 * sin(phase * 6 * pi))
        elif name == "huia":
            turn(head, pivot, -0.15 * sin(phase * 4 * pi))
        elif name == "mink":
            turn(head, pivot, 0.12 * sin(phase * 4 * pi))
            move(("tail",), dy=0.02 * sin(phase * 6 * pi))
    drawing = draw({key: moved[key] for key in shapes}, {key: moved[key] for key in cuts})
    assert all(
        len(row) == WIDTH // 2
        for key, rows in drawing.items()
        if key != "art"
        for row in rows.splitlines()
    )
    return drawing


def fields(values: Mapping[str, str]) -> str:
    """Keep drawings editable as multiline TOML values"""
    return "\n".join(f"{key} = '''\n{value}\n'''" for key, value in values.items())


def bake(names: Iterable[str] = ()) -> None:
    """Rebuild artwork while preserving editable species metadata"""
    if missing := set(names) - animals.keys():
        raise SystemExit("Unknown species: " + ", ".join(sorted(missing)))
    forest: list[str] = []
    for name, (shapes, cuts) in animals.items():
        values = {
            key: value
            for key, value in FOREST[name].items()
            if key not in {"art", "shade", "hit", "tone"}
        }
        forest.append(
            f"[{name}]\n"
            + "\n".join(f"{key} = {value!r}" for key, value in values.items())
            + "\n"
            + fields(pose(name, shapes, cuts, "idle", 0))
        )
        if names and name not in names:
            continue
        frames: list[str] = []
        actions: dict[str, int] = dict.fromkeys(
            ("blink", "look", "listen", "peek", "play", "ears", "pet", "object", "nap"),
            8,
        )
        actions["breathe"] = 16
        actions.update(dict.fromkeys(values["idle"].split()[:4], 32))
        for region in ("head_moves", "body_moves", "object_moves"):
            for action in values[region].split():
                actions.setdefault(action, 8)
        for action, count in actions.items():
            for frame in range(count):
                frames.append(
                    f"[[{action}]]\n"
                    + fields(pose(name, shapes, cuts, action, frame / (count - 1)))
                )
        (ROOT / f"{name}.toml").write_text("\n\n".join(frames) + "\n")
        print(f"Baked {values['name']}", flush=True)
    (ROOT / "forest.toml").write_text("\n\n".join(forest) + "\n")


if __name__ == "__main__":
    bake(sys.argv[1:])
