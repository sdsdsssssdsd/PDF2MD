# -*- coding: utf-8 -*-
"""Phase 5A：Canary 聚合 / EMA abort / 版本 metadata。"""
from __future__ import annotations

from app.formula.canary import (
    CanaryDocMetrics,
    aggregate_canary,
    evaluate_canary_gates,
    ingest_o018_artifacts,
    run_phase5a_canary_seed,
)
from app.formula.types import FormulaQAReport
from app.formula.versions import PIPELINE_VERSION, pipeline_versions
from app.ocr.cost_model import CostModelSnapshot, RecoveryCostModel


def test_qa_report_includes_versions():
    d = FormulaQAReport().to_dict()
    assert "versions" in d
    assert d["versions"]["pipeline_version"] == PIPELINE_VERSION
    assert "gate_version" in d["versions"]


def test_ema_skips_timeout_and_oom():
    m = RecoveryCostModel(
        snapshot=CostModelSnapshot(formula_seconds_ema=3.0, page_seconds_ema=40.0),
        auto_load=False,
        auto_save=False,
        alpha=1.0,
    )
    m.runtime.model_loaded = True
    before_f = m.snap.formula_samples
    before_p = m.snap.page_samples
    m.observe_formula(99.0, success=False, abort_reason="timeout")
    m.observe_page(736.0, success=False, abort_reason="oom")
    assert m.snap.formula_samples == before_f
    assert m.snap.page_samples == before_p
    assert abs(m.snap.formula_seconds_ema - 3.0) < 1e-9
    # 成功仍更新
    m.observe_formula(4.0, success=True)
    assert m.snap.formula_samples == before_f + 1


def test_aggregate_and_gates_seed():
    docs = [
        CanaryDocMetrics(
            doc_id="a",
            recovery_accepted=5,
            writeback_applied=5,
            model_load_count=1,
            total_recovery_seconds=20.0,
            false_accept=0,
            true_accept=5,
            false_reject=0,
            mode_counts={"formula_batch": 2},
        )
    ]
    summary = aggregate_canary(docs)
    assert summary["documents_total"] == 1
    assert summary["false_accept"] == 0
    assert summary["p50_recovery_seconds"] == 20.0
    gates = evaluate_canary_gates(summary)
    assert gates["status"] == "pass_seed"
    assert gates["ready_for_phase_5b_default_balanced"] is False


def test_run_phase5a_seed_uses_o018():
    payload = run_phase5a_canary_seed()
    assert payload["phase"] == "5A"
    assert payload["summary"]["document_count"] >= 1
    assert payload["summary"]["false_accept"] == 0
    assert payload["versions"]["scheduler_version"]
    d = ingest_o018_artifacts()
    assert d.model_load_count <= 1
    assert d.writeback_applied == 5
