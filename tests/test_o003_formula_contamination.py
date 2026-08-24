# -*- coding: utf-8 -*-
"""O-003 style heavily contaminated display formulas must not ship as fake math."""
from __future__ import annotations

import os

from pathlib import Path

import pytest

from app.utils.md_postprocess import (
    postprocess_markdown,
    repair_display_formula_scraps,
    repair_prose_artifacts,
)
from app.utils.paths import APP_ROOT


def test_strip_intertext_garbage():
    raw = r"$$p _ { t + 1 } = p _ { t } \, Q , \\ \intertext { s e f t i m e } \intertext { s e f t i m e }$$"
    out = repair_display_formula_scraps(raw)
    assert r"\intertext" not in out
    assert "seftime" not in out.replace(" ", "")
    assert "p_{t+1}" in out.replace(" ", "") or "p _ { t + 1 }" in out or "Q" in out


def test_when_p_becomes_vector_ode():
    raw = r"$$w h e n \, p \quad \mathfrak { p } ( t ) = \mathfrak { p } (0) \, e ^ { - t l } .$$"
    out = repair_display_formula_scraps(raw)
    assert "when" not in out.lower() or "w h e n" not in out
    assert "e^{-tL}" in out.replace(" ", "")
    assert r"\mathbf{p}" in out or "mathbf{p}" in out.replace("\\", "")


def test_membership_drops_bogus_frac():
    raw = (
        r"$$\frac { i - y \| ^ { 2 } } { ( n , m ) } , \quad "
        r"H _ { i c } = \begin{cases} 1 \text {if node $i$ belongs to community $c$} \\ "
        r"0 \text {otherwise} \end{cases} \\ \text {equative}$$"
    )
    out = repair_display_formula_scraps(raw)
    assert "i - y" not in out
    assert "equative" not in out
    assert "H_{ic}" in out.replace(" ", "") or "H _ { i c }" in out


def test_e_tt_to_tL_and_min_tau():
    raw = (
        r"$$R ( t ; H ) = H ^ { T } ( \Pi e ^ { - t t } - \pi ^ { T } \pi ) H ,$$"
        "\n\n"
        r"$$\text {weighted} \quad r ( t , H ) = \min _ { t \prec t } \text {Tr} \left [ R ( \tau , H ) \right ] ,$$"
    )
    out = repair_display_formula_scraps(raw)
    assert "e^{-tL}" in out.replace(" ", "")
    assert "weighted" not in out
    assert r"\tau" in out or "tau" in out


def test_due_stackrel_rejected_or_fixed():
    raw = (
        r"$$\begin{aligned}\text {due} & \stackrel { \circ } { a } & "
        r"r ^ { * } ( t ) = \max _ { H } ( t , H ) \, \text {and} \, "
        r"H ^ { * } ( t ) = \arg \max _ { H } r ( t , H ) . \\ \text {this, we}\end{aligned}$$"
    )
    out = repair_display_formula_scraps(raw)
    assert "due" not in out.lower() or "formula-not-decoded" in out
    assert r"\stackrel" not in out or "formula-not-decoded" in out
    if "formula-not-decoded" not in out:
        assert "r(t, H)" in out.replace(" ", "") or "r ( t , H )" in out


def test_nu_code_garbage_cleaned():
    raw = (
        r"$$\nu ( t , t ^ { \prime } ) = \, \nu ( \widehat { H } ( t ) , "
        r"\widehat { H } ( t ^ { \prime } ) ) . ( 1 0 ) \quad \code { CODE } \\ "
        r"\, \nu ( t , t ^ { \prime } ) = \, \nu ( \widehat { H } ( t ) , "
        r"\widehat { H } ( t ^ { \prime } ) ) . \, \ln \, \text {accorages} \\ "
        r"\, \nu ( t ) = \, \nu ( t ) . \, \text {to the} \, \ n$$"
    )
    out = repair_display_formula_scraps(raw)
    assert "CODE" not in out
    assert "accorages" not in out
    assert "formula-not-decoded" in out or out.count(r"\nu") <= 2


def test_fi_ligature_and_page_number():
    raw = "to de fi ne a time.\n\n9\n\nNext paragraph."
    out = repair_prose_artifacts(raw)
    assert "define" in out
    assert "\n9\n" not in out


def test_o003_block_batch_no_intertext():
    md_path = Path(
        os.environ.get(
            "PDF2MD_BENCH_O003_MD",
            str(APP_ROOT / "input" / "O-003_Peach2019_DataDrivenClustering.md"),
        )
    )
    if not md_path.is_file():
        md_path = APP_ROOT / "input" / "O-003_Peach2019_DataDrivenClustering.md"
    if not md_path.is_file():
        pytest.skip(f"O-003 fixture markdown not found: {md_path}")
    raw = md_path.read_text(encoding="utf-8")
    # only process a slice if file huge — full file is fine
    out = postprocess_markdown(raw, pdf_path=None, fix_bold=False, mode="safe")
    assert r"\intertext" not in out
    assert r"\code { CODE }" not in out and r"\code{CODE}" not in out
    assert "w h e n" not in out
    assert "equative" not in out
    assert "accorages" not in out
