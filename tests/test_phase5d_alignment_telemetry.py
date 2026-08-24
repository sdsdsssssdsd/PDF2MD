# -*- coding: utf-8 -*-
"""Phase 5D：写回对齐一致性 + Docling 遥测（无 GPU）。"""
from __future__ import annotations

from app.engines.docling_telemetry import (
    get_docling_telemetry,
    record_converter_access,
    record_convert_phases,
    reset_docling_telemetry,
)
from app.formula.config import formula_config_for_deepseek_limited_production
from app.formula.writeback import (
    FormulaWritebackManager,
    RecoveryWritebackItem,
    candidate_eq_ambiguous,
    find_multi_formula_alignment_conflicts,
    latex_signature_similarity,
    register_display_formulas_by_order,
)


def test_similarity_fpr_duplicate():
    a = r"\mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}"
    b = r"\mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}"
    assert latex_signature_similarity(a, b) > 0.99


def test_eq_ambiguous_eqi():
    assert candidate_eq_ambiguous("page7_eqi1") is True
    assert candidate_eq_ambiguous("page6_eq1") is False


def test_alignment_conflict_blocks_both():
    items = [
        RecoveryWritebackItem(
            candidate_id="page7_eqi1",
            recovered_latex=r"\mathrm{FPR}=\frac{FP}{FP+TN}",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=7,
        ),
        RecoveryWritebackItem(
            candidate_id="page7_eqi2",
            recovered_latex=r"\mathrm{FPR}=\frac{FP}{FP+TN}",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=7,
        ),
    ]
    conf = find_multi_formula_alignment_conflicts(items)
    assert conf == {"page7_eqi1", "page7_eqi2"}


def test_writeback_skips_ambiguous_duplicates():
    md = "# t\n\n$$a$$\n\n$$b$$\n"
    ids = ["page7_eqi1", "page7_eqi2"]
    reg = register_display_formulas_by_order(md, ids)
    cfg = formula_config_for_deepseek_limited_production()
    items = [
        RecoveryWritebackItem(
            candidate_id="page7_eqi1",
            recovered_latex=r"FPR=\frac{FP}{FP+TN}",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=7,
        ),
        RecoveryWritebackItem(
            candidate_id="page7_eqi2",
            recovered_latex=r"FPR=\frac{FP}{FP+TN}",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=7,
        ),
    ]
    report = FormulaWritebackManager(cfg).apply(md, items, reg)
    assert report.applied_count == 0
    assert all(
        e.skip_reason == "multi_formula_alignment_ambiguous" for e in report.entries
    )


def test_docling_telemetry_reuse_counters():
    reset_docling_telemetry()
    record_converter_access(created=True, key="k1", init_seconds=1.5)
    record_converter_access(created=False, key="k1")
    phases = record_convert_phases(init_seconds=0.1, convert_seconds=2.0, export_seconds=0.2)
    t = get_docling_telemetry()
    assert t.converter_create_count == 1
    assert t.converter_reuse_count == 1
    assert phases["converter_reused"] is True
    assert phases["docling_convert_seconds"] == 2.0
