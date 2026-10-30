"""Materialise tool-native configuration from the repository's TOML settings

Generated files belong to out/tools and may be removed at any time
Package manifests and lockfiles remain in their ecosystem's native format
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def write(name: str, content: str) -> Path:
    """Publish changed tool settings atomically without touching unchanged files"""
    target = ROOT / "out/tools" / name
    if target.is_file() and target.read_text() == content:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    try:
        temporary.write_text(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def publish(name: str, value: dict[str, Any]) -> Path:
    """Serialise native JSON without maintaining a second authored configuration"""
    return write(name, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def generate() -> None:
    """Resolve paths against their owning project before generating native JSON"""
    source = ROOT / "tools/config"
    frontend = ROOT / "frontend"
    data = tomllib.loads((source / "frontend.toml").read_text())
    typescript = data.pop("typescript")
    typescript["include"] = [str(frontend / path) for path in typescript["include"]]
    # Type references resolve from the generated file, outside frontend/node_modules
    typescript["compilerOptions"]["types"] = [
        str(frontend / "node_modules" / (f"@types/{name}" if "/" not in name else name))
        for name in typescript["compilerOptions"]["types"]
    ]
    typescript["compilerOptions"]["resolveJsonModule"] = True
    publish("tsconfig.json", typescript)
    data["vite"]["server"]["fs"] = {"allow": [str(frontend), str(ROOT / "out/tools")]}
    for name, value in data.items():
        publish(f"{name}.json", value)
    backend = ROOT / "backend"
    typing = tomllib.loads((source / "typing.toml").read_text())
    typing["extraPaths"] = [
        str((backend / path).resolve()) for path in typing.get("extraPaths", [])
    ]
    typing["include"] = [str(backend / path) for path in typing["include"]]
    for environment in typing["executionEnvironments"]:
        environment["root"] = str(backend / environment["root"])
        environment["extraPaths"] = [str(backend / path) for path in environment["extraPaths"]]
    publish("pyrightconfig.json", typing)
    tests = tomllib.loads((source / "pytest.toml").read_text())["pytest"]
    for field in ("testpaths", "pythonpath"):
        tests[field] = [str((backend / path).resolve()) for path in tests[field]]
    tests["cache_dir"] = str((backend / tests["cache_dir"]).resolve())
    content = (
        "[pytest]\n"
        + "\n".join(f"{key} = {json.dumps(value)}" for key, value in tests.items())
        + "\n"
    )
    write("pytest.toml", content)
    wildlife = tomllib.loads((ROOT / "backend/assets/wildlife.toml").read_text())
    publish("wildlife.json", wildlife)
    publish("search.json", tomllib.loads((ROOT / "backend/assets/search.toml").read_text()))
    catalogue = tomllib.loads((ROOT / "backend/assets/minis.toml").read_text())
    publish(
        "minis.json",
        {name: mini for name, mini in catalogue.items() if name not in {"auth", "agent"}},
    )
    cartoons = ROOT / "frontend/assets/wildlife/cartoons/index.toml"
    publish(
        "cartoons.json",
        tomllib.loads(cartoons.read_text()).get("species", {}) if cartoons.exists() else {},
    )
    for name in ("artifacts", "test-results", "coverage", "cypress", ".cache"):
        (ROOT / "out" / name).mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    generate()
