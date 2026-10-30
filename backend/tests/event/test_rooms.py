import gzip
import json
import webbrowser
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from uq_minis.core.common import MiniError
from uq_minis.minis.event import rooms
from uq_minis.minis.event.pipeline import generate

CSV = """campus,building,room,kind,seats,tour,photo
St Lucia,Test Hall,99-001,Learning Theatre,80,https://tour.panoee.net/example,https://campuses.uq.edu.au/files/room.jpg
St Lucia,Test Hall,99-002,Seminar,26,,
"""


class TestRooms:
    @pytest.mark.parametrize("key", ["left", "right"])
    def test_shortcut(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str) -> None:
        catalogue = tmp_path / "rooms.csv"
        catalogue.write_text(CSV)
        answers = iter([
            "St Lucia",
            "99 · Test Hall",
            "99-001 · 80 seats · Learning Theatre",
            "select",
        ])

        def pick(message: str, **options: Any) -> str:
            answer = next(answers)
            if message.startswith("Room"):
                action = options["actions"][key][1]
                with pytest.raises(MiniError, match="Highlight a room"):
                    action("")
                with pytest.raises(MiniError, match="No (photo|virtual tour)"):
                    action("99-002 · 26 seats · Seminar")
                action(answer)
            return answer

        opened = Mock(return_value=True)
        monkeypatch.setattr(rooms, "ask", pick)
        monkeypatch.setattr(rooms, "number", Mock(return_value=20))
        monkeypatch.setattr(webbrowser, "open", opened)
        raw: dict[str, Any] = {}
        rooms.choose(raw, catalogue)
        opened.assert_called_once_with(
            "https://tour.panoee.net/example"
            if key == "left"
            else "https://campuses.uq.edu.au/files/room.jpg"
        )
        assert raw["event"]["room"] == "99-001"

    def test_select(
        self, event_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        catalogue = tmp_path / "rooms.csv"
        catalogue.write_text(CSV)
        original = event_toml.read_bytes()
        answers = iter([
            "St Lucia",
            "99 · Test Hall",
            "99-001 · 80 seats · Learning Theatre",
            "tour",
            "back",
            "99 · Test Hall",
            "99-002 · 26 seats · Seminar",
            "select",
            "21-50",
        ])
        monkeypatch.setattr(rooms, "ask", Mock(side_effect=answers))
        seats = Mock(return_value=20)
        monkeypatch.setattr(rooms, "number", seats)
        tours: list[str] = []

        def tour(url: str) -> bool:
            tours.append(url)
            return True

        monkeypatch.setattr(webbrowser, "open", tour)
        result = generate(
            event_toml,
            mode="both",
            risk_layout="form",
            interactive=True,
            choose_room=True,
            rooms=catalogue,
            destination=tmp_path / "out",
            jobs=1,
        )
        assert tours == ["https://tour.panoee.net/example"]
        assert seats.call_args.kwargs == {
            "default": 20,
            "minimum": 0,
            "maximum": 80,
            "unit": " seats",
        }
        outputs = dict(result.outputs)
        payload = json.loads(outputs["form"].read_text())
        assert "99-002" in str(payload) and "03-309" not in str(payload)
        with ZipFile(outputs["risk-form"]) as document:
            assert "99-002" in document.read("word/document.xml").decode()
        assert event_toml.read_bytes() == original

    @pytest.mark.parametrize(
        "row",
        [
            "St Lucia,Test Hall,99-001,Theatre,0,",
            "St Lucia,Test Hall,99-001,Theatre,20,javascript:alert(1)",
            "St Lucia,Test Hall,99-001,Theatre,20,https://tour.panoee.net@example.org/tour",
            "St Lucia,Test Hall,99-001,Theatre,20,https://tour.panoee.net:1234/tour",
            "St Lucia,Test Hall,99-001,Theatre,20,,javascript:alert(1)",
            "St Lucia,Test Hall,99-001,Theatre,20,,https://campuses.uq.edu.au@evil.org/photo.jpg",
            "St Lucia,Test Hall,99-001,Theatre,20,,https://campuses.uq.edu.au:1234/photo.jpg",
        ],
    )
    def test_invalid(self, tmp_path: Path, row: str) -> None:
        path = tmp_path / "rooms.csv"
        path.write_text(CSV.splitlines()[0] + "\n" + row)
        with pytest.raises(MiniError, match="Cannot read room catalogue"):
            rooms.read(path)

    def test_catalogue(
        self, event_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rooms, "STATE", tmp_path)
        catalogue = rooms.read()
        assert {room.campus for room in catalogue} == {
            "St Lucia",
            "Gatton",
            "Herston",
            "Other",
        }
        assert len(catalogue) > 100
        assert all(room.seats > 0 for room in catalogue)
        assert sum(bool(room.photo) for room in catalogue) == 225
        custom = tmp_path / "event/rooms.csv"
        custom.parent.mkdir()
        custom.write_text(CSV)
        assert len(rooms.read()) == 2
        custom.write_text(CSV + CSV.splitlines()[1] + "\n")
        with pytest.raises(MiniError, match="duplicate"):
            rooms.read()
        with pytest.raises(MiniError, match="interactive"):
            generate(event_toml, choose_room=True)

    @pytest.mark.parametrize(
        "data",
        [
            b"broken",
            gzip.compress(CSV.encode())[:-6],
            gzip.compress(b"x" * (1024 * 1024 + 1)),
        ],
    )
    def test_compressed(self, tmp_path: Path, data: Any) -> None:
        path = tmp_path / "rooms.csv.gz"
        path.write_bytes(data)
        with pytest.raises(MiniError, match="Cannot read room catalogue"):
            rooms.read(path)
