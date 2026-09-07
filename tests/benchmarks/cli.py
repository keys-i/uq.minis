"""Measure fresh-process CLI startup and two-event DOCX generation"""

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    """Print median timings from five runs of each command"""
    results = {}
    cases = {
        **{f"{tool} help": ["--tool", tool, "--help"] for tool in ("event-risk", "event", "auth")},
        "risk batch": ["--tool", "event-risk", "examples", "--layout", "form", "--no-input"],
    }
    with TemporaryDirectory(prefix="uq-minis-benchmark-") as directory:
        for name, args in cases.items():
            samples = []
            for attempt in range(5):
                output = ["-o", str(Path(directory) / str(attempt))] if name == "risk batch" else []
                start = time.perf_counter()
                subprocess.run(
                    [sys.executable, "-c", "from uq_minis.cli import main; main()", *args, *output],
                    cwd=Path(__file__).resolve().parents[2],
                    stdout=subprocess.DEVNULL,
                    check=True,
                )
                samples.append(round((time.perf_counter() - start) * 1000, 2))
            results[name] = {"median_ms": statistics.median(samples), "samples_ms": samples}
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
