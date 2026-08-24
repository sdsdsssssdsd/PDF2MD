# -*- coding: utf-8 -*-
"""写回时插入 \\tag{n} 还原 PDF 公式编号。"""
from __future__ import annotations

from app.formula.writeback import (
    build_display_block,
    equation_label_from_candidate_id,
    inject_equation_tag,
    latex_with_optional_tag,
)


def test_label_from_candidate_id():
    assert equation_label_from_candidate_id("page7_eq6") == "6"
    assert equation_label_from_candidate_id("page7_eqA.1") == "A.1"
    assert equation_label_from_candidate_id("page7_eq7_2") == "7"
    assert equation_label_from_candidate_id("page7_eqi2") == ""


def test_inject_tag_tpr_fpr():
    tpr = r"\mathrm{TPR}=\frac{\mathrm{TP}}{\mathrm{TP}+\mathrm{FN}}"
    out = inject_equation_tag(tpr, "6")
    assert out.endswith(r"\tag{6}")
    assert r"TPR" in out
    # 幂等
    out2 = inject_equation_tag(out, "6")
    assert out2.count(r"\tag{6}") == 1


def test_latex_with_optional_tag_display_block():
    body = latex_with_optional_tag(
        r"FPR=\frac{FP}{FP+TN}",
        candidate_id="page7_eq7",
        preserve=True,
    )
    assert r"\tag{7}" in body
    md = build_display_block(body)
    assert md.startswith("$$\n") and md.endswith("\n$$")
    assert r"\tag{7}" in md
    assert "$$\n" in md and "\n$$" in md


def test_build_display_block_multiline_not_inline():
    md = build_display_block(r"x=1\tag{1}")
    assert md == "$$\nx=1\\tag{1}\n$$"
    # 已包单行 $$ 也要拆成多行
    md2 = build_display_block(r"$$y=2$$")
    assert md2 == "$$\ny=2\n$$"


def test_preserve_false_skips_tag():
    body = latex_with_optional_tag(
        r"x=1",
        candidate_id="page1_eq1",
        preserve=False,
    )
    assert r"\tag" not in body
