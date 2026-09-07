"""Compare warm MCP calls with fresh CLI processes for the same form preview."""

import asyncio
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    """Print five-sample medians; exclude MCP startup and its first call."""
    root = Path(__file__).resolve().parents[2]
    source = root / "examples/movie-night/event.toml"
    entry = [sys.executable, "-c", "from uq_minis.cli import main; main()"]
    params = StdioServerParameters(command=entry[0], args=[*entry[1:], "agents"], cwd=str(root))
    results = {}
    with TemporaryDirectory(prefix="uq-minis-agents-") as directory:
        output = Path(directory)
        async with stdio_client(params) as streams, ClientSession(*streams) as session:
            await session.initialize()
            samples = []
            for attempt in range(6):
                start = time.perf_counter()
                result = await session.call_tool(
                    "event_generate",
                    {
                        "source": str(source),
                        "form": True,
                        "risk": False,
                        "output": str(output / f"mcp-{attempt}"),
                    },
                )
                if result.is_error:
                    raise RuntimeError(result)
                if attempt:
                    samples.append((time.perf_counter() - start) * 1000)
            results["warm_mcp"] = samples
        samples = []
        for attempt in range(5):
            start = time.perf_counter()
            subprocess.run(
                [
                    *entry,
                    "event",
                    str(source),
                    "--form",
                    "--preview",
                    "--no-input",
                    "-o",
                    str(output / f"cli-{attempt}"),
                ],
                cwd=root,
                stdout=subprocess.DEVNULL,
                check=True,
            )
            samples.append((time.perf_counter() - start) * 1000)
        results["fresh_cli"] = samples
        first_mcp = next((output / "mcp-1").glob("*.json"))
        first_cli = next((output / "cli-0").glob("*.json"))
        assert json.loads(first_mcp.read_text()) == json.loads(first_cli.read_text())
    print(
        json.dumps(
            {
                name: {
                    "median_ms": round(statistics.median(samples), 2),
                    "samples_ms": [round(sample, 2) for sample in samples],
                }
                for name, samples in results.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
