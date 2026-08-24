# -*- coding: utf-8 -*-
"""Phase 7.2B0 / B0.1 prioritization + counterfactual + number plausibility 单测。"""
from __future__ import annotations

from app.diagnostics.document_profile import build_document_recovery_profile
from app.formula.canary_o018 import O018RegressionError, check_o018_regression_gate
from app.formula.types import FormulaCandidate, FormulaQuality
from app.ocr.prioritization import (
    NUM_NON_EQ,
    build_counterfactual_budget,
    build_ranking_error_analysis,
    classify_equation_number_plausibility,
    prioritize_candidates,
)


def test_prioritize_moves_numbered_ahead_of_unnumbered():
    weak = FormulaCandidate(
        text="x",
        page=1,
        number_status="unnumbered_confirmed",
        quality=FormulaQuality(corruption_score=0.2),
    )
    strong = FormulaCandidate(
        text=r"\frac{a}{b}+\sum_{i=1}^{n} x_i",
        page=2,
        equation_number="3",
        number_status="numbered_confirmed",
        context_before="see Eq.(3)",
        quality=FormulaQuality(corruption_score=0.9),
        bbox=(0, 0, 100, 40),
    )
    ordered, meta = prioritize_candidates([weak, strong], enabled=True)
    assert "plausibility" in meta["mode"]
    assert ordered[0] is strong
    assert ordered[1] is weak


def test_year_2019_is_non_equation_and_demoted():
    year = FormulaCandidate(
        text="<!-- formula-not-decoded -->",
        page=9,
        context_before="published in 2019",
        quality=FormulaQuality(corruption_score=0.9),
        bbox=(0, 0, 80, 20),
    )
    # 模拟 eq_number_from_candidate 抽到 2019：写入 equation_number
    year.equation_number = "2019"
    real = FormulaCandidate(
        text=r"E=mc^2",
        page=9,
        equation_number="12",
        number_status="numbered_confirmed",
        context_before="Eq.(12)",
        quality=FormulaQuality(corruption_score=0.9),
        bbox=(400, 0, 500, 30),
    )
    plaus = classify_equation_number_plausibility(year)
    assert plaus["class"] == NUM_NON_EQ
    assert plaus["score"] <= 0.1
    ordered, meta = prioritize_candidates([year, real], enabled=True)
    assert ordered[0] is real
    assert ordered[1] is year
    # top score 不应把 2019 标成 confirmed
    top_year = [s for s in meta["scores"] if s.get("number_token") == "2019"]
    assert top_year and top_year[0]["equation_number_plausibility"] == NUM_NON_EQ


def test_prioritize_disabled_uses_reading_order():
    a = FormulaCandidate(text="a", page=2, equation_number="1")
    b = FormulaCandidate(text="b", page=1, equation_number="2")
    ordered, meta = prioritize_candidates([a, b], enabled=False)
    assert meta["mode"] == "reading_order"
    assert ordered[0].page == 1


def test_counterfactual_budget_o003_shaped():
    rows = [{"gate_accepted": False, "timing": {"ocr_seconds": 5.0}} for _ in range(8)]
    rows.append({"gate_accepted": True, "timing": {"ocr_seconds": 5.0}})
    rows.append({"gate_accepted": True, "timing": {"ocr_seconds": 5.0}})
    rows.append({"gate_accepted": False, "timing": {"ocr_seconds": 5.0}})
    rows.append({"gate_accepted": True, "timing": {"ocr_seconds": 5.0}})
    cf = build_counterfactual_budget(rows, budgets=(4, 6, 8, 10))
    assert cf["total_accepted"] == 3
    assert cf["budgets"]["8"]["accepted"] == 0
    assert cf["recall_at_k"]["8"] == 0.0
    assert cf["budgets"]["8"]["accepted"] < cf["total_accepted"]


def test_ranking_error_analysis_joins_scores_and_outcomes():
    weak = FormulaCandidate(text="a", page=1, number_status="unnumbered_confirmed")
    strong = FormulaCandidate(
        text=r"\sum x",
        page=1,
        equation_number="2",
        number_status="numbered_confirmed",
        context_before="Eq.(2)",
    )
    ordered, meta = prioritize_candidates([weak, strong], enabled=True)
    rows = [
        {"gate_accepted": True, "eq_number": "2", "failure_class": "accepted"},
        {
            "gate_accepted": False,
            "eq_number": "",
            "failure_class": "extraction_failure",
        },
    ]
    # 对齐实际 order
    rows_ordered = []
    for c in ordered:
        if c is strong:
            rows_ordered.append(rows[0])
        else:
            rows_ordered.append(rows[1])
    analysis = build_ranking_error_analysis(meta, rows_ordered)
    assert analysis["n_joined"] == 2
    assert analysis["accepted_attempt_indices"] == [1]
    assert "recall_at_k" in analysis


def test_profile_includes_counterfactual():
    rows = [
        {"gate_accepted": True, "timing": {"ocr_seconds": 4.0}},
        {
            "gate_accepted": False,
            "failure_class": "extraction_failure",
            "timing": {"ocr_seconds": 4.0},
        },
        {"gate_accepted": True, "timing": {"ocr_seconds": 4.0}},
    ]
    prof = build_document_recovery_profile(
        rows, document_id="t", ocr_calls=3, accepted=2
    )
    assert "counterfactual_budget" in prof
    assert "recall_at_k" in prof["counterfactual_budget"]


def test_o018_canary():
    ok = check_o018_regression_gate(
        {
            "document": "O-018_Abdo2025_Stacking_SHAP",
            "accepted": 7,
            "rejected": 0,
        }
    )
    assert ok["pass"] is True
    bad = check_o018_regression_gate(
        {
            "document": "O-018_Abdo2025_Stacking_SHAP",
            "accepted": 6,
            "rejected": 1,
        },
        raise_on_fail=False,
    )
    assert bad["pass"] is False
    try:
        check_o018_regression_gate(
            {"document": "O-018_x", "accepted": 6, "rejected": 1},
            raise_on_fail=True,
        )
        assert False, "expected raise"
    except O018RegressionError:
        pass
