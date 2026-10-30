"""Measure fresh web startup and real overlay work with Python's JIT on and off

Results report medians from isolated processes and retain output digests
No runtime setting changes without a measured benefit on its target host
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """Write reproducible startup and overlay samples beneath out/artifacts"""
    cases = {
        "cli": 'import uvicorn; uvicorn.run=lambda *a,**k:None; from uq_minis.cli import main; main(["browser"])',
        "web": "import uvicorn; uvicorn.run=lambda *a,**k:None; from uq_minis.web import run; run()",
        "overlay": """import hashlib,json,time,sys
from itertools import islice
from uq_minis.minis.timey.video import Timer,frames
start=time.perf_counter(); digest=hashlib.sha256()
for style in ('minimal','minecraft','temple-run'):
    for frame in islice(frames(Timer(seconds=30,style=style),640,360,fps=12),36): digest.update(frame)
print(json.dumps({'work_ms':(time.perf_counter()-start)*1000,'digest':digest.hexdigest(),'jit':sys._jit.is_enabled()}))""",
    }
    results: dict[str, object] = {"python": sys.version, "platform": sys.platform}
    with TemporaryDirectory(prefix="bench-", dir=ROOT / "out/.cache") as scratch:
        for name, code in cases.items():
            for jit in ("0", "1") if name == "overlay" else ("0",):
                elapsed: list[float] = []
                work: list[float] = []
                digests: set[str] = set()
                for _ in range(5):
                    start = perf_counter()
                    process = subprocess.run(
                        [sys.executable, "-c", code],
                        cwd=scratch,
                        env={**os.environ, "PYTHON_JIT": jit},
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    elapsed.append((perf_counter() - start) * 1000)
                    if name == "overlay":
                        data = json.loads(process.stdout.splitlines()[-1])
                        work.append(data["work_ms"])
                        digests.add(data["digest"])
                results[f"{name}_jit_{jit}"] = {
                    "median_ms": statistics.median(elapsed),
                    "samples_ms": elapsed,
                    "work_ms": work,
                    "digests": sorted(digests),
                }
    target = ROOT / "out/artifacts/python.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(results, indent=2) + "\n")
    print(target.read_text())


if __name__ == "__main__":
    main()
