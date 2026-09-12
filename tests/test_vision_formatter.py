"""Vision Format Engine 单元测试。"""
from __future__ import annotations

from app.vision_transcribe.formatter.engine import format_document
from app.vision_transcribe.formatter.page import repair_page_marker
from app.vision_transcribe.formatter.table import repair_table


def test_repair_page_marker_deduplicates_machine_markers():
    md = (
        "<!-- PDF2MD:PAGE:0001 -->\n"
        "alpha\n"
        "<!-- PDF2MD:PAGE:0001 -->\n"
        "beta\n"
    )
    out = repair_page_marker(md)
    assert out.count("PDF2MD:PAGE:0001") == 1
    assert "alpha" in out and "beta" in out


def test_repair_table_converts_tabs_and_inserts_separator():
    md = "A\tB\tC\n1\t2\t3\n"
    out = repair_table(md)
    assert "| A | B | C |" in out
    assert "| --- | --- | --- |" in out


def test_format_document_preserves_page_and_figure_markers():
    md = (
        "<!-- PDF2MD:PAGE:0001 -->\n"
        "1  Introduction  Model overview\n"
        "<!-- PDF2MD:FIGURE:p0001:f01 -->\n"
        "<!-- PDF2MD:PAGE_END:0001 -->\n"
        "<!-- PDF2MD:BATCH_END:0001 -->\n"
    )
    out = format_document(md)
    assert "PDF2MD:PAGE:0001" in out
    assert "PDF2MD:FIGURE:p0001:f01" in out
    assert "PDF2MD:PAGE_END:0001" in out
