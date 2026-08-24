"""Display-math scrap cleanup (Docling layout leftovers)."""
from __future__ import annotations

from app.utils.md_postprocess import repair_display_formula_scraps


def test_drops_text_red_al_and_fixes_logit_tma():
    raw = (
        r"$$\begin{array} { l l } \text {red} & \log i ( P _ { s j c } ) = "
        r"\beta _ { 0 } + \beta _ { 1 } T M A 1 _ { s } + \beta _ { 2 } I M D _ { s } "
        r"\\ \text {al} & + \sum _ { k = 4 } ^ { 9 } \beta _ { k } X _ { k s } "
        r"+ \gamma _ { 0 j c } + \zeta _ { 0 c } & ( 1 ) \\ \end{array}$$"
    )
    out = repair_display_formula_scraps(raw)
    assert "red" not in out.lower() or r"\text" not in out
    assert r"\text {al}" not in out and r"\text{al}" not in out
    assert r"\operatorname{logit}" in out
    assert "TMA1" in out
    assert "IMD" in out
    assert "(1)" in out
    assert r"\begin{array}" not in out


def test_drops_bottom_and_orphan_eq():
    raw = (
        r"$$\log i t ( P _ { s j c } ) & = \beta _ { 0 } + \beta _ { 1 } T M A 1 _ { s } "
        r"& \quad \text {bottom} \\ & + \gamma _ { 3 j c } & \quad ( 2 ) \\$$"
        "\n\n$$= 4$$\n\n"
    )
    out = repair_display_formula_scraps(raw)
    assert "bottom" not in out
    assert r"\operatorname{logit}" in out
    assert "TMA1" in out
    assert "$$= 4$$" not in out
    assert "= 4" not in out.replace("=", "") or "$$= 4$$" not in out


def test_keeps_legitimate_text():
    raw = r"$$\mathrm{Male} + \text{Female}$$"
    out = repair_display_formula_scraps(raw)
    assert r"\text{Female}" in out or r"\text {Female}" in out.replace(" ", "")
