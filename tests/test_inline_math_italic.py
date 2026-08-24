# -*- coding: utf-8 -*-
"""Inline math: math-italic gamma + broken TMA$1 \\cdot$."""
from __future__ import annotations

from app.utils.md_postprocess import convert_inline_unicode_math, postprocess_markdown


def test_math_italic_gamma_interaction_term():
    raw = (
        "where \U0001D6FE 3 \U0001D457\U0001D450 ( TMA$1 \\cdot$ IMD ) \U0001D460 "
        "is the random slope for the interaction effect in course offering "
        "\U0001D457 within course \U0001D450 ."
    )
    out = convert_inline_unicode_math(raw, mode="safe")
    assert r"\gamma_{3jc}" in out
    assert "TMA1" in out and r"\cdot" in out and "IMD" in out
    assert "_{s}" in out or "_s" in out
    assert "TMA$1" not in out
    assert "is the random slope" in out
    assert "$" in out


def test_gamma_line_via_postprocess():
    raw = (
        "where \U0001D6FE 3 \U0001D457\U0001D450 ( TMA$1 \\cdot$ IMD ) \U0001D460 "
        "is the random slope."
    )
    out = postprocess_markdown(raw, pdf_path=None, fix_bold=False, mode="safe")
    assert r"\gamma_{3jc}" in out
    assert r"(TMA1 \cdot IMD)_{s}" in out or r"(TMA1 \cdot IMD)_s" in out
