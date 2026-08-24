# -*- coding: utf-8 -*-
"""Phase 3C 单元：comparison / 页选择逻辑（不需 GPU）。"""
from __future__ import annotations

from app.ocr.phase3c_two_page import (
    PHASE3C_MULTI_EQS,
    PHASE3C_SINGLE_EQ,
    build_comparison,
)


def test_page_selection_targets():
    assert PHASE3C_SINGLE_EQ == "1"
    assert PHASE3C_MULTI_EQS == ("6", "7")


def test_comparison_prefers_formula_when_page_slower():
    multi = {
        "formula_mode": {
            "n": 2,
            "total_seconds": 80.0,
            "human_usable": 2,
            "gate_accepted": 2,
            "ocr_calls": 2,
        },
        "page_mode": {
            "n": 2,
            "total_seconds": 215.0,
            "human_usable": 2,
            "gate_accepted": 2,
            "ocr_calls": 1,
            "page_ocr_once": True,
        },
    }
    c = build_comparison(multi, safety_factor=1.2)
    assert c["recommended_mode"] == "FORMULA_BATCH"
    assert c["cost_page_better_with_safety"] is False


def test_comparison_prefers_page_when_cheaper_and_quality_ok():
    multi = {
        "formula_mode": {
            "n": 8,
            "total_seconds": 320.0,
            "human_usable": 7,
            "gate_accepted": 7,
            "ocr_calls": 8,
        },
        "page_mode": {
            "n": 8,
            "total_seconds": 200.0,
            "human_usable": 6,  # 允许少 1
            "gate_accepted": 6,
            "ocr_calls": 1,
            "page_ocr_once": True,
        },
    }
    c = build_comparison(multi, safety_factor=1.2)
    # 200*1.2=240 < 320 → PAGE
    assert c["recommended_mode"] == "PAGE"
    assert c["quality_loss_ok"] is True


def test_comparison_rejects_page_on_quality_loss():
    multi = {
        "formula_mode": {
            "n": 4,
            "total_seconds": 400.0,
            "human_usable": 4,
            "gate_accepted": 4,
            "ocr_calls": 4,
        },
        "page_mode": {
            "n": 4,
            "total_seconds": 100.0,
            "human_usable": 2,  # 少 2 → 不允许
            "gate_accepted": 2,
            "ocr_calls": 1,
            "page_ocr_once": True,
        },
    }
    c = build_comparison(multi, safety_factor=1.2)
    assert c["recommended_mode"] == "FORMULA_BATCH"
    assert c["quality_loss_ok"] is False
