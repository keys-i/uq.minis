"""Share the CLI's habitat artwork and palette with the browser

The browser receives the same bundled residents, palettes and original
artwork as terminal workflows. SVG responses are inert and bounded rather
than a path for injecting executable markup into the frontend
"""

from functools import lru_cache
from importlib.resources import files
from io import StringIO
from random import choice
from typing import Any

from fastapi import APIRouter, Response
from rich.console import Console

from uq_minis.core.art import COLOURS, RESIDENTS, habitats, poses
from uq_minis.core.common import MiniError

router = APIRouter()


@router.get("/api/brand/uq.png")
def university() -> Response:
    """Use the bundled university logo on course cards"""
    return Response(
        files("uq_minis.assets").joinpath("uq-logo.png").read_bytes(), media_type="image/png"
    )


@router.get("/api/habitat")
def habitat(mini: str = "home") -> dict[str, Any]:
    """Use a mini's resident or an equally likely visitor from the shared forest"""
    animal = choice(list(habitats())) if mini == "home" else RESIDENTS.get(mini, "numbat")
    look = habitats()[animal]
    return {
        "animal": animal,
        "name": look.name,
        "status": look.status,
        "country": look.country,
        "place": look.place,
        "quip": choice(look.quip.split("|")).strip(),
        "source": look.source,
        "colours": {
            **COLOURS,
            "accent": look.primary,
            "secondary": look.secondary,
            "leaf": look.leaf,
        },
    }


@lru_cache(maxsize=16)
def drawing(animal: str, pose: str) -> str:
    """Export a bounded still using Rich without remote fonts or a rendering service"""
    if animal not in habitats() or pose not in {"idle", "look", "pet"}:
        raise MiniError("Choose a known habitat and greeting")
    frame = len(poses(animal)[pose]) // 2 if pose != "idle" else 0
    console = Console(file=StringIO(), width=66, record=True, color_system="truecolor")
    console.print(habitats()[animal].picture(frame, pose, (64, 24)), end="")
    return console.export_svg(
        code_format=files("uq_minis.assets").joinpath("habitat.svg").read_text()
    )


@router.get("/api/habitat/{animal}.svg")
def picture(animal: str, pose: str = "idle") -> Response:
    """Serve trusted CLI artwork as an image, never as executable page markup"""
    return Response(drawing(animal, pose), media_type="image/svg+xml")
