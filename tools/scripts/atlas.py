"""Compile editable transparent character sheets into bounded runtime atlases

Connected alpha silhouettes supply frame bounds rather than assuming that an
illustrator placed each whole animal exactly on a rectangular grid
This performs asset packing and encoding, retaining the original PNG artwork
"""

from __future__ import annotations

import argparse
import hashlib
import math
import tomllib
from pathlib import Path
from typing import Any, cast

import tomli_w
from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "frontend/assets/wildlife"


def frames(
    image: Image.Image, count: int = 8, extract: list[Image.Image] | None = None, columns: int = 4
) -> list[list[int]]:
    """Find separate illustrations, ignoring almost-transparent matte remnants"""
    width = max(1, image.width // 2)
    height = max(1, image.height // 2)
    with image.getchannel("A") as alpha, alpha.copy() as sample:
        sample.thumbnail((width, height))
        width, height = sample.size
        pixels = bytearray(255 if value >= 16 else 0 for value in sample.tobytes())
    boxes: list[tuple[int, int, int, int]] = []
    islands: dict[tuple[int, int, int, int], list[int]] = {}
    for index in range(len(pixels)):
        if not pixels[index]:
            continue
        pixels[index] = 0
        queue = [index]
        minimum_x = maximum_x = index % width
        minimum_y = maximum_y = index // width
        area = 0
        members: list[int] = []
        while queue:
            current = queue.pop()
            x, y = current % width, current // width
            minimum_x, maximum_x = min(minimum_x, x), max(maximum_x, x)
            minimum_y, maximum_y = min(minimum_y, y), max(maximum_y, y)
            area += 1
            if extract is not None:
                members.append(current)
            for neighbour in (
                current - width if y else -1,
                current + width if y < height - 1 else -1,
                current - 1 if x else -1,
                current + 1 if x < width - 1 else -1,
            ):
                if neighbour >= 0 and pixels[neighbour]:
                    pixels[neighbour] = 0
                    queue.append(neighbour)
        if area >= width * height // 2000:
            box = (minimum_x, minimum_y, maximum_x + 1, maximum_y + 1)
            boxes.append(box)
            islands[box] = members
    if len(boxes) != count:
        raise ValueError(f"Expected {count} separate illustrations, found {len(boxes)}")
    ordered = sorted(boxes, key=lambda box: (box[1] + box[3]) / 2)
    ordered = [
        box
        for start in range(0, count, columns)
        for box in sorted(ordered[start : start + columns], key=lambda box: box[0])
    ]
    result: list[list[int]] = []
    for box in ordered:
        x, y, right, bottom = box
        x, y = max(0, int(x * image.width / width) - 6), max(0, int(y * image.height / height) - 6)
        right, bottom = (
            min(image.width, int(right * image.width / width) + 6),
            min(image.height, int(bottom * image.height / height) + 6),
        )
        result.append([x, y, right - x, bottom - y])
        if extract is not None:
            # Mask the selected island so a neighbour inside its rectangle cannot leak through
            selected = bytearray(width * height)
            for member in islands[box]:
                selected[member] = 255
            with (
                Image.frombytes("L", (width, height), bytes(selected)) as small,
                small.filter(ImageFilter.MaxFilter(3)) as expanded,
            ):
                full = cast(
                    Image.Image,
                    cast(Any, expanded).resize(image.size, Image.Resampling.NEAREST),
                )
            with (
                full,
                image.getchannel("A") as alpha,
                ImageChops.multiply(alpha, full) as clean,
                image.copy() as isolated,
            ):
                isolated.putalpha(clean)
                extract.append(isolated.crop((x, y, right, bottom)))
    return result


def split(source: Path, names: list[str]) -> None:
    """Separate a multi-resident illustration into editable eight-part sources"""
    known = tomllib.loads((ROOT / "backend/assets/wildlife.toml").read_text())["species"]
    if not names or any(name not in known for name in names):
        raise ValueError("Use bundled animal identities for source names")
    with Image.open(source) as image:
        parts: list[Image.Image] = []
        boxes = frames(image, len(names) * 8, parts)
        for index, name in enumerate(names):
            group = boxes[index * 8 : (index + 1) * 8]
            cell_width = max(box[2] for box in group) + 24
            cell_height = max(box[3] for box in group) + 24
            with Image.new("RGBA", (cell_width * 4, cell_height * 2)) as packed:
                for slot in range(8):
                    with parts[index * 8 + slot] as part:
                        packed.alpha_composite(
                            part, (slot % 4 * cell_width + 12, slot // 4 * cell_height + 12)
                        )
                packed.save(ASSETS / "source" / f"{name}.png")


def build() -> None:
    """Encode changed sources and publish their frame index for the frontend"""
    index = ASSETS / "rigs.toml"
    data: dict[str, Any] = tomllib.loads(index.read_text()) if index.exists() else {}
    for source in sorted((ASSETS / "source").glob("*.png")):
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        portrait = ASSETS / "portraits" / f"{source.stem}.webp"
        if (
            data.get(source.stem, {}).get("digest") == digest
            and data[source.stem].get("version") == 3
            and portrait.exists()
            and (ASSETS / f"{source.stem}.webp").exists()
        ):
            continue
        with Image.open(source) as image:
            if image.mode != "RGBA" or image.width * image.height > 12_000_000:
                raise ValueError(f"{source.name} needs a bounded true-alpha source")
            try:
                rectangles = frames(image)
            except ValueError as error:
                raise ValueError(f"{source.name}: {error}") from error
            portrait.parent.mkdir(exist_ok=True)
            x, y, w, h = rectangles[1]
            with image.crop((x, y, x + w, y + h)) as head:
                head.thumbnail((96, 96), Image.Resampling.LANCZOS)
                head.save(portrait, format="WEBP", quality=85, method=6)
            scale = min(1, 1024 / image.width)
            size = (round(image.width * scale), round(image.height * scale))
            with image.copy() as packed:
                packed.thumbnail(size, Image.Resampling.LANCZOS)
                size = packed.size
                packed.save(ASSETS / f"{source.stem}.webp", format="WEBP", quality=88, method=6)
            scaled: list[list[int]] = []
            for x, y, width, height in rectangles:
                left, top = (
                    math.floor(x * size[0] / image.width),
                    math.floor(y * size[1] / image.height),
                )
                right, bottom = (
                    min(size[0], math.ceil((x + width) * size[0] / image.width)),
                    min(size[1], math.ceil((y + height) * size[1] / image.height)),
                )
                scaled.append([left, top, right - left, bottom - top])
            data[source.stem] = {
                "version": 3,
                "size": list(size),
                "frames": scaled,
                "digest": digest,
            }
    text = "# == Painted character frame bounds ==\n" + tomli_w.dumps(data)
    if not index.exists() or index.read_text() != text:
        index.write_text(text)


def backdrops() -> None:
    """Encode individual painted habitats so unseen biomes are not downloaded"""
    directory = ASSETS.parent / "habitats"
    index = directory / "index.toml"
    data: dict[str, Any] = tomllib.loads(index.read_text()) if index.exists() else {}
    for source in (directory / "source").glob("*.png"):
        target = directory / f"{source.stem}.webp"
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if target.exists() and data.get(source.stem) == digest:
            continue
        with Image.open(source) as image:
            image.save(target, format="WEBP", quality=88, method=6)
        data[source.stem] = digest
    text = tomli_w.dumps(data)
    if not index.exists() or index.read_text() != text:
        index.write_text(text)


def cartoons() -> None:
    """Pack complete illustrated poses without separating an animal's anatomy"""
    destination = ASSETS / "cartoons"
    destination.mkdir(exist_ok=True)
    index = destination / "index.toml"
    catalogue = tomllib.loads((ROOT / "backend/assets/wildlife.toml").read_text())["species"]
    originals = list(catalogue)[:24]
    added = [
        "mink",
        "solenodon",
        "potoroo",
        "melomys",
        "skink",
        "paddlefish",
        "crayfish",
        "dog",
        "orangutan",
        "leopard",
        "lynx",
        "gorilla",
        "bonobo",
        "lemur",
        "aye",
        "tamarin",
    ]
    neighbours = [
        "macaque",
        "tahr",
        "dolphin",
        "bustard",
        "florican",
        "vulture",
        "gharial",
        "indipangolin",
        "parakeet",
        "eagle",
    ]
    sheets = {
        "original": (ASSETS.parent / "images/wildlife.webp", 24, 4),
        "activities": (ASSETS.parent / "images/poses.webp", 48, 8),
        "residents": (destination / "source/residents.png", 32, 8),
        "neighbours": (destination / "source/neighbours.png", 20, 5),
    }
    signatures = {
        name: hashlib.sha256(path.read_bytes()).hexdigest() for name, (path, _, _) in sheets.items()
    }
    previous = tomllib.loads(index.read_text()) if index.exists() else {}
    if previous.get("sources") == signatures and all(
        (destination / f"{name}.webp").is_file()
        and (destination / "portraits" / f"{name}.webp").is_file()
        for name in catalogue
    ):
        return
    extracted: dict[str, list[Image.Image]] = {}
    try:
        for name, (path, count, columns) in sheets.items():
            extracted[name] = []
            with Image.open(path) as image:
                frames(image, count, extracted[name], columns)
        poses: dict[str, list[Image.Image]] = {}
        for i, name in enumerate(originals):
            offset = i // 4 * 8 + i % 4 * 2
            poses[name] = [extracted["original"][i], *extracted["activities"][offset : offset + 2]]
        for i, name in enumerate(added):
            poses[name] = extracted["residents"][i * 2 : i * 2 + 2]
        for i, name in enumerate(neighbours):
            offset = i // 5 * 10 + i % 5
            poses[name] = [extracted["neighbours"][offset], extracted["neighbours"][offset + 5]]
        if set(poses) != set(catalogue):
            raise ValueError("Every resident needs a complete cartoon")
        species: dict[str, Any] = {}
        (destination / "portraits").mkdir(exist_ok=True)
        for name, illustrations in poses.items():
            with Image.new("RGBA", (320 * len(illustrations), 220)) as packed:
                for slot, illustration in enumerate(illustrations):
                    with illustration.copy() as pose:
                        pose.thumbnail((250, 185), Image.Resampling.LANCZOS)
                        packed.alpha_composite(
                            pose, (slot * 320 + (320 - pose.width) // 2, 202 - pose.height)
                        )
                packed.save(destination / f"{name}.webp", format="WEBP", quality=90, method=6)
            with illustrations[0].copy() as portrait:
                portrait.thumbnail((96, 96), Image.Resampling.LANCZOS)
                portrait.save(
                    destination / "portraits" / f"{name}.webp", format="WEBP", quality=85, method=6
                )
            species[name] = {
                "size": [320 * len(illustrations), 220],
                "frames": [[slot * 320, 0, 320, 220] for slot in range(len(illustrations))],
            }
        species["guests"] = tomllib.loads((ASSETS / "rigs.toml").read_text())["guests"]
        index.write_text(tomli_w.dumps({"sources": signatures, "species": species}))
    finally:
        for illustrations in extracted.values():
            for illustration in illustrations:
                illustration.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path)
    parser.add_argument("names", nargs="*")
    arguments = parser.parse_args()
    if arguments.split:
        split(arguments.split, arguments.names)
    cartoons()
    backdrops()
