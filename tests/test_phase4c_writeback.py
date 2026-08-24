# -*- coding: utf-8 -*-
"""Phase 4C：Controlled Writeback 单测。"""
from __future__ import annotations

import json
from pathlib import Path

from app.formula.config import FormulaConfig
from app.formula.writeback import (
    FormulaBlockRegistry,
    FormulaBlockRef,
    FormulaWritebackManager,
    RecoveryWritebackItem,
    content_hash,
    register_display_formulas_by_order,
)


def _md_two() -> str:
    return (
        "# T\n\n"
        "Before\n\n"
        "$$\\quad\\quad garbage A$$\n\n"
        "Mid\n\n"
        "$$\\quad\\quad garbage B$$\n\n"
        "After\n"
    )


def _registry(md: str) -> FormulaBlockRegistry:
    return register_display_formulas_by_order(md, ["page6_eq4", "page6_eq5"])


def test_writeback_disabled_leaves_markdown_unchanged():
    md = _md_two()
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=False,
        deepseek_recovery_writeback_dry_run=False,
    )
    wb = FormulaWritebackManager(cfg)
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq4",
            recovered_latex=r"Recall=\frac{TP}{TP+FN}",
            gate_accepted=True,
            would_replace=True,
        )
    ]
    report = wb.apply(md, items, _registry(md))
    assert report.markdown_after == md
    assert report.applied_count == 0
    assert all(e.skip_reason == "writeback_disabled" for e in report.entries)


def test_dry_run_plans_but_does_not_mutate():
    md = _md_two()
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=True,
    )
    wb = FormulaWritebackManager(cfg)
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq4",
            recovered_latex=r"Recall=\frac{TP}{TP+FN}",
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
        )
    ]
    report = wb.apply(md, items, _registry(md))
    assert report.markdown_after == md
    assert report.applied_count == 0
    assert report.entries[0].replacement.startswith("$$")
    assert report.entries[0].skip_reason == ""
    assert report.entries[0].dry_run is True


def test_apply_exact_span_only_changes_target():
    md = _md_two()
    mid = "Mid"
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=False,
    )
    wb = FormulaWritebackManager(cfg)
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq4",
            recovered_latex=r"Recall=\frac{TP}{TP+FN}",
            gate_accepted=True,
            would_replace=True,
        )
    ]
    report = wb.apply(md, items, _registry(md))
    assert report.applied_count == 1
    assert report.entries[0].writeback_applied is True
    assert "Recall" in report.markdown_after
    assert "garbage A" not in report.markdown_after
    assert "garbage B" in report.markdown_after  # 未目标不变
    assert mid in report.markdown_after
    assert report.markdown_before.count("Before") == report.markdown_after.count("Before")


def test_reject_not_accepted():
    md = _md_two()
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=False,
    )
    wb = FormulaWritebackManager(cfg)
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq4",
            recovered_latex=r"Recall=\frac{TP}{TP+FN}",
            gate_accepted=False,
            would_replace=False,
        )
    ]
    report = wb.apply(md, items, _registry(md))
    assert report.markdown_after == md
    assert report.entries[0].skip_reason == "not_accepted_or_would_replace_false"


def test_stale_candidate_hash():
    md = _md_two()
    reg = _registry(md)
    # 污染原文
    md2 = md.replace("garbage A", "CHANGED", 1)
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=False,
    )
    wb = FormulaWritebackManager(cfg)
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq4",
            recovered_latex=r"Recall=\frac{TP}{TP+FN}",
            gate_accepted=True,
            would_replace=True,
        )
    ]
    report = wb.apply(md2, items, reg)
    assert report.applied_count == 0
    assert report.entries[0].skip_reason in {
        "stale_content_mismatch",
        "stale_content_hash",
    }


def test_duplicate_candidate_id_fail_closed():
    md = _md_two()
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=False,
    )
    wb = FormulaWritebackManager(cfg)
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq4",
            recovered_latex="A=1",
            gate_accepted=True,
            would_replace=True,
        ),
        RecoveryWritebackItem(
            candidate_id="page6_eq4",
            recovered_latex="A=2",
            gate_accepted=True,
            would_replace=True,
        ),
    ]
    report = wb.apply(md, items, _registry(md))
    assert report.markdown_after == md
    assert report.applied_count == 0
    assert "duplicate_candidate_id" in report.error
    assert all(e.skip_reason == "duplicate_candidate_id" for e in report.entries)


