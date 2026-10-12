import gzip
import json
from zipfile import ZipFile

import pytest

from uq_minis.core.common import MiniError
from uq_minis.minis.event import rooms
from uq_minis.minis.event.pipeline import generate

CSV = """campus,building,room,kind,seats,tour
St Lucia,Test Hall,99-001,Learning Theatre,80,https://tour.panoee.net/example
St Lucia,Test Hall,99-002,Seminar,26,
"""


class TestRooms:
    def test_select(self, event_toml, tmp_path, monkeypatch):
        catalogue = tmp_path / "rooms.csv"
        catalogue.write_text(CSV)
        original = event_toml.read_bytes()
        answers = iter([
            "St Lucia",
            "invalid",
            "20",
            "99 · Test Hall",
            "99-001 · 80 seats · Learning Theatre",
            "tour",
            "back",
            "99 · Test Hall",
            "99-002 · 26 seats · Seminar",
            "select",
            "21-50",
        ])
        monkeypatch.setattr(rooms, "ask", lambda *args, **kwargs: next(answers))
        tours = []
        monkeypatch.setattr(rooms.webbrowser, "open", lambda url: tours.append(url) or True)
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
        ],
    )
    def test_invalid(self, tmp_path, row):
        path = tmp_path / "rooms.csv"
        path.write_text(CSV.splitlines()[0] + "\n" + row)
        with pytest.raises(MiniError, match="Cannot read room catalogue"):
            rooms.read(path)

    def test_catalogue(self, event_toml, tmp_path, monkeypatch):
        monkeypatch.setattr(rooms, "STATE", tmp_path)
        catalogue = rooms.read()
        assert {room.campus for room in catalogue} == {"St Lucia", "Gatton", "Herston", "Other"}
        assert len(catalogue) > 100
        assert all(room.seats > 0 for room in catalogue)
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
        [b"broken", gzip.compress(CSV.encode())[:-6], gzip.compress(b"x" * (1024 * 1024 + 1))],
    )
    def test_compressed(self, tmp_path, data):
        path = tmp_path / "rooms.csv.gz"
        path.write_bytes(data)
        with pytest.raises(MiniError, match="Cannot read room catalogue"):
            rooms.read(path)
