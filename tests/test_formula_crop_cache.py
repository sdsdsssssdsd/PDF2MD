# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from app.formula.crop_cache import (
    language_from_stem,
    page_index_candidates,
    render_formula_crop,
    resolve_pdf,
    write_crop_png,
)


def test_language_from_stem():
    assert language_from_stem("01_车辆悬架鲁棒控制") == "zh"
    assert language_from_stem("O-018_Abdo2025_Stacking_SHAP") == "en"
    assert language_from_stem("01_Attention_Is_All_You_Need") == "en"


def test_page_index_candidates():
    assert page_index_candidates(7, 10) == [7, 6]
    assert page_index_candidates(0, 10) == [0]


def test_resolve_pdf_testset():
    p = resolve_pdf("01_Attention_Is_All_You_Need")
    assert p is not None
    assert p.is_file()


def test_render_and_hash_synthetic(tmp_path: Path):
    import pymupdf

    pdf = tmp_path / "tiny.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 80), "E = mc^2")
    doc.save(pdf)
    doc.close()
    im, idx = render_formula_crop(pdf, 1, [10, 40, 160, 120], scale=2.0)
    assert idx == 0
    dest = tmp_path / "crop.png"
    w, h, digest = write_crop_png(im, dest)
    assert dest.is_file()
    assert w >= 8 and h >= 8
    assert len(digest) == 16
