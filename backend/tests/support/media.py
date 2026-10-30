"""Shared test inputs, isolated state and terminal setup"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock

import httpx
import pytest

from uq_minis.cli import timey as wizard
from uq_minis.minis.timey import video


@pytest.fixture
def fontlist(monkeypatch: pytest.MonkeyPatch):
    families = {"Open Sans": "Sans Serif", "Noto Sans Devanagari": "Sans Serif"}
    monkeypatch.setattr(wizard, "catalogue", Mock(return_value=families))
    return families


@pytest.fixture
def videos(monkeypatch: pytest.MonkeyPatch):
    client = MagicMock()
    client.__enter__.return_value = client
    client.extract_info.return_value = {
        "entries": [{"id": "abcdefghijk", "title": "A quiet forest", "duration": 83}]
    }
    factory = Mock(return_value=client)
    monkeypatch.setattr(video, "YoutubeDL", factory)
    return factory, client


@pytest.fixture
def predictions(monkeypatch: pytest.MonkeyPatch):
    reply = Mock(
        return_value=httpx.Response(200, json=["forest", ["forest walk", "forest sounds"]])
    )
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", partial(client, transport=httpx.MockTransport(reply)))
    return reply


@pytest.fixture
def thumbnails(monkeypatch: pytest.MonkeyPatch):
    from io import BytesIO

    with BytesIO() as buffer:
        video.Image.new("RGB", (48, 36), "#e8a37e").save(buffer, format="PNG")
        payload = buffer.getvalue()
    reply = MagicMock()
    reply.__enter__.return_value = reply
    reply.iter_bytes.return_value = [payload]
    monkeypatch.setattr(httpx, "stream", Mock(return_value=reply))
    return reply


@pytest.fixture
def draft() -> dict[str, Any]:
    return {
        "snippet": {"title": "Minecraft timer", "description": "", "tags": []},
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }


@pytest.fixture
def art():
    return {
        "name": "Hollow Knight",
        "font": "serif",
        "shapes": [
            {
                "kind": "round",
                "points": [[0, 0], [540, 234]],
                "colour": "#101830EE",
                "width": 1,
                "radius": 24,
            },
            {
                "kind": "line",
                "points": [[12, 12], [528, 12]],
                "colour": "#BBCFFF",
                "width": 3,
                "radius": 0,
            },
            {
                "kind": "polygon",
                "points": [[15, 40], [30, 20], [45, 40]],
                "colour": "#FFFFFF",
                "width": 1,
                "radius": 0,
            },
            {
                "kind": "ellipse",
                "points": [[480, 20], [515, 55]],
                "colour": "#BBCFFF",
                "width": 1,
                "radius": 0,
            },
        ],
        "text": {
            key: {
                "point": [270, top],
                "size": size,
                "colour": "#FFFFFF",
                "outline": "#101830",
                "stroke": 1,
            }
            for key, top, size in (
                ("label", 30, 20),
                ("timer", 80, 60),
                ("caption", 155, 16),
            )
        },
        "bar": {
            "points": [[35, 190], [505, 200]],
            "colour": "#BBCFFF",
            "background": "#252F42",
            "segments": 8,
        },
    }


@pytest.fixture
def designer(monkeypatch: pytest.MonkeyPatch, art: dict[str, Any]):
    result = SimpleNamespace(
        calls=[],
        status=0,
        output={
            "codex": json.dumps(art),
            "claude": json.dumps({"structured_output": art}),
        },
    )
    monkeypatch.setattr(shutil, "which", Mock(side_effect="/bin/{}".format))

    def run(argv: list[str], **kwargs: Any):
        from io import BytesIO

        result.calls.append(argv)
        if "exec" in argv:
            Path(argv[argv.index("-o") + 1]).write_text(result.output["codex"])
            assert argv[argv.index("--sandbox") + 1] == "read-only"
            assert "--ephemeral" in argv and "--output-schema" in argv
        else:
            assert argv[argv.index("--tools") + 1] == ""
            kwargs["stdout"].write(result.output["claude"].encode())
            kwargs["stdout"].flush()
        return SimpleNamespace(
            stdin=BytesIO(), poll=lambda: result.status, returncode=result.status
        )

    monkeypatch.setattr(subprocess, "Popen", run)
    return result


@pytest.fixture
def clip(tmp_path: Path):
    pytest.importorskip("PIL.Image")
    if not all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe")):
        pytest.skip("FFmpeg is an optional native video tool")

    def make(
        name: str,
        source: str,
        seconds: float = 1,
        *,
        audio: bool = False,
        options: Sequence[str] = (),
    ):
        path = tmp_path / name
        argv = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source]
        if audio:
            argv += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
        argv += ["-t", str(seconds), "-c:v", "libx264"]
        if audio:
            argv += ["-c:a", "aac"]
        subprocess.run([*argv, *options, str(path)], check=True, capture_output=True)
        return path

    return make
