# -*- coding: utf-8 -*-
"""Docling 把散文 OCR 混进 display 公式时，从损坏原文剥离前缀（不发明内容）。"""
from __future__ import annotations

import re

from app.formula.config import FormulaConfig
from app.formula.corruption import assess_corruption, strip_spacing
from app.formula.validator import validate_latex

_LEADING_PROSE_BLOB = re.compile(
    r"^\\text\s*\{[^}]*(?:wein|out\s+comes|predicted\s+pro|probabin|between\s+out)[^}]*\}\s*"
    r"(?:\\,)?\s*(?:\[\s*\d+\s*\])?\s*\\colon\s*\\\\\s*",
    re.I,
)
_BRIER_LABEL = re.compile(r"^\\text\s*\{\s*Brier\s*\}\s*", re.I)


def salvage_prose_prefixed_latex(
    original: str,
    *,
    cfg: FormulaConfig | None = None,
    context_before: str = "",
) -> str | None:
    """剥离 leading \\text{散文…} 后折叠空格；失败返回 None。"""
    raw = (original or "").strip()
    if not raw or not _LEADING_PROSE_BLOB.search(raw):
        return None

    fcfg = cfg or FormulaConfig()
    before_q = assess_corruption(raw, fcfg)
    if before_q.corruption_score < 0.75:
        return None

    body = _LEADING_PROSE_BLOB.sub("", raw, count=1).strip()
    body = _BRIER_LABEL.sub(r"\\mathrm{Brier}\\,", body)
    collapsed = strip_spacing(body)
    if not collapsed or len(collapsed) < 8:
        return None

    vr = validate_latex(
        collapsed,
        fcfg,
        context_before=context_before or "",
    )
    if not vr.valid or vr.quality is None:
        return None
    if float(vr.quality.corruption_score) > 0.35:
        return None
    if float(vr.quality.corruption_score) >= float(before_q.corruption_score) - 0.1:
        return None
    return collapsed
