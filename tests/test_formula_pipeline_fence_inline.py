# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.config import FormulaConfig
from app.formula.pipeline import FormulaPipeline, _can_enqueue_deepseek
from app.formula.types import DocumentContext, FormulaCandidate


def test_display_math_inside_code_fence_not_counted():
    md = """```r
x <- 1
$$ not a formula $$
```
"""
    pipe = FormulaPipeline(FormulaConfig(enabled=True, recovery_preset="fast"))
    res = pipe.process_markdown(md)
    assert res.report.formula_count == 0


def test_can_enqueue_deepseek_inline_when_wrap_dollars():
    cfg = FormulaConfig(
        deepseek_limited_production_enabled=True,
        recovery_preset="balanced",
        lean_docling_balanced=True,
    )
    doc = DocumentContext(pdf_path="paper.pdf", markdown="")
    cand = FormulaCandidate(
        text=r"\bad",
        display_mode="inline",
        lifecycle="detected",
    )
    assert _can_enqueue_deepseek(cand, cfg, doc, wrap_dollars=True) is True
    assert _can_enqueue_deepseek(cand, cfg, doc, wrap_dollars=False) is False


def test_can_enqueue_deepseek_display_blocks_inline_wrap():
    cfg = FormulaConfig(
        deepseek_limited_production_enabled=True,
        recovery_preset="balanced",
        lean_docling_balanced=True,
    )
    doc = DocumentContext(pdf_path="paper.pdf", markdown="")
    display = FormulaCandidate(text="x", display_mode="display", lifecycle="detected")
    inline = FormulaCandidate(text="x", display_mode="inline", lifecycle="detected")
    assert _can_enqueue_deepseek(display, cfg, doc, wrap_dollars=False) is True
    assert _can_enqueue_deepseek(inline, cfg, doc, wrap_dollars=False) is False
    assert _can_enqueue_deepseek(inline, cfg, doc, wrap_dollars=True) is True
