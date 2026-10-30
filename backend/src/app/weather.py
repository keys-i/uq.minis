"""Serve shared habitat forecasts without exposing visitor locations upstream

Only bundled representative coordinates can be queried, with conditional
requests and bounded response sizes protecting the free forecast service
Cached weather remains usable during an upstream outage
"""

from __future__ import annotations

import asyncio
import json
import math
import tomllib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from time import time
from typing import Any, cast
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Request

from uq_minis.core.common import atomic_json
from uq_minis.core.paths import CACHE


@lru_cache(maxsize=1)
def catalogue() -> dict[str, dict[str, Any]]:
    """Read the bundled species locations rather than accepting external URLs"""
    return tomllib.loads(files("uq_minis.assets").joinpath("wildlife.toml").read_text())["species"]


def _number(value: object, minimum: float, maximum: float, default: float = 0) -> float:
    """Reject non-finite or unexpected measurements before publishing JSON"""
    return (
        float(cast(float, value))
        if type(value) in {int, float}
        and math.isfinite(cast(float, value))
        and minimum <= cast(float, value) <= maximum
        else default
    )


def _mapping(value: object) -> dict[str, Any]:
    """Reject malformed provider objects before reading their fields"""
    if not isinstance(value, dict):
        raise ValueError("Expected a forecast object")
    return cast(dict[str, Any], value)


def _expiry(response: httpx.Response, default: int = 1800) -> float:
    """Honour provider freshness within a bounded one-day cache window"""
    expires = response.headers.get("Expires")
    now = time()
    value = parsedate_to_datetime(expires).timestamp() if expires else now + default
    return max(now + 60, min(now + 86400, value)) if math.isfinite(value) else now + default


