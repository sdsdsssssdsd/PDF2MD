# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from app.formula.gold_harvest import harvest_page, harvest_pdf, is_right_margin_eq_label


def test_right_margin_label_rules():
    assert is_right_margin_eq_label("(1)", 300.0, 420.0) == "1"
    assert is_right_margin_eq_label("（2）", 300.0, 420.0) == "2"
    assert is_right_margin_eq_label("(1)", 40.0, 420.0) == ""
    assert is_right_margin_eq_label("1 Introduction", 40.0, 420.0) == ""
    assert is_right_margin_eq_label("9", 380.0, 420.0) == ""
    assert is_right_margin_eq_label("Eq. (4):", 300.0, 420.0) == ""
    # 双栏左栏右缘（约页宽 44%），不是页左列表号
    assert is_right_margin_eq_label("（1）", 260.0, 595.0) == "1"
    assert is_right_margin_eq_label("(7)", 180.0, 420.0) == "7"


def test_harvest_page_takes_formula_not_section(tmp_path: Path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=420, height=280)
    page.insert_text((24, 40), "1 Introduction", fontsize=14)
    page.insert_text((40, 120), "E = mc^2", fontsize=11)
    page.insert_text((360, 120), "(1)", fontsize=11)
    page.insert_text((40, 180), "See Eq. (1) in the text", fontsize=10)
    path = tmp_path / "h.pdf"
    doc.save(path)
    doc.close()
    doc = pymupdf.open(str(path))
    hits = harvest_page(doc[0], 0)
    doc.close()
    assert [h.equation_number for h in hits] == ["1"]
    assert "E" in hits[0].preview or "mc" in hits[0].preview


def test_harvest_chinese_fullwidth(tmp_path: Path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=420, height=200)
    page.insert_text((40, 90), "J = x^T Q x + u^T R u", fontsize=11)
    page.insert_text((360, 90), "（1）", fontsize=11, fontname="china-ss")
    path = tmp_path / "zh.pdf"
    doc.save(path)
    doc.close()
    rows = harvest_pdf(path, pdf_id="zh_demo", language="zh", per_paper=3, skip_cover=False)
    assert len(rows) == 1
    assert rows[0]["equation_number"] == "1"
    assert rows[0]["language"] == "zh"
    assert rows[0]["verified"] is False
    assert "do_not_train" in rows[0]["notes"]


def test_harvest_left_column_right_margin(tmp_path: Path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=520, height=200)
    # 左栏公式右缘紧贴编号，与中文双栏期刊一致（编号约在页宽 38%）
    page.insert_text((20, 90), "mb*xbdd = Cs*(xtd-xbd)+u(t)", fontsize=11)
    page.insert_text((200, 90), "（1）", fontsize=11, fontname="china-ss")
    page.insert_text((300, 90), "X = (a + b) / 2", fontsize=11)
    page.insert_text((480, 90), "(3)", fontsize=11)
    path = tmp_path / "twocol_left.pdf"
    doc.save(path)
    doc.close()
    doc = pymupdf.open(str(path))
    hits = harvest_page(doc[0], 0)
    doc.close()
    assert [h.equation_number for h in hits] == ["1", "3"]
    assert any("xbdd" in h.preview or "mb" in h.preview for h in hits if h.equation_number == "1")


def test_harvest_drops_chinese_other_column(tmp_path: Path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=520, height=200)
    page.insert_text((20, 90), "为提高樽海鞘算法在求解问题时的收敛速度", fontsize=10)
    page.insert_text((300, 90), "X = (a + b) / 2", fontsize=11)
    page.insert_text((480, 90), "(3)", fontsize=11)
    path = tmp_path / "twocol.pdf"
    doc.save(path)
    doc.close()
    doc = pymupdf.open(str(path))
    hits = harvest_page(doc[0], 0)
    doc.close()
    assert [h.equation_number for h in hits] == ["3"]
    assert "为提高" not in hits[0].preview
    assert "X" in hits[0].preview