def test_missing_candidate_id_fail_closed():
    md = _md_two()
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=False,
    )
    wb = FormulaWritebackManager(cfg)
    items = [
        RecoveryWritebackItem(
            candidate_id="no_such_id",
            recovered_latex="A=1",
            gate_accepted=True,
            would_replace=True,
        )
    ]
    report = wb.apply(md, items, _registry(md))
    assert report.markdown_after == md
    assert report.entries[0].skip_reason == "candidate_id_not_found"


def test_rollback_on_release_gate_failure():
    md = _md_two()
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=False,
    )
    wb = FormulaWritebackManager(cfg)
    # 故意写回未闭合 $
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq4",
            recovered_latex="broken $ formula",
            gate_accepted=True,
            would_replace=True,
        )
    ]
    report = wb.apply(md, items, _registry(md))
    # build_display_block wraps with $$ ... $$ so "broken $ formula" → $$broken $ formula$$
    # dollar count may be odd → either skip at replacement check or rollback
    assert report.markdown_after == md
    assert report.applied_count == 0
    assert report.rolled_back_count >= 1 or report.entries[0].skip_reason == (
        "replacement_unbalanced_dollar"
    )


def test_skip_mode_never_writes():
    md = _md_two()
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=False,
    )
    wb = FormulaWritebackManager(cfg)
    items = [
        RecoveryWritebackItem(
            candidate_id="page6_eq4",
            recovered_latex=r"Recall=\frac{TP}{TP+FN}",
            gate_accepted=True,
            would_replace=True,
            scheduler_mode="skip",
        )
    ]
    report = wb.apply(md, items, _registry(md))
    assert report.markdown_after == md
    assert report.entries[0].skip_reason == "scheduler_skip"


def test_registry_rejects_duplicate_register():
    reg = FormulaBlockRegistry()
    b = FormulaBlockRef(
        candidate_id="a",
        start=0,
        end=4,
        original_inner="x",
        original_full="$$x$$",
        content_hash=content_hash("$$x$$"),
    )
    reg.register(b)
    try:
        reg.register(b)
        assert False, "expected duplicate error"
    except ValueError as e:
        assert "duplicate_candidate_id" in str(e)


def test_o018_five_formulas_writeback_from_shadow_fixture():
    """O-018：5 个 accepted recovery 均可按 candidate_id 写回（无 GPU）。"""
    recovered = {
        "page6_eq1": r"E\left[\left(y-\hat{f}\right)^{2}\right]=Bias^{2}+V+\varepsilon",
        "page6_eq4": r"Recall=\frac{TP}{TP+FN}",
        "page6_eq5": r"F1=2\times\frac{Precision\times Recall}{Precision+Recall}",
        "page7_eq6": r"\mathrm{TPR}=\frac{\mathrm{TP}}{\mathrm{TP}+\mathrm{FN}}",
        "page7_eq7": r"\mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}",
    }
    parts = ["# O-018 shadow writeback fixture\n"]
    ids = []
    for cid, _ in recovered.items():
        ids.append(cid)
        parts.append(f"\nContext for {cid}\n\n$$\\quad\\quad\\quad garbage$$\n")
    md = "".join(parts)
    reg = register_display_formulas_by_order(md, ids)

    items = [
        RecoveryWritebackItem(
            candidate_id=cid,
            recovered_latex=latex,
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            scheduler_mode="formula_batch",
        )
        for cid, latex in recovered.items()
    ]
    cfg = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=False,
    )
    report = FormulaWritebackManager(cfg).apply(md, items, reg)
    assert report.applied_count == 5
    assert report.rolled_back_count == 0
    assert "garbage" not in report.markdown_after
    assert "Recall" in report.markdown_after
    assert "TPR" in report.markdown_after
    assert report.release_gate.get("publishable") is True

    # dry-run 路径
    cfg2 = FormulaConfig(
        deepseek_recovery_writeback_enabled=True,
        deepseek_recovery_writeback_dry_run=True,
    )
    dry = FormulaWritebackManager(cfg2).apply(md, items, reg)
    assert dry.markdown_after == md
    assert dry.applied_count == 0
    assert sum(1 for e in dry.entries if e.replacement and not e.skip_reason) == 5


def test_load_real_shadow_json_if_present():
    """若 4B.1 产物存在，校验 would_replace 条目可映射到 WritebackItem。"""
    path = Path("debug/formula_benchmark/runs/phase4b1_o018_shadow.json")
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("would_replace_review") or []
    assert len(rows) >= 5
    assert all(r.get("would_replace") for r in rows)
    assert all(r.get("gate_accepted") for r in rows)
