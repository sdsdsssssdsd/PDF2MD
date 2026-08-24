# -*- coding: utf-8 -*-
"""Phase 3B：MatchEvaluator + 离线 Gate confusion。"""
from __future__ import annotations

from app.ocr.match_eval import FormulaMatchEvaluator, normalize_latex
from app.ocr.offline_scoring import (
    default_negative_gate_cases,
    default_positive_gate_cases,
    offline_fixture_scoring,
    replay_gate_cases,
    run_phase3b_offline,
)


def test_normalize_aliases_var_v():
    a = normalize_latex(r"Bias^{2}+Var+\varepsilon")
    b = normalize_latex(r"Bias^{2}+V+\varepsilon")
    assert a == b


def test_eq1_human_usable_despite_var_alias():
    m = FormulaMatchEvaluator().compare(
        r"E\left[\left(y-\hat{f}\right)^{2}\right]=Bias^{2}+V+\varepsilon",
        r"E[(y-\hat{f})^2]=Bias^2+Var+\varepsilon",
    )
    assert m.exact_normalized_match or m.human_usable
    assert m.structural_match or m.human_usable


def test_eq4_exact_usable():
    m = FormulaMatchEvaluator().compare(
        r"Recall=\frac{TP}{TP+FN}",
        r"Recall=\frac{TP}{TP+FN}",
    )
    assert m.exact_normalized_match
    assert m.human_usable


def test_negative_not_usable_as_recall():
    m = FormulaMatchEvaluator().compare(
        r"\frac{\omega_{nd}^n}{\omega}",
        r"Recall=\frac{TP}{TP+FN}",
    )
    assert not m.human_usable
    assert not m.exact_normalized_match


def test_layer_extractor_vs_ocr_failure():
    ev = FormulaMatchEvaluator()
    # raw 含正确式，selected 抽错 → extractor_failure
    raw = r"text \[ Recall=\frac{TP}{TP+FN} \quad (4) \] more"
    layer = ev.layer_report(
        raw_ocr=raw,
        selected="The F1-score is the harmonic average",
        gold=r"Recall=\frac{TP}{TP+FN}",
    )
    assert layer.raw_contains_usable
    assert layer.layer == "extractor_failure"
    assert layer.extractor_gap

    layer2 = ev.layer_report(
        raw_ocr=r"only garbage \omega_{nd}",
        selected=r"\frac{\omega_{nd}^n}{\omega}",
        gold=r"Recall=\frac{TP}{TP+FN}",
    )
    assert layer2.layer == "ocr_failure"


def test_mse_family_not_false_reject():
    from app.formula.tokens import token_consistency

    ratio, reasons = token_consistency(
        "The expected mean squared error (MSE) can be expressed by Eq. (1):",
        r"E[(y-\hat{f})^2]=Bias^2+V+\varepsilon",
    )
    assert "ocr_context_conflict" not in reasons
    assert ratio > 0


def test_gate_confusion_false_accept_near_zero():
    cm = replay_gate_cases()
    assert cm.false_accept == 0, cm.to_dict()
    # 正例应大多 accept；若有 false_reject 记下来但不在此硬失败（校准点）
    assert cm.true_accept >= 3
    assert cm.true_reject >= 3


def test_offline_fixture_scoring_runs():
    payload = offline_fixture_scoring()
    assert payload["by_mode"]
    assert payload["rows"]
    # formula 模式 human_usable 应明显高于旧 strict gold
    formula = payload["by_mode"].get("formula") or {}
    assert formula.get("n", 0) >= 4


def test_run_phase3b_writes(tmp_path):
    out = tmp_path / "p3b.json"
    payload = run_phase3b_offline(out_path=out)
    assert out.exists()
    assert payload["gate_confusion"]["false_accept"] == 0
