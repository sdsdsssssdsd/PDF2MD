# -*- coding: utf-8 -*-
"""公式 bbox：双栏按栏裁切，避免串到邻栏正文。"""
from __future__ import annotations

from pathlib import Path

from app.formula.session import (
    EquationAnchor,
    EquationAnchorIndex,
    column_bounds,
    formula_band_from_number,
)
from app.formula.types import FormulaCandidate
from app.formula.recovery import FormulaRecoveryManager
from app.formula.config import FormulaConfig


def test_column_bounds_right_half():
    x0, x1 = column_bounds(600.0, 520.0, 540.0)
    assert x0 >= 280.0  # 不越过中线去左栏
    assert x1 > 530.0


def test_column_bounds_left_half():
    x0, x1 = column_bounds(600.0, 100.0, 120.0)
    assert x0 < 50.0
    assert x1 <= 320.0


def test_formula_band_keeps_column():
    box = formula_band_from_number(595.0, 842.0, (527.0, 512.0, 540.0, 524.0))
    x0, y0, x1, y1 = box
    assert x0 >= 280.0
    # v1 narrow band（fallback 仍保留）
    assert 28.0 <= (y1 - y0) <= 52.0
    assert y0 < 512.0 < y1
    assert y0 >= 490.0


def test_formula_band_v2_display_expands():
    from app.formula.geometry import formula_band_from_number_v2

    nb = (527.0, 512.0, 540.0, 524.0)
    box = formula_band_from_number_v2(595.0, 842.0, nb, level="display")
    assert (box[3] - box[1]) >= 54.0


def test_index_prefers_rightmost_duplicate():
    idx = EquationAnchorIndex()
    idx.add("7", EquationAnchor(page=7, bbox=(100, 10, 110, 20), x_ratio=0.2))
    idx.add("7", EquationAnchor(page=6, bbox=(480, 690, 492, 705), x_ratio=0.81))
    hit = idx.lookup("7")
    assert hit is not None
    assert hit.page == 6
    assert hit.x_ratio > 0.7


def test_equation_numbers_prefer_context_before():
    mgr = FormulaRecoveryManager(FormulaConfig(recognizer_primary="null"))
    cand = FormulaCandidate(
        text=r"\Gamma ( 7 )",
        raw_text=r"\Gamma ( 7 )",
        context_before="Recall can be calculated using Eq. (4):",
        context_after="F1 Eq. (5)",
    )
    nums = mgr._equation_numbers(cand)
    assert nums[0] == "4"


def test_equation_numbers_ignore_function_args():
    mgr = FormulaRecoveryManager(FormulaConfig(recognizer_primary="null"))
    cand = FormulaCandidate(
        text=r"p(t)=p(0)e^{-tL}",
        raw_text=r"p(t)=p(0)e^{-tL}",
        context_before="Laplacian time-dependent solution:",
        context_after="Markov time",
    )
    assert mgr._equation_numbers(cand) == []


def test_equation_numbers_display_tail_only_from_raw():
    mgr = FormulaRecoveryManager(FormulaConfig(recognizer_primary="null"))
    cand = FormulaCandidate(
        text=r"E=mc^2 \quad (10)",
        raw_text=r"E=mc^2 \quad (10)",
        context_before="",
        context_after="",
    )
    assert mgr._equation_numbers(cand) == ["10"]

    cand_spaced = FormulaCandidate(
        text=r"\nu ( t , t ^ { \prime } ) = ... & ( 1 0 ) &",
        raw_text=r"\nu ( t , t ^ { \prime } ) = ... & ( 1 0 ) &",
        context_before="",
        context_after="",
    )
    assert mgr._equation_numbers(cand_spaced) == ["10"]
