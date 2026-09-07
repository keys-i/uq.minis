from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest


def test_agent_protocol_generates_preview_and_survives_bad_calls(event_toml, tmp_path):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def exercise():
        # A preview must never reach submission, even when an event TOML requests it.
        entry = (
            "from unittest.mock import patch; from uq_minis.cli import main; "
            "guard=patch('uq_minis.helper.forms.submit_payload', side_effect=AssertionError('Unexpected submission')); "
            "guard.start(); main()"
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", entry, "agents"],
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        async with stdio_client(params) as streams, ClientSession(*streams) as session:
            await session.initialize()
            catalog = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert "event_generate" in catalog and "scrappy_links" in catalog
            assert catalog["event_generate"].annotations.open_world_hint is False
            assert catalog["event_submit"].annotations.open_world_hint is True
            arguments = {
                "source": str(event_toml),
                "form": True,
                "risk": False,
                "output": str(tmp_path / "outputs"),
            }
            result = await session.call_tool("event_generate", arguments)
            assert not result.is_error, result
            generated = result.structured_content["outputs"][0]
            assert generated["kind"] == "form"
            assert len(json.loads(Path(generated["path"]).read_text())["answers"]) > 100
            repeated = await session.call_tool("event_generate", arguments)
            assert repeated.is_error  # No silent overwrites.
            invalid = await session.call_tool("event_generate", {**arguments, "form": False})
            assert invalid.is_error
            status = await session.call_tool(
                "watcher_status", {"state_dir": str(tmp_path / "state")}
            )
            assert not status.is_error and status.structured_content == {"events": []}
            watched = await session.call_tool(
                "watcher_watch",
                {
                    "source": str(event_toml),
                    "event_id": "MCP1",
                    "state_dir": str(tmp_path / "state"),
                },
            )
            assert not watched.is_error and watched.structured_content["state"] == "waiting_request"
            retry = await session.call_tool(
                "watcher_retry", {"event_id": "MCP1", "state_dir": str(tmp_path / "state")}
            )
            assert retry.is_error and "Sent Items" in retry.content[0].text
            stopped = await session.call_tool(
                "watcher_stop", {"event_id": "MCP1", "state_dir": str(tmp_path / "state")}
            )
            assert not stopped.is_error and stopped.structured_content["state"] == "stopped"
            html = tmp_path / "search.html"
            html.write_text(
                '<h2 class="trigger"><a class="code">COMP3400</a><a class="title">Logic</a></h2><a href="/course.html?course_code=COMP3400">View all previous offerings</a>'
            )
            links = await session.call_tool(
                "scrappy_links", {"html": str(html), "output": str(tmp_path / "links.csv")}
            )
            assert not links.is_error and links.structured_content["count"] == 1
            assert "COMP3400" in Path(links.structured_content["path"]).read_text()
            listed = await session.call_tool(
                "scrappy_list",
                {
                    "offerings": links.structured_content["path"],
                    "query": "logic",
                    "limit": 1,
                },
            )
            assert not listed.is_error and listed.structured_content["total"] == 1
            assert listed.structured_content["courses"][0]["course_code"] == "COMP3400"
            assert catalog["scrappy_list"].annotations.read_only_hint is True

    event_toml.write_text(event_toml.read_text().replace('action = "preview"', 'action = "submit"'))
    asyncio.run(exercise())


def test_explicit_submission_uses_submit_and_returns_no_credentials(
    event_toml, tmp_path, monkeypatch
):
    pytest.importorskip("mcp")
    from uq_minis.minis import event
    from uq_minis.minis.event.pipeline import RunResult
    from uq_minis_tools.agents import create_server

    calls = []

    def submit(source, **options):
        calls.append((source, options))
        return RunResult(outputs=(("form", tmp_path / "form.json"),), submissions=((source, 200),))

    monkeypatch.setattr(event, "generate", submit)
    result = asyncio.run(create_server().call_tool("event_submit", {"source": str(event_toml)}))
    assert not result.is_error
    assert calls[0][0] == event_toml
    assert calls[0][1]["form_action"] == "submit" and calls[0][1]["mode"] == "form"
    assert set(result.structured_content) == {"outputs", "submissions"}
    assert result.structured_content["submissions"] == [{"source": str(event_toml), "status": 200}]
