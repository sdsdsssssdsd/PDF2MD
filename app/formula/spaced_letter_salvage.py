# -*- coding: utf-8 -*-
"""Docling spaced-letter 公式：几何无解时从损坏原文折叠（不发明内容）。"""
from __future__ import annotations

import re

from app.formula.config import FormulaConfig
from app.formula.corruption import _SPACED_LETTERS, assess_corruption, strip_spacing
from app.formula.validator import validate_latex

_TAIL_EQ_NUM = re.compile(r"(?:\\quad\s*)*\(\s*\d+\s*\)\s*$")


def salvage_spaced_letter_latex(
    original: str,
    *,
    cfg: FormulaConfig | None = None,
) -> str | None:
    """将 `M e t r i c _ { c }` 类损坏折叠为可写回 LaTeX；失败返回 None。"""
    raw = (original or "").strip()
    if not raw or not _SPACED_LETTERS.search(raw):
        return None
    if "=" not in raw and "\\frac" not in raw:
        return None

    collapsed = strip_spacing(raw)
    collapsed = _TAIL_EQ_NUM.sub("", collapsed).strip().rstrip(",")
    if not collapsed or len(collapsed) < 6:
        return None

    fcfg = cfg or FormulaConfig()
    before_q = assess_corruption(raw, fcfg)
    if before_q.corruption_score < 0.75:
        return None

    vr = validate_latex(collapsed, fcfg)
    if not vr.valid or vr.quality is None:
        return None
    if float(vr.quality.corruption_score) > 0.35:
        return None
    if float(vr.quality.corruption_score) >= float(before_q.corruption_score) - 0.1:
        return None
    return collapsed
