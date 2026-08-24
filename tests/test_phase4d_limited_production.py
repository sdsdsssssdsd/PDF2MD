# -*- coding: utf-8 -*-
"""Phase 4D：有限生产写回策略与 O-018 集成。"""
from __future__ import annotations

import pytest

from app.formula.config import (
    FormulaConfig,
    formula_config_for_deepseek_limited_production,
    formula_config_for_preset,
)
from app.formula.phase4d_limited_production import (
    O018_IDS,
    build_corrupted_markdown_from_ids,
    run_o018_limited_production_from_shadow,
)
from app.formula.writeback import (
    FormulaWritebackManager,
    RecoveryWritebackItem,
    classify_gate_decision,
    register_display_formulas_by_order,
)


def _items(n: int, *, page: int = 6, reason: str = "gain_accept") -> list[RecoveryWritebackItem]:
    return [
        RecoveryWritebackItem(
            candidate_id=f"page{page}_eq{i}",
            recovered_latex=f"A_{i}=1",
            gate_accepted=True,
            would_replace=True,
            gate_reason=reason,
            scheduler_mode="formula_batch",
            page=page,
        )
        for i in range(1, n + 1)
    ]


def test_default_config_not_limited_production():
    cfg = FormulaConfig()
    assert cfg.deepseek_limited_production_enabled is False
    assert cfg.deepseek_recovery_writeback_enabled is False
    assert cfg.deepseek_recovery_writeback_dry_run is True


def test_limited_production_requires_balanced():
    with pytest.raises(ValueError):
        formula_config_for_deepseek_limited_production(recovery_preset="fast")


def test_classify_high_confidence():
    assert (
        classify_gate_decision(gate_accepted=True, gate_reason="gain_accept")
        == "ACCEPT_HIGH_CONFIDENCE"
    )
    assert (
        classify_gate_decision(gate_accepted=True, gate_reason="weak")
        == "ACCEPT_BORDERLINE"
    )


def test_budget_per_document():
    ids = [f"page6_eq{i}" for i in range(1, 6)]
    md = build_corrupted_markdown_from_ids(ids)
    reg = register_display_formulas_by_order(md, ids)
    cfg = formula_config_for_deepseek_limited_production(
        deepseek_max_writebacks_per_document=3,
        deepseek_max_writebacks_per_page=10,
    )
    items = _items(5, page=6)
    for it, cid in zip(items, ids, strict=True):
        it.candidate_id = cid
    report = FormulaWritebackManager(cfg).apply(md, items, reg)
    assert report.applied_count == 3
    assert sum(1 for e in report.entries if e.skip_reason == "writeback_budget_exceeded") == 2


def test_budget_per_page():
    ids = [f"page6_eq{i}" for i in range(1, 5)]
    md = build_corrupted_markdown_from_ids(ids)
    reg = register_display_formulas_by_order(md, ids)
    cfg = formula_config_for_deepseek_limited_production(
        deepseek_max_writebacks_per_document=10,
        deepseek_max_writebacks_per_page=2,
    )
    items = _items(4, page=6)
    for it, cid in zip(items, ids, strict=True):
        it.candidate_id = cid
    report = FormulaWritebackManager(cfg).apply(md, items, reg)
    assert report.applied_count == 2
    assert sum(1 for e in report.entries if e.skip_reason == "writeback_budget_exceeded") == 2


def test_borderline_stays_shadow_only():
    ids = ["page6_eq1"]
    md = build_corrupted_markdown_from_ids(ids)
    reg = register_display_formulas_by_order(md, ids)
    cfg = formula_config_for_deepseek_limited_production()
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq1",
            recovered_latex="A=1",
            gate_accepted=True,
            would_replace=True,
            gate_reason="borderline_ok",
            scheduler_mode="formula",
            page=6,
        )
    ]
    report = FormulaWritebackManager(cfg).apply(md, items, reg)
    assert report.applied_count == 0
    assert report.entries[0].skip_reason == "not_high_confidence"
    assert report.markdown_after == md


def test_false_risk_blocks_all():
    ids = ["page6_eq1"]
    md = build_corrupted_markdown_from_ids(ids)
    reg = register_display_formulas_by_order(md, ids)
    cfg = formula_config_for_deepseek_limited_production()
    items = _items(1)
    items[0].candidate_id = "page6_eq1"
    report = FormulaWritebackManager(cfg).apply(md, items, reg, false_risk_signals=1)
    assert report.applied_count == 0
    assert report.entries[0].skip_reason == "document_false_risk"


def test_unresolved_marks_incomplete():
    ids = ["page6_eq1"]
    md = build_corrupted_markdown_from_ids(ids)
    reg = register_display_formulas_by_order(md, ids)
    cfg = formula_config_for_deepseek_limited_production()
    items = _items(1)
    items[0].candidate_id = "page6_eq1"
    report = FormulaWritebackManager(cfg).apply(
        md, items, reg, unresolved_formula_count=2
    )
    assert report.document_status == "formula_incomplete"
    assert report.applied_count == 1  # 仍可写已 accept 的；状态 incomplete


def test_writeback_disabled_degrades():
    ids = ["page6_eq1"]
    md = build_corrupted_markdown_from_ids(ids)
    reg = register_display_formulas_by_order(md, ids)
    cfg = formula_config_for_preset(
        "balanced",
        deepseek_recovery_writeback_enabled=False,
        deepseek_recovery_writeback_dry_run=False,
    )
    items = _items(1)
    items[0].candidate_id = "page6_eq1"
    report = FormulaWritebackManager(cfg).apply(md, items, reg)
    assert report.markdown_after == md
    assert report.entries[0].skip_reason == "writeback_disabled"


def test_o018_limited_production_from_shadow_json():
    payload = run_o018_limited_production_from_shadow()
    assert payload["acceptance"]["passed"] is True
    assert payload["writeback"]["applied_count"] == 5
    assert len(O018_IDS) == 5
