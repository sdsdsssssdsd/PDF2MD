# -*- coding: utf-8 -*-
"""O-018 Eq.6 / Eq.7 对齐回归 fixture（无 GPU）。

记录：同页无明确编号且恢复结果高度相似时，必须跳过自动写回。
"""
from __future__ import annotations

from app.formula.config import formula_config_for_deepseek_limited_production
from app.formula.writeback import (
    FormulaWritebackManager,
    RecoveryWritebackItem,
    register_display_formulas_by_order,
)

# 来自真实 QA：page7 两条曾都像 FPR
FPR = r"\mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}"
TPR = r"\mathrm{TPR}=\frac{\mathrm{TP}}{\mathrm{TP}+\mathrm{FN}}"


def test_o018_eq6_eq7_duplicate_fpr_blocked():
    md = "# O-018\n\n$$garbage1$$\n\n$$garbage2$$\n"
    ids = ["page7_eqi1", "page7_eqi2"]
    reg = register_display_formulas_by_order(md, ids)
    cfg = formula_config_for_deepseek_limited_production()
    items = [
        RecoveryWritebackItem(
            candidate_id="page7_eqi1",
            recovered_latex=FPR,
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=7,
        ),
        RecoveryWritebackItem(
            candidate_id="page7_eqi2",
            recovered_latex=FPR,
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=7,
        ),
    ]
    report = FormulaWritebackManager(cfg).apply(md, items, reg)
    assert report.applied_count == 0
    assert {e.skip_reason for e in report.entries} == {"multi_formula_alignment_ambiguous"}


def test_o018_eq6_eq7_bound_ids_allow_distinct():
    """结构绑定 page7_eq6/eq7 后，即使内容需 Gate，身份不再 ambiguous。"""
    from app.formula.equation_identity import bind_equation_identities

    md = (
        "TPR using Eq. (6), against FPR using Eq. (7) at thresholds.\n\n"
        "<!-- formula-not-decoded -->\n\n"
        "<!-- formula-not-decoded -->\n"
    )
    ids = bind_equation_identities(md)
    assert [ids[k].equation_number for k in sorted(ids)] == ["6", "7"]


def test_o018_eq6_eq7_distinct_tpr_fpr_allowed():
    md = "# O-018\n\n$$garbage1$$\n\n$$garbage2$$\n"
    ids = ["page7_eq6", "page7_eq7"]
    reg = register_display_formulas_by_order(md, ids)
    cfg = formula_config_for_deepseek_limited_production()
    items = [
        RecoveryWritebackItem(
            candidate_id="page7_eq6",
            recovered_latex=TPR,
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=7,
        ),
        RecoveryWritebackItem(
            candidate_id="page7_eq7",
            recovered_latex=FPR,
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=7,
        ),
    ]
    report = FormulaWritebackManager(cfg).apply(md, items, reg)
    assert report.applied_count == 2
