"""Timey search behaviour and failure paths"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, Mock

import httpx
import pytest
from typer.testing import CliRunner

from uq_minis.cli import timey as wizard
from uq_minis.core import terminal
from uq_minis.core.common import MiniError
from uq_minis.minis.timey import video


class TestSearch:
    @pytest.mark.parametrize(
        "query",
        [
            "",
            "x",
            "x" * 201,
            "https://youtu.be/abcdefghijk",
            "~/film",
            "/film",
            "./film",
        ],
    )
    def test_local(self, predictions: Mock, query: str) -> None:
        assert asyncio.run(video.suggest(query)) == []
        predictions.assert_not_called()

    @pytest.mark.parametrize("state", ["valid", "malformed", "large", "offline", "denied"])
    def test_predict(self, predictions: Mock, state: str) -> None:
        if state == "valid":
            predictions.return_value = httpx.Response(
                200,
                json=[
                    "forest",
                    ["forest walk", "forest walk", "bad\x1btext", "x" * 201, 12],
                ],
            )
        elif state == "malformed":
            predictions.return_value = httpx.Response(200, json={"suggestions": []})
        elif state == "large":
            predictions.return_value = httpx.Response(200, content=b"x" * (16 * 1024 + 1))
        elif state == "offline":
            predictions.side_effect = httpx.ConnectError("Offline")
        else:
            predictions.return_value = httpx.Response(403)
        assert asyncio.run(video.suggest(" forest ")) == (
            ["forest walk"] if state == "valid" else []
        )
        request = predictions.call_args.args[0]
        assert request.url.params["q"] == "forest" and request.url.params["ds"] == "yt"

    def test_results(self, videos: tuple[Mock, MagicMock]) -> None:
        factory, client = videos
        client.extract_info.return_value["entries"] += [
            {"id": "abcdefghijk", "title": "Duplicate"},
            {"id": "bad/url", "title": "Untrusted ID"},
            {"id": "zyxwvutsrqp", "is_live": True},
            {
                "id": "12345678901",
                "title": "\x1b[31mForest\nwalk",
                "duration": float("inf"),
            },
            None,
        ]
        results = video.search(" forest ")
        assert len(results) == 2 and results[0]["length"] == "01:23"
        assert results[1]["length"] == "duration unavailable" and "\x1b" not in results[1]["title"]
        client.extract_info.assert_called_once_with("ytsearch5:forest", download=False)
        assert factory.call_args.args[0]["extract_flat"]
        assert all(
            result["url"].startswith("https://www.youtube.com/watch?v=") for result in results
        )

    def test_results_use_a_private_copy_of_google_cookies(
        self, videos: tuple[Mock, MagicMock], tmp_path: Path
    ) -> None:
        factory, _ = videos
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("private session")
        video.search("forest", cookies=cookies)
        private = Path(factory.call_args.args[0]["cookiefile"])
        assert private != cookies and not private.exists()

    @pytest.mark.parametrize("query", ["", "x" * 201])
    def test_query(self, videos: tuple[Mock, MagicMock], query: str) -> None:
        with pytest.raises(MiniError, match="200"):
            video.search(query)
        videos[0].assert_not_called()

    @pytest.mark.parametrize("failure", ["unavailable", "network", "malformed", "empty"])
    def test_failure(
        self,
        videos: tuple[Mock, MagicMock],
        monkeypatch: pytest.MonkeyPatch,
        failure: str,
    ) -> None:
        _, client = videos
        if failure == "unavailable":
            monkeypatch.setattr(video, "YoutubeDL", None)
        elif failure == "network":
            client.extract_info.side_effect = video.DownloadError("Offline")
        else:
            client.extract_info.return_value = [] if failure == "malformed" else None
        if failure == "empty":
            assert video.search("forest") == []
        else:
            with pytest.raises(MiniError):
                video.search("forest")

    @pytest.mark.parametrize(
        "answers",
        [
            "forest\nhttps://www.youtube.com/watch?v=abcdefghijk\n",
            "forest\nback\n\nhttps://www.youtube.com/watch?v=abcdefghijk\n",
        ],
    )
    def test_choose(
        self,
        videos: tuple[Mock, MagicMock],
        thumbnails: MagicMock,
        runner: CliRunner,
        answers: str,
    ) -> None:
        app = terminal.application()
        result: list[str] = []

        @app.command()
        def run():
            result.append(wizard._media("Choose a video"))

        invoked = runner.invoke(app, [], input=answers)
        assert invoked.exit_code == 0, invoked.output
        assert result == ["https://www.youtube.com/watch?v=abcdefghijk"]
        assert all(value in invoked.output for value in ("A quiet forest", "01:23"))

    def test_path(self, videos: tuple[Mock, MagicMock], runner: CliRunner) -> None:
        app = terminal.application()

        @app.command()
        def run():
            assert wizard._media("Choose a video") == "https://youtu.be/abcdefghijk"

        result = runner.invoke(app, [], input="~/missing-folder\nhttps://youtu.be/abcdefghijk\n")
        assert result.exit_code == 0, result.output
        videos[0].assert_not_called()
