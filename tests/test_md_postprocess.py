"""Pure-Python tests for Markdown post-process (no models / no PDF engines)."""
from __future__ import annotations

from app.utils.md_postprocess import (
    _repair_table_line_math,
    convert_inline_unicode_math,
    postprocess_markdown,
)


def test_decimal_glue_via_pipeline_style():
    import re

    text = "threshold 0 . 5 and 0 . 8602"
    text2, n = re.subn(r"(\d+)\s+\.\s+(\d+)", r"\1.\2", text)
    assert n == 2
    assert "0.5" in text2
    assert "0.8602" in text2


def test_hat_p_i_not_hat_pi():
    raw = "predicted by ˆ p i and ˆ y i"
    out = convert_inline_unicode_math(raw, mode="safe")
    assert r"\hat{p}_{i}" in out or r"\hat{p}" in out
    assert r"\hat_{pi}" not in out
    assert r"\hat_{yi}" not in out


def test_in_does_not_cross_brace_into_prose():
    # `} i ∈ I` must not swallow the set into one broken $...$
    raw = "dataset D ( t ) = { ( x , y ) } i ∈ I ( t ) , where I"
    out = convert_inline_unicode_math(raw, mode="safe")
    assert r")\} i" not in out
    assert "where I" in out


def test_table_line_does_not_break_pipes_with_dollars():
    line = "| GBDT | 0.8602 ± 0.0028 | 0.8224 ± 0.0034 |"
    fixed = _repair_table_line_math(line)
    assert "$|" not in fixed.replace("|$", "")  # no $ glued to open pipe oddly
    assert fixed.count("|") == line.count("|")
    assert r"$0.8602 \pm 0.0028$" in fixed
    assert "GBDT" in fixed


def test_postprocess_safe_preserves_english():
    text = "For each cutoff we construct a dataset."
    out = postprocess_markdown(text, pdf_path=None, fix_inline_math=True, fix_bold=False, mode="safe")
    assert "For each cutoff we construct a dataset." in out
