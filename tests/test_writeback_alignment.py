# -*- coding: utf-8 -*-
"""写回对齐：Shadow 匹配 + 页码一致（不二次 Gate）。"""
from __future__ import annotations

import json
from pathlib import Path

from app.formula.config import FormulaConfig
from app.formula.deepseek_production_pass import (
    make_pending_display_block,
    register_marked_blocks,
)
from app.formula.types import FormulaCandidate
from app.formula.writeback import (
    FormulaWritebackManager,
    RecoveryWritebackItem,
)
from app.formula.writeback_context_gate import pages_consistent
from app.formula.writeback_match import (
    build_pending_indexes,
    match_shadow_row_to_pending,
)


def _cfg() -> FormulaConfig:
    return FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=False,
        deepseek_writeback_require_high_confidence=True,
    )


def test_match_shadow_row_by_candidate_id_not_fallback():
    cand_a = FormulaCandidate(text="a", page=4, candidate_id="page4_eqi3")
    cand_b = FormulaCandidate(text="b", page=8, candidate_id="page8_eqi1")
    pending = [("page4_eqi3", cand_a), ("page8_eqi1", cand_b)]
    by_id, by_pe = build_pending_indexes(pending)
    used: set[str] = set()
    cid = match_shadow_row_to_pending(
        {"candidate_id": "page8_eqi1", "page": 8, "eq_number": "i1"},
        by_id,
        by_pe,
        used=used,
    )
    assert cid == "page8_eqi1"
    used.add(cid or "")
    assert (
        match_shadow_row_to_pending(
            {"candidate_id": "p8_eqx_999", "page": 4, "eq_number": "x"},
            by_id,
            by_pe,
            used=used,
        )
        is None
    )


def test_page0_placeholder_allows_ocr_page_at_writeback():
    """Lean 入队 page0_eqiN：OCR 实测页码不应挡写回。"""
    assert pages_consistent("page0_eqi4", 8) is True
    md = make_pending_display_block("page0_eqi4", r"\quad garbage") + "\n"
    reg = register_marked_blocks(md)
    items = [
        RecoveryWritebackItem(
            candidate_id="page0_eqi4",
            recovered_latex=r"\mathrm{VI}(t,t')=\mathrm{VI}(\widehat{H}(t),\widehat{H}(t'))",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            gate_decision="ACCEPT_HIGH_CONFIDENCE",
            page=8,
        )
    ]
    report = FormulaWritebackManager(_cfg()).apply(md, items, reg)
    assert report.applied_count == 1
    assert "VI" in report.markdown_after


def test_alignment_duplicate_vl_picks_context_winner():
    """同页重复 Vl 恢复：按 context 拆槽，赢的一侧写回（O-003）。"""
    md = (
        make_pending_display_block("page9_eqi4", r"\quad garbage")
        + "\n\n"
        + make_pending_display_block("page9_eqi6", r"\quad garbage")
        + "\n"
    )
    reg = register_marked_blocks(md)
    vl = (
        r"\begin{aligned}V l(t)=\frac{1}{\ell(\ell-1)}"
        r"\sum_{i\neq j}V l(H_{l}^{*}(t),H_{j}^{*}(t)).\end{aligned}"
    )
    items = [
        RecoveryWritebackItem(
            candidate_id="page9_eqi4",
            recovered_latex=vl,
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            gate_decision="ACCEPT_HIGH_CONFIDENCE",
            page=9,
            context_before="partition quality Vl(t) at time t using",
        ),
        RecoveryWritebackItem(
            candidate_id="page9_eqi6",
            recovered_latex=vl,
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            gate_decision="ACCEPT_HIGH_CONFIDENCE",
            page=9,
            context_before="unrelated prose about Louvain stability only",
        ),
    ]
    report = FormulaWritebackManager(_cfg()).apply(md, items, reg)
    assert report.applied_count == 1
    applied = [e for e in report.entries if e.writeback_applied]
    assert len(applied) == 1
    assert applied[0].candidate_id == "page9_eqi4"


def test_page_mismatch_blocked_at_writeback():
    assert pages_consistent("page4_eqi3", 8) is False
    md = make_pending_display_block("page4_eqi3", r"\quad garbage") + "\n"
    reg = register_marked_blocks(md)
    items = [
        RecoveryWritebackItem(
            candidate_id="page4_eqi3",
            recovered_latex=r"\frac{TP}{TP+FP}",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            gate_decision="ACCEPT_HIGH_CONFIDENCE",
            page=8,
        )
    ]
    report = FormulaWritebackManager(_cfg()).apply(md, items, reg)
    assert report.applied_count == 0
    assert report.entries[0].skip_reason == "candidate_page_mismatch"


def test_eqi_slot_writes_back_when_gate_accepted():
    """eqi 槽位：OCR Gate 已 accept 则允许写回（不在写回层二次否决）。"""
    md = make_pending_display_block("page7_eqi4", r"\quad garbage") + "\n"
    reg = register_marked_blocks(md)
    items = [
        RecoveryWritebackItem(
            candidate_id="page7_eqi4",
            recovered_latex=r"\mathrm{F1}_{c}=\frac{2\cdot P\cdot R}{P+R}",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            gate_decision="ACCEPT_HIGH_CONFIDENCE",
            page=7,
        )
    ]
    report = FormulaWritebackManager(_cfg()).apply(md, items, reg)
    assert report.applied_count == 1
    assert "F1" in report.markdown_after


def test_o018_precision_not_blocked_by_roc_in_distant_context():
    """上下文含 ROC-AUC 字样时，Precision 式仍应写回。"""
    md = make_pending_display_block("page6_eq3", r"\quad garbage") + "\n"
    reg = register_marked_blocks(md)
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq3",
            recovered_latex=r"\mathrm{Precision}=\frac{\mathrm{TP}}{\mathrm{TP}+\mathrm{FP}}",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            gate_decision="ACCEPT_HIGH_CONFIDENCE",
            context_before="ROC-AUC of 0.97 in the abstract. Precision per class:",
            page=6,
        )
    ]
    report = FormulaWritebackManager(_cfg()).apply(md, items, reg)
    assert report.applied_count == 1


def test_numbered_eq6_still_writes_back():
    md = make_pending_display_block("page7_eq6", r"\quad garbage") + "\n"
    reg = register_marked_blocks(md)
    items = [
        RecoveryWritebackItem(
            candidate_id="page7_eq6",
            recovered_latex=r"\mathrm{TPR}=\frac{\mathrm{TP}}{\mathrm{TP}+\mathrm{FN}}",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            gate_decision="ACCEPT_HIGH_CONFIDENCE",
            context_before="True Positive Rate (TPR) using Eq. (6)",
            page=7,
        )
    ]
    report = FormulaWritebackManager(_cfg()).apply(md, items, reg)
    assert report.applied_count == 1
    assert "TPR" in report.markdown_after


def test_anomaly_manifest_loads():
    path = Path(__file__).resolve().parent / "fixtures" / "anomaly_manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = {d["id"] for d in data["documents"]}
    assert "O-003_Peach2019_DataDrivenClustering" in ids
    assert "en_O-028_Almazroei2026_SHAP_LIME" in ids
    assert "writeback_guards" in data
