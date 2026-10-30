# Minis backend

Python application logic, FastAPI browser routes and CLI tools share the same mini implementations

```sh
uv sync --all-extras
uv run mini list
uv run mini browser
uv run dev check
```

Run these commands from `backend/`
The React interface lives in `../frontend/`; build it there before serving the browser app, or use Vite during development
Mini-specific logic belongs in `src/minis/`, shared rules in `src/core/`, command workflows in `src/cli/` and browser routes in `src/app/`
Local state belongs in `.config/`; credentials and marks are never returned by unrelated mini routes

Python 3.15 lazy imports keep optional browser, document and media dependencies behind their public entry points
The `mini` command and `python -m uq_minis.cli` share the same dispatcher; background workers use module execution
Public contracts use Google-style docstrings, and Ruff checks that documented argument lists stay complete

`uv run python tests/benchmarks/imports.py` compares importing a package with accessing all its public exports in five fresh processes per case
It measures import time and peak traced Python allocations, excluding native buffers and whole-application latency
On this Mac with Python 3.15, package-only imports took 1–2 ms and about 142 KiB of traced allocation; materialising all Event, Scrappy, Agent or Timey exports took 349–774 ms and 14–34 MiB
The work is deferred until first use, rather than eliminated

JIT is available in this interpreter but remains at its runtime default
Five-run CLI benchmarks with `PYTHON_JIT=0`, then `1`, then `0` did not show a consistent gain
For example, the repeat JIT-off risk-document batch took a 742 ms median compared with 777 ms with JIT on
Use `PYTHON_JIT=1 uv run python tests/benchmarks/cli.py` to repeat the comparison for another machine or workload

Backend tests use up to four isolated processes and work stealing
The recorded serial baseline completed 1,683 tests with six failures in 240.26 seconds; the reorganised suite passed 1,680 tests without coverage in 49.65 seconds
Those counts differ because duplicate checks were consolidated and regressions added, so this is a suite-throughput comparison rather than a per-test speed claim
