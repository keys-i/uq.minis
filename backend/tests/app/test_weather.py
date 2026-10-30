import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import time

import httpx
import pytest

from uq_minis.app.weather import Forecasts


def test_forecast(tmp_path: Path) -> None:
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if "/sunrise/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "sunrise": {"time": "2026-10-21T06:00:00+00:00"},
                        "sunset": {"time": "2026-10-21T18:00:00+00:00"},
                    }
                },
            )
        if request.headers.get("if-modified-since"):
            return httpx.Response(304)
        return httpx.Response(
            200,
            headers={"Last-Modified": "Wed, 21 Oct 2026 00:00:00 GMT"},
            json={
                "properties": {
                    "meta": {"updated_at": "now"},
                    "timeseries": [
                        {
                            "time": datetime.now(UTC).isoformat(),
                            "data": {
                                "instant": {
                                    "details": {
                                        "air_temperature": 24,
                                        "cloud_area_fraction": 38,
                                        "wind_speed": 2,
                                    }
                                }
                            },
                        }
                    ],
                },
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            forecasts = Forecasts(client, tmp_path)
            a, b = await asyncio.gather(forecasts.get("otter"), forecasts.get("otter"))
            assert a == b and a["temperature"] == 24 and not a["stale"]
            assert len(requests) == 2
            assert await forecasts.get("otter") == a
            refreshed = await forecasts.refresh("otter", {**a, "expires": time() - 1})
            assert refreshed["temperature"] == 24 and len(requests) == 3
            await forecasts.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "solar", [None, {"properties": {"sunrise": "invalid"}}, {"properties": []}]
)
def test_solar_failure(tmp_path: Path, solar: object) -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=solar))
        ) as client:
            forecasts = Forecasts(client, tmp_path)
            assert await forecasts.solar({}, datetime.now(UTC), None) == {}
            previous = {
                "habitat": "otter",
                "expires": time() - 1,
                "temperature": 21,
                "updated": "before",
            }
            assert (await forecasts.refresh("otter", previous))["temperature"] == 21
            assert (await forecasts.get("otter"))["stale"]
            await forecasts.close()

    asyncio.run(run())


def test_cache_boundary(tmp_path: Path) -> None:
    async def run() -> None:
        async with httpx.AsyncClient() as client:
            forecasts = Forecasts(client, tmp_path)
            path = tmp_path / "otter.json"
            for expires in [float("nan"), float("inf"), "forever"]:
                path.write_text(json.dumps({"habitat": "otter", "expires": expires}))
                assert forecasts.cached("otter") is None
            path.unlink()
            secret = tmp_path / "private"
            secret.write_text("private")
            path.symlink_to(secret)
            assert forecasts.cached("otter") is None

    asyncio.run(run())
