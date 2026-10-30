"""Compare package-only imports with materialising their public exports

Run five fresh Python processes per case, tracing Python allocations only
This isolates deferred import work rather than claiming whole-app latency
or native-process memory measurements
"""

import json
import statistics
import subprocess
import sys

SAMPLE = """
import importlib, json, sys, time, tracemalloc
tracemalloc.start()
start = time.perf_counter()
module = importlib.import_module(sys.argv[1])
if sys.argv[2] == 'eager':
    for name in module.__all__:
        getattr(module, name)
print(json.dumps({
    'ms': (time.perf_counter() - start) * 1000,
    'peak_kib': tracemalloc.get_traced_memory()[1] / 1024,
    'modules': len(sys.modules),
}))
"""


def main() -> None:
    """Print median import time, traced peak allocation and loaded module count"""
    results = {}
    for mini in ("event", "scrappy", "agent", "timey"):
        results[mini] = {}
        for mode in ("lazy", "eager"):
            samples = [
                json.loads(
                    subprocess.check_output(
                        [sys.executable, "-c", SAMPLE, f"uq_minis.minis.{mini}", mode],
                        text=True,
                    )
                )
                for _ in range(5)
            ]
            results[mini][mode] = {
                key: round(statistics.median(sample[key] for sample in samples), 2)
                for key in samples[0]
            }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
