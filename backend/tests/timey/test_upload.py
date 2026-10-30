"""Timey upload behaviour and failure paths"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from rich.text import Text

from uq_minis.cli import timey as wizard
from uq_minis.core.art import Preview
from uq_minis.core.common import MiniError
from uq_minis.minis.timey import youtube


class TestUpload:
    def test_thumbnail(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        image = tmp_path / "thumbnail.png"
        image.write_bytes(b"original image")
        path = tmp_path / "details.json"
        monkeypatch.setattr(
            wizard,
            "ask",
            Mock(side_effect=["Title", "Description", "timer", "private", "custom", str(image)]),
        )
        monkeypatch.setattr(wizard, "confirm", Mock(side_effect=[False, False, True, False]))
        monkeypatch.setattr(wizard, "picture", Mock(return_value=Preview(Text("image"), "Image")))
        wizard._upload_details(path, "Title", metadata=False)
        assert image.read_bytes() == b"original image"
        assert youtube.read_details(path)["thumbnail"] == str(image)

    def test_metadata(self, draft: dict[str, Any]) -> None:
        data = draft
        assert "tags" not in youtube.validate(data)["snippet"]
        data["status"]["publishAt"] = "2099-01-01T18:00:00+10:00"
        assert youtube.validate(data)["status"]["publishAt"].endswith("+10:00")

    @pytest.mark.parametrize(
        "section,change",
        [
            ("status", {"privacyStatus": "public"}),
            ("status", {"publishAt": "2099-01-01T18:00:00"}),
            ("status", {"publishAt": "2000-01-01T18:00:00Z"}),
            ("status", {"selfDeclaredMadeForKids": "no"}),
            ("status", {"privacyStatus": []}),
            ("snippet", {"title": "<bad>"}),
            ("snippet", {"description": "🦊" * 1251}),
            ("snippet", {"tags": ["x" * 501]}),
            ("snippet", {"tags": "timer"}),
            ("snippet", {"tags": [""]}),
            ("snippet", {"categoryId": "gaming"}),
            ("snippet", {"defaultLanguage": "English"}),
            ("status", {"publishAt": "tomorrow"}),
            ("status", {"embeddable": "yes"}),
            ("status", {"license": "unknown"}),
            (None, {"notifySubscribers": "yes"}),
            (None, {"thumbnail": []}),
            (None, {"snippet": []}),
            (None, {"status": []}),
        ],
        ids=[
            "public-schedule",
            "naive-date",
            "past-date",
            "audience-type",
            "visibility-type",
            "title",
            "description-size",
            "tags-size",
            "tags-type",
            "empty-tag",
            "category",
            "language",
            "date-format",
            "embedding",
            "licence",
            "notifications",
            "thumbnail",
            "snippet-type",
            "status-type",
        ],
    )
    def test_invalid(
        self, draft: dict[str, Any], section: None | str, change: dict[str, Any]
    ) -> None:
        draft["status"]["publishAt"] = "2099-01-01T18:00:00+10:00"
        (draft[section] if section else draft).update(change)
        with pytest.raises(MiniError):
            youtube.validate(draft)

    @pytest.mark.parametrize(
        "content",
        ["{broken", "[]", " " * 65537],
        ids=["invalid-json", "wrong-shape", "too-large"],
    )
    def test_draft(self, tmp_path: Path, content: Any) -> None:
        draft = tmp_path / "details.json"
        draft.write_text(content)
        with pytest.raises(MiniError):
            youtube.read_details(draft)

    def test_chunks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        if youtube.build is None:
            pytest.skip("Google's upload client is an optional Timey dependency")
        data = {
            "snippet": {"title": "Timer"},
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": False,
            },
        }
        video, draft, token, thumbnail = (
            tmp_path / name for name in ("timer.mp4", "details.json", "token.json", "thumb.png")
        )
        video.write_bytes(b"video")
        token.write_text("{}")
        thumbnail.write_bytes(b"png")
        draft.write_text(json.dumps({**data, "thumbnail": str(thumbnail)}))
        credentials = SimpleNamespace(
            valid=True, expired=False, to_json=lambda: '{"token":"private"}'
        )
        monkeypatch.setattr(
            youtube.Credentials, "from_authorized_user_file", Mock(return_value=credentials)
        )
        replies = iter([
            (SimpleNamespace(progress=lambda: 0.5), None),
            (None, {"id": "abcdefghijk", "status": {"privacyStatus": "private"}}),
        ])
        called: list[dict[str, Any]] = []
        closed: list[bool] = []
        progress: list[float | None] = []

        def insert(**kwargs: Any):
            called.append(kwargs)
            return SimpleNamespace(next_chunk=Mock(side_effect=replies))

        def thumbnail_set(**kwargs: Any):
            assert video.with_suffix(".uploaded.json").exists()
            raise youtube.HttpError(SimpleNamespace(status=403, reason="Forbidden"), b"{}")

        service = SimpleNamespace(
            videos=lambda: SimpleNamespace(insert=insert),
            thumbnails=lambda: SimpleNamespace(set=thumbnail_set),
            close=lambda: closed.append(True),
        )
        monkeypatch.setattr(youtube, "build", Mock(return_value=service))
        with pytest.raises(MiniError, match="Video uploaded to .*thumbnail failed"):
            youtube.upload(
                video,
                draft,
                tmp_path / "missing-client.json",
                token,
                progress=lambda done, stage: progress.append(done),
            )
        assert [done for done in progress if done is not None] == [0.5] and closed == [True]
        if os.name == "posix":
            assert token.stat().st_mode & 0o777 == 0o600
        assert called[0]["media_body"].resumable()
        assert called[0]["media_body"].chunksize() == 8 * 1024 * 1024
        assert not called[0]["notifySubscribers"]
        with pytest.raises(MiniError, match="upload receipt"):
            youtube.upload(video, draft, tmp_path / "missing-client.json", token)
        assert len(called) == 1
