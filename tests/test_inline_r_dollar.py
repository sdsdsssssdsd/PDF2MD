# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.pipeline import _inline_r_accessor_false_positive


def test_r_accessor_in_code_context():
    ctx = "case1 <- dataset_demographics(module = 'DDD')\n"
    assert _inline_r_accessor_false_positive(" final_result ", ctx) is True
    assert _inline_r_accessor_false_positive("x", "plain text about variable ") is False


def test_r_accessor_rejects_latex_body():
    assert _inline_r_accessor_false_positive(r"\alpha", "require(foo)\n") is False


def test_code_fence_dollar_not_formula():
    from app.formula import FormulaPipeline
    from app.formula.config import formula_config_for_deepseek_limited_production
    from app.formula.pipeline import _inside_markdown_code_fence

    md = "```\n> x <- 1\n$ assessment_data # A tibble: 2 x 1\n```\n"
    assert _inside_markdown_code_fence(md, md.index("$")) is True
    r = FormulaPipeline(formula_config_for_deepseek_limited_production()).process_markdown(
        md, pdf_path=None
    )
    assert r.report.formula_count == 0


def test_o016_raw_has_no_formulas():
    from pathlib import Path

    from app.formula import FormulaPipeline
    from app.formula.config import formula_config_for_deepseek_limited_production

    raw = Path(
        "logs/experiment/O-016_Howard2025_ouladFormat/O-016_Howard2025_ouladFormat.raw.md"
    )
    if not raw.is_file():
        return
    text = raw.read_text(encoding="utf-8")
    r = FormulaPipeline(formula_config_for_deepseek_limited_production()).process_markdown(
        text, pdf_path=None
    )
    assert r.report.formula_count == 0
