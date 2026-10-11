from __future__ import annotations

from zipfile import ZipFile

import pytest

from uq_minis.core.risk_docx import (
    build_form_document,
    build_pack_document,
    load_event_config,
)


@pytest.mark.parametrize(
    "build,pages,labels",
    [
        (build_form_document, 6, ["EVENT MANAGEMENT RISK ASSESSMENT", "UQ Sample Club"]),
        (
            build_pack_document,
            7,
            [
                "SAMPLE EVENT PACK",
                "External Attendees",
                "THIS SECTION TO BE COMPLETED BY THE UNIVERSITY OF QUEENSLAND ONLY",
            ],
        ),
    ],
    ids=["form", "pack"],
)
def test_build(event_toml, tmp_path, build, pages, labels):
    document = build(load_event_config(event_toml))
    path = tmp_path / "risk.docx"
    document.save(path)
    with ZipFile(path) as archive:
        assert archive.read("word/document.xml").count(b'w:type="page"') == pages
    text = "\n".join(
        cell.text for table in document.tables for row in table.rows for cell in row.cells
    )
    assert all(label in text for label in labels)
