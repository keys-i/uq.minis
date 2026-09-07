from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from uq_minis.helper.risk_docx import build_form_document, build_pack_document, load_event_config


def page_breaks(path: Path) -> int:
    with ZipFile(path) as archive:
        return archive.read("word/document.xml").count(b'w:type="page"')


def table_text(document: object) -> str:
    return "\n".join(
        cell.text for table in document.tables for row in table.rows for cell in row.cells
    )


def test_form_and_pack_are_rebuilt_from_event_data(event_toml: Path, tmp_path: Path) -> None:
    config = load_event_config(event_toml)
    form = build_form_document(config)
    pack = build_pack_document(config)
    form_path = tmp_path / "form.docx"
    pack_path = tmp_path / "pack.docx"
    form.save(form_path)
    pack.save(pack_path)

    assert page_breaks(form_path) == 6
    assert page_breaks(pack_path) == 7
    assert "EVENT MANAGEMENT RISK ASSESSMENT" in table_text(form)
    assert "SAMPLE EVENT PACK" in table_text(pack)
    assert "External Attendees" in table_text(pack)
    assert "UQ Sample Club" in table_text(form)
    assert "THIS SECTION TO BE COMPLETED BY THE UNIVERSITY OF QUEENSLAND ONLY" in table_text(pack)
