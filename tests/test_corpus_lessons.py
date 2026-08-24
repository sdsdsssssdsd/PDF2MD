# -*- coding: utf-8 -*-
from __future__ import annotations

from app.utils.md_postprocess import (
    _repair_table_line_math,
    postprocess_markdown,
    repair_display_formula_scraps,
    repair_prose_artifacts,
)


def test_table_folds_math_italic_average():
    line = (
        "| 1 | average_score | desc | all \U0001D434\U0001D463\U0001D452\U0001D45F\U0001D44E\U0001D454\U0001D452 "
        "\U0001D446\U0001D450\U0001D45C\U0001D45F\U0001D452 = ∑Assessment | note |"
    )
    out = _repair_table_line_math(line)
    assert "Average" in out or "average" in out.lower()
    assert "\U0001D434" not in out
    assert r"$\sum$" in out


def test_thousands_comma_unmath():
    raw = "better fit (AIC: 29,$390 \\to 29$,370) than P1"
    out = repair_prose_artifacts(raw)
    assert "29,390" in out
    assert "29,370" in out
    assert "$390" not in out


def test_unescape_underscore():
    assert "student_assessments" in repair_prose_artifacts(r"student\_assessments table")


def test_broken_f1_display():
    raw = (
        r"$$F1 = \frac { 2 \mathrm{Prec} { \mathrm{Rec} } } "
        r"{ \mathrm{Prec} { + \mathrm{Rec} } } , "
        r"\quad \mathrm{Prec} { = \frac { TP } { TP + FP } } , "
        r"\quad \mathrm{Rec} = \frac { TP } { TP + FN } .$$"
    )
    out = repair_display_formula_scraps(raw)
    assert r"2 \cdot \mathrm{Prec} \cdot \mathrm{Rec}" in out
    assert r"\mathrm{Prec} { \mathrm{Rec}" not in out
