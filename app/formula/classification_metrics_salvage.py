# -*- coding: utf-8 -*-
"""分类指标（F1/Prec/Rec/TP）display 公式：从 Docling amp 表碎片折叠（不发明内容）。"""
from __future__ import annotations

import re

from app.formula.config import FormulaConfig
from app.formula.corruption import _AMP_LEADING_EQ, assess_corruption, strip_spacing
from app.formula.validator import validate_latex

_FRAC = re.compile(r"\\frac\s*\{[^}]+\}\s*\{[^}]+\}", re.I)


def _has_main_f1_structure(raw: str) -> bool:
    m = re.search(r"F\s*1\s*&\s*=.*?\\frac", raw, re.I | re.S)
    if not m:
        return False
    head = raw[m.start() : m.start() + 180]
    return (
        "2" in head
        and re.search(r"\\Pr\s+e\s+c", head, re.I) is not None
        and "+" in head
    )


def _collapse_metric_fracs(raw: str) -> tuple[str | None, str | None]:
    fracs = [strip_spacing(m.group(0)) for m in _FRAC.finditer(raw)]
    if len(fracs) < 2:
        return None, None
    prec_frac = rec_frac = None
    for f in fracs:
        compact = f.replace(" ", "")
        if "+FP" in compact or "TP+FP" in compact:
            prec_frac = f
        elif "+FN" in compact or "TP+FN" in compact:
            rec_frac = f
    if prec_frac and rec_frac:
        return prec_frac, rec_frac
    if len(fracs) == 2:
        return fracs[0], fracs[1]
    return None, None


def salvage_classification_metrics_latex(
    original: str,
    *,
    cfg: FormulaConfig | None = None,
    context_before: str = "",
) -> str | None:
    """O-024 类 F1 三线式：原文含 TP 分式 + amp 碎片时折叠为空格并重组。"""
    raw = (original or "").strip()
    if not raw or not _AMP_LEADING_EQ.search(raw):
        return None
    ctx = (context_before or "").lower()
    if not re.search(r"\bf1\b|f1@0|precision and recall|fixed-threshold", ctx):
        return None

    fcfg = cfg or FormulaConfig()
    before_q = assess_corruption(raw, fcfg)
    if before_q.corruption_score < 0.75:
        return None
    if not _has_main_f1_structure(raw):
        return None

    prec_frac, rec_frac = _collapse_metric_fracs(raw)
    if not prec_frac or not rec_frac:
        return None

    collapsed = (
        r"F1 = \frac{2 \cdot \mathrm{Prec} \cdot \mathrm{Rec}}"
        r"{\mathrm{Prec} + \mathrm{Rec}}, "
        f"\\quad \\mathrm{{Prec}} = {prec_frac}, "
        f"\\quad \\mathrm{{Rec}} = {rec_frac}."
    )

    vr = validate_latex(collapsed, fcfg, context_before=context_before or "")
    if not vr.valid or vr.quality is None:
        return None
    if float(vr.quality.corruption_score) > 0.35:
        return None
    if float(vr.quality.corruption_score) >= float(before_q.corruption_score) - 0.1:
        return None
    return collapsed