class Forecasts:
    """Own one reusable HTTP pool and bounded, deduplicated refresh tasks"""

    def __init__(self, client: httpx.AsyncClient, root: Path = CACHE / "weather") -> None:
        """Share a bounded connection pool and keep one refresh per habitat"""
        self.client = client
        self.root = root
        self.busy = asyncio.Semaphore(2)
        self.pending: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self.failed: dict[str, float] = {}

    def cached(self, habitat: str) -> dict[str, Any] | None:
        """Read only a small regular file beneath the owned cache directory"""
        path = self.root / f"{habitat}.json"
        if any(item.is_symlink() for item in (path, *path.parents)):
            return None
        try:
            if path.stat().st_size > 16384:
                return None
            data = _mapping(json.loads(path.read_text()))
            if (
                data.get("habitat") != habitat
                or type(data.get("expires")) not in {int, float}
                or not math.isfinite(data["expires"])
            ):
                return None
            return data
        except OSError, ValueError:
            return None

    async def _read(
        self, url: str, params: dict[str, str], modified: str = ""
    ) -> tuple[httpx.Response, Any]:
        """Limit provider responses without buffering an arbitrarily large body"""
        async with self.client.stream(
            "GET", url, params=params, headers={"If-Modified-Since": modified} if modified else {}
        ) as response:
            if response.status_code == 304:
                return response, None
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > 1024**2:
                    raise ValueError("Forecast response exceeds the size limit")
            return response, json.loads(content)

    async def refresh(self, habitat: str, previous: dict[str, Any] | None) -> dict[str, Any]:
        """Refresh one known location while retaining its previous usable forecast"""
        location = catalogue()[habitat]
        now = datetime.now(UTC)
        local = now.astimezone(ZoneInfo(location["zone"]))
        params = {"lat": str(location["latitude"]), "lon": str(location["longitude"])}
        try:
            async with self.busy:
                forecast = await self._read(
                    "https://api.met.no/weatherapi/locationforecast/2.0/compact",
                    params,
                    str((previous or {}).get("modified", "")),
                )
                solar = await self.solar(params, local, previous)
            response, payload = forecast
            if response.status_code == 304 and previous:
                result = dict(previous)
            else:
                rows = _mapping(_mapping(payload)["properties"])["timeseries"]
                if not isinstance(rows, list):
                    raise ValueError("Invalid forecast series")
                rows = cast(list[Any], rows)
                if not 0 < len(rows) <= 500:
                    raise ValueError("Invalid forecast series")
                rows = [_mapping(item) for item in rows]
                row = min(
                    rows,
                    key=lambda item: abs(
                        (datetime.fromisoformat(item["time"]) - now).total_seconds()
                    ),
                )
                details = _mapping(_mapping(_mapping(row["data"])["instant"])["details"])
                hour = _mapping(row["data"].get("next_1_hours", {}))
                result = {
                    "habitat": habitat,
                    "updated": payload["properties"]["meta"]["updated_at"],
                    "temperature": _number(details.get("air_temperature"), -90, 70),
                    "cloud": _number(details.get("cloud_area_fraction"), 0, 100),
                    "wind": _number(details.get("wind_speed"), 0, 100),
                    "rain": _number(
                        _mapping(hour.get("details", {})).get("precipitation_amount"), 0, 200
                    ),
                    "symbol": str(_mapping(hour.get("summary", {})).get("symbol_code", "unknown"))[
                        :64
                    ],
                }
            result.update(solar)
            result["modified"] = response.headers.get(
                "Last-Modified", (previous or {}).get("modified", "")
            )
            result["expires"] = _expiry(response)
            result["stale"] = False
            if not any(item.is_symlink() for item in (self.root, *self.root.parents)):
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                await asyncio.to_thread(
                    atomic_json, self.root / f"{habitat}.json", result, private=True
                )
            self.failed.pop(habitat, None)
            return result
        except httpx.HTTPError, ValueError, KeyError, TypeError, OSError:
            self.failed[habitat] = time() + 300
            return {
                **(previous or {"habitat": habitat, "updated": "", "expires": time() + 300}),
                "stale": True,
            }

    async def solar(
        self, params: dict[str, str], local: datetime, previous: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Reuse current solar events and retain forecast data if astronomy is unavailable"""
        fields = (
            "sunrise",
            "sunset",
            "solarnoon",
            "solarmidnight",
            "polar_day",
            "solar_date",
            "solar_expires",
        )
        cached = {key: previous[key] for key in fields if previous and key in previous}
        date = local.date().isoformat()
        if (
            cached.get("solar_date") == date
            and _number(cached.get("solar_expires"), 0, 1e12) > time()
        ):
            return cached
        offset = local.strftime("%z")
        try:
            response, payload = await self._read(
                "https://api.met.no/weatherapi/sunrise/3.0/sun",
                {**params, "date": date, "offset": f"{offset[:3]}:{offset[3:]}"},
            )
            solar = _mapping(_mapping(payload)["properties"])
            result: dict[str, Any] = {"solar_date": date, "solar_expires": _expiry(response, 21600)}
            for field in fields[:4]:
                event = _mapping(solar.get(field) or {})
                value = event.get("time")
                if value is not None:
                    datetime.fromisoformat(value)
                result[field] = value
            result["polar_day"] = (
                _number(
                    _mapping(solar.get("solarnoon") or {}).get("disc_centre_elevation"), -90, 90
                )
                > 0
                and not result["sunset"]
            )
            return result
        except httpx.HTTPError, ValueError, KeyError, TypeError:
            return cached

    async def get(self, habitat: str) -> dict[str, Any]:
        """Return fresh data immediately and refresh stale data in the background"""
        previous = self.cached(habitat)
        if previous and previous["expires"] > time():
            return previous
        if self.failed.get(habitat, 0) > time():
            return {
                **(
                    previous or {"habitat": habitat, "updated": "", "expires": self.failed[habitat]}
                ),
                "stale": True,
            }
        task = self.pending.get(habitat)
        if task is None or task.done():
            task = asyncio.create_task(self.refresh(habitat, previous))
            self.pending[habitat] = task
        if previous:
            return {**previous, "stale": True}
        return await asyncio.shield(task)

    async def close(self) -> None:
        """Cancel refreshes before their shared HTTP connection pool closes"""
        for task in self.pending.values():
            task.cancel()
        await asyncio.gather(*self.pending.values(), return_exceptions=True)


def install(app: FastAPI) -> None:
    """Register the public endpoint and compose its pool with the existing lifespan"""
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        async with (
            previous(application),
            httpx.AsyncClient(
                headers={"User-Agent": "UQMinis/0.33 https://uni.keysi.dev/mini/"},
                timeout=4,
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
                follow_redirects=False,
                trust_env=False,
            ) as client,
        ):
            forecasts = Forecasts(client)
            application.state.forecasts = forecasts
            try:
                yield
            finally:
                await forecasts.close()

    app.router.lifespan_context = lifespan

    @app.get("/api/weather/{habitat}")
    async def weather(request: Request, habitat: str) -> dict[str, Any]:
        """Return public habitat conditions without starting a private workspace"""
        if habitat not in catalogue():
            raise HTTPException(404, "Choose a known animal habitat")
        forecasts = getattr(request.app.state, "forecasts", None)
        if forecasts is None:
            raise HTTPException(
                503, "Habitat weather is starting; the scene will use its home clock"
            )
        return await cast(Forecasts, forecasts).get(habitat)
