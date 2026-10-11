"""Bake shaded braille habitats without a runtime graphics dependency"""

import tomllib
from math import cos, pi, sin, sqrt
from pathlib import Path

WIDTH, HEIGHT = 80, 64
BITS = ((1, 8), (2, 16), (4, 32), (64, 128))
ROOT = Path(__file__).parent
FOREST = tomllib.loads((ROOT / "forest.toml").read_text())


def shape(x, y, rx, ry, depth=0.15, front=0):
    """Keep editable ellipsoid geometry in normalised habitat coordinates"""
    return x, y, rx, ry, depth, front, 0


def surface(x, y, model):
    """Find the visible depth of a rotated ellipsoid"""
    cx, cy, rx, ry, depth, front, angle = model
    dx, dy = x - cx, y - cy
    radius = ((dx * cos(angle) + dy * sin(angle)) / rx) ** 2 + (
        (dy * cos(angle) - dx * sin(angle)) / ry
    ) ** 2
    return front + depth * sqrt(1 - radius) if radius < 1 else None


def draw(shapes, cuts):
    """Bake braille dots, depth, materials and pointer targets from one model"""
    pixels, regions, tones = [], [], []
    for row in range(HEIGHT):
        depths, areas, materials = [], [], []
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
                if key.startswith(("propflower", "facewattle"))
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
    result = {key: [] for key in ("art", "shade", "hit", "tone")}
    for row in range(0, HEIGHT, 4):
        glyphs, levels, targets, colours = [], [], [], []
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
                    0, (-0.6 * nx - 0.8 * ny + 1.2) / sqrt(nx * nx + ny * ny + 1) / sqrt(2.44)
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
animals = {}
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
    cuts = {}
    if name == "numbat":
        shapes["tail"] = shape(0.77, 0.57, 0.13, 0.16, 0.13)
        shapes["facewhite"] = shape(0.21, 0.51, 0.075, 0.014, 0.015, 0.24)
        for n in range(5):
            shapes[f"white{n}"] = shape(0.44 + n * 0.045, 0.66, 0.009, 0.105, 0.015, 0.22)
        cuts["log"] = shape(0.82, 0.89, 0.07, 0.006)
    elif name == "saola":
        shapes.update(
            {
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
            }
        )
        for n in range(3):
            shapes[f"propleaf{n}"] = shape(0.10 + n * 0.04, 0.81 - n * 0.045, 0.035, 0.022, 0.03)
    elif name == "huia":
        shapes.update(
            {
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
            }
        )
        for n in range(3):
            cuts[f"feather{n}"] = shape(0.40 + n * 0.025, 0.66, 0.003, 0.09)
    elif name in ("mink", "otter"):
        shapes.update(
            {
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
            }
        )
        cuts["whisker"] = shape(0.14, 0.63, 0.055, 0.004)
        if name == "otter":
            shapes["body"] = shape(0.49, 0.71, 0.25, 0.12, 0.20)
            shapes["head"] = shape(0.25, 0.59, 0.11, 0.095, 0.17, 0.04)
            shapes["white0"] = shape(0.31, 0.69, 0.04, 0.07, 0.02, 0.20)
            shapes["tail"] = shape(0.79, 0.77, 0.17, 0.04, 0.08)
    elif name == "bee":
        shapes.pop("neck")
        shapes.update(
            {
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
            }
        )
        shapes.pop("tail")
        for n in range(2):
            cuts[f"vein{n}"] = shape(0.36 + n * 0.17, 0.38, 0.045, 0.003)
    elif name == "quoll":
        shapes["tail"] = shape(0.81, 0.73, 0.15, 0.025, 0.055)
        shapes["ear1"] = shape(0.18, 0.39, 0.045, 0.045, 0.09)
        shapes["ear2"] = shape(0.30, 0.40, 0.037, 0.04, 0.08)
        for n, (x, y) in enumerate(
            (
                (0.38, 0.62),
                (0.47, 0.64),
                (0.56, 0.62),
                (0.64, 0.66),
                (0.42, 0.73),
                (0.52, 0.75),
                (0.60, 0.74),
            )
        ):
            shapes[f"white{n}"] = shape(x, y, 0.012, 0.014, 0.015, 0.22)
        shapes["prop"] = shape(0.83, 0.87, 0.10, 0.055, 0.09)
    elif name in ("pangolin", "solenodon"):
        shapes.update(
            {
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
            }
        )
        if name == "solenodon":
            shapes["tail"] = shape(0.81, 0.78, 0.16, 0.017, 0.04)
            shapes["ear1"] = shape(0.20, 0.50, 0.035, 0.035, 0.08)
        else:
            for row in range(4):
                for col in range(5):
                    x, y = 0.30 + col * 0.065 + (row % 2) * 0.025, 0.57 + row * 0.055
                    if surface(x, y, shapes["body"]) is not None:
                        shapes[f"scale{row}{col}"] = shape(x, y, 0.024, 0.012, 0.012, 0.225)
    elif name == "auk":
        shapes.update(
            {
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
            }
        )
        for n in range(3):
            cuts[f"bill{n}"] = shape(0.20 + n * 0.035, 0.34, 0.003, 0.025)
    elif name in ("potoroo", "melomys"):
        shapes.update(
            {
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
            }
        )
        if name == "potoroo":
            shapes["propflower"] = shape(0.83, 0.84, 0.075, 0.025, 0.06)
        else:
            shapes["body"] = shape(0.48, 0.70, 0.20, 0.14, 0.20)
            shapes["paw2"] = shape(0.62, 0.80, 0.032, 0.06, 0.08)
            shapes["foot2"] = shape(0.62, 0.86, 0.055, 0.02, 0.07)
            shapes["prop"] = shape(0.84, 0.89, 0.055, 0.023, 0.03, 0.12)
    elif name == "skink":
        shapes.update(
            {
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
            }
        )
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
    elif name in ("tiger", "panda", "dog"):
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
        else:
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
    elif name == "orangutan":
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
    if name in ("mink", "otter", "auk", "melomys", "paddlefish", "crayfish"):
        for n in range(3):
            shapes[f"scenewater{n}"] = shape(0.23 + n * 0.3, 0.94, 0.10, 0.005, 0.01, -0.12)
    if name in ("auk", "melomys", "paddlefish"):
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
    if name not in ("bee", "huia", "auk", "crayfish"):
        x, y, rx, ry, depth, front, _ = shapes["face"]
        shapes["facemouth"] = shape(x, y + ry * 0.5, rx * 0.6, 0.004, 0.015, front + depth + 0.005)
        x, y, _, _, _, front, _ = shapes["eye1"]
        shapes["eye2"] = shape(x + 0.065, y + 0.006, 0.017, 0.023, 0.015, front - 0.015)
        shapes["eyelight2"] = shape(x + 0.060, y, 0.005, 0.006, 0.01, front + 0.015)
    animals[name] = shapes, cuts


def pose(name, shapes, cuts, action, phase):
    """Move attached features around joints before sampling the whole sculpture"""
    original = shapes | cuts
    moved = dict(original)
    strength = (1 - cos(phase * pi)) / 2 if action in ("look", "listen") else sin(phase * pi) ** 2
    if action in FOREST[name]["idle"].split()[:4]:
        strength = sin(phase * pi) ** 0.6

    def move(keys, dx=0, dy=0, sx=1, sy=1):
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

    def turn(keys, pivot, angle):
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
        if key.startswith(
            ("head", "ear", "horn", "face", "eye", "nose", "antenna", "beak", "whisker", "bill")
        )
    ]
    body = [key for key in original if not key.startswith(("prop", "scene"))]
    pivot = (
        (0.32, 0.55)
        if name == "saola"
        else (0.36, 0.43)
        if name == "huia"
        else (0.45, 0.43)
        if name == "auk"
        else (0.30, 0.60)
    )
    if action in ("blink", "pet", "nap") and name != "bee":
        move(("eye1", "eyelight", "eye2", "eyelight2"), sy=0.15)
    if action == "blink" and name == "bee":
        turn(("ear1", "antenna1"), (0.25, 0.43), -0.4)
    if action in ("look", "listen", "peek"):
        turn(head, pivot, 0.10 if action == "look" else 0.07 if action == "listen" else -0.12)
    elif action == "ears":
        for key, angle in (("ear1", -0.30), ("ear2", 0.25), ("horn1", -0.08), ("horn2", -0.08)):
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
        turn(("paw1", "foot1"), (0.31 - 0.12 * strength, 0.72), 0.30 * sin(phase * 8 * pi))
        turn(("paw2", "foot2"), (0.64 - 0.12 * strength, 0.72), -0.25 * sin(phase * 8 * pi))
        turn(("tail",), (0.66 - 0.12 * strength, 0.68), 0.20 * sin(phase * 4 * pi))
        if name == "auk":
            move(("paw1",), dx=0.04, dy=-0.025 * sin(phase * 8 * pi))
    elif action in ("forage", "probe", "browse", "sniff", "dig"):
        turn(head, pivot, -0.18 - 0.09 * sin(phase * 8 * pi) if name != "saola" else -0.85)
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
        turn(("paw2",), (0.51 - 0.08 * strength, 0.50 - 0.10 * strength), 0.9 * sin(phase * 8 * pi))
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
        turn(("paw1", "foot1"), (0.31 + 0.07 * phase * strength, 0.72), 0.35 * sin(phase * 6 * pi))
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
        move(body, dx=-0.11, dy=-0.09 * abs(sin(phase * 4 * pi)) if name == "potoroo" else 0)
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
        turn(("tail", "tailupper", "taillower"), (0.71, 0.54), 0.35 * sin(phase * 10 * pi))
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
        turn(("tail", "dark0", "dark1", "dark2", "dark3"), (0.66, 0.72), 0.32 * sin(phase * 6 * pi))
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
    if name == "bee" and action in ("ears", "pet", "play", "object", "breathe"):
        move(("paw1",), sy=0.6)
        move(("paw2",), sy=0.7)
        move(body, dy=-0.022)
    if name in ("huia", "auk") and action in ("pet", "play", "ears"):
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


def fields(values):
    """Keep drawings editable as multiline TOML values"""
    return "\n".join(f"{key} = '''\n{value}\n'''" for key, value in values.items())


def bake():
    """Rebuild artwork while preserving editable species metadata"""
    forest = []
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
        frames = []
        actions = dict.fromkeys(
            ("blink", "look", "listen", "peek", "play", "ears", "pet", "object", "nap"), 8
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
    (ROOT / "forest.toml").write_text("\n\n".join(forest) + "\n")


if __name__ == "__main__":
    bake()
