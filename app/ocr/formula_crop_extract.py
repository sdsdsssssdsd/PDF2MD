# -*- coding: utf-8 -*-
"""Phase 6B：Formula crop 提取 — 整个 crop 即公式，不要求 document equation block。"""
from __future__ import annotations

import re
from typing import Any

from app.ocr.extractor import (
    EquationBlock,
    EquationExtractor,
    ExtractResult,
    _clean_math,
    _looks_like_formula,
    strip_ocr_noise,
)

# 裸 LaTeX / 半包装
_BEGIN_EQ = re.compile(
    r"\\begin\{(?:equation\*?|align\*?|multline\*?|gather\*?|eqnarray\*?)\}([\s\S]+?)\\end\{(?:equation\*?|align\*?|multline\*?|gather\*?|eqnarray\*?)\}",
    re.I,
)
_DISPLAY = re.compile(r"\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$")
_INLINE = re.compile(r"\\\(([\s\S]+?)\\\)|(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)")
_PROSE_PREFIX = re.compile(
    r"^(?:the\s+formula\s+is|formula\s*:|equation\s*:|如下|公式为|即为)\s*[:：]?\s*",
    re.I,
)
_EQ_TAG_TAIL = re.compile(r"(?:\\tag\*?\{[^}]*\}|(?:\\quad|\\qquad|\s)*[（(]\s*[\w.]+?\s*[）)])\s*$")


def salvage_formula_from_raw(raw: str) -> ExtractResult:
    """从单次 OCR raw 抢救唯一数学主体。禁止发明公式。"""
    text = strip_ocr_noise(raw or "").strip()
    if not text:
        return ExtractResult(block=None, method="none", failure_reason="no_equation_blocks")

    # 1) 标准块
    base = EquationExtractor()
    blocks = base.parse(text)
    if len(blocks) == 1:
        body = blocks[0].latex_or_text or ""
        if _looks_like_formula(body) and _prose_contamination_ok(body):
            return ExtractResult(
                block=blocks[0], method="formula_crop_single", blocks=blocks
            )
    if len(blocks) > 1:
        # crop 模式：取质量最高的一块（编号由 Identity 侧提供，不依赖 OCR 编号）
        scored = sorted(
            blocks,
            key=lambda b: (_formula_score(b.latex_or_text), -len(b.latex_or_text or "")),
            reverse=True,
        )
        best = scored[0]
        if _formula_score(best.latex_or_text) >= 0:
            return ExtractResult(
                block=best, method="formula_crop_best_of_many", blocks=blocks
            )

    # 2) begin{equation} 等
    m = _BEGIN_EQ.search(text)
    if m:
        body = _clean_math(m.group(1))
        if _looks_like_formula(body):
            blk = EquationBlock(latex_or_text=body, source="salvage_env")
            return ExtractResult(block=blk, method="formula_crop_env", blocks=[blk])

    # 3) 去散文前缀后的整段
    body = _PROSE_PREFIX.sub("", text).strip()
    body = _EQ_TAG_TAIL.sub("", body).strip()
    body = _clean_math(body)
    # 去掉残留 markdown 围栏
    body = re.sub(r"^```(?:math|latex|tex)?\s*", "", body, flags=re.I)
    body = re.sub(r"\s*```$", "", body).strip()
    if _looks_like_formula(body) and _prose_contamination_ok(body):
        blk = EquationBlock(latex_or_text=body, source="salvage_raw")
        return ExtractResult(block=blk, method="formula_crop_raw_salvage", blocks=[blk])

    # 4) 多行里挑最像公式的一行
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cands: list[str] = []
    for ln in lines:
        ln2 = _PROSE_PREFIX.sub("", ln)
        ln2 = _EQ_TAG_TAIL.sub("", ln2).strip()
        ln2 = _clean_math(ln2)
        if _looks_like_formula(ln2) and _prose_contamination_ok(ln2):
            cands.append(ln2)
    if len(cands) == 1:
        blk = EquationBlock(latex_or_text=cands[0], source="salvage_line")
        return ExtractResult(block=blk, method="formula_crop_line", blocks=[blk])
    if len(cands) > 1:
        best_ln = max(cands, key=_formula_score)
        if _formula_score(best_ln) >= 0:
            blk = EquationBlock(latex_or_text=best_ln, source="salvage_best_line")
            return ExtractResult(block=blk, method="formula_crop_best_line", blocks=[blk])

    return ExtractResult(
        block=None,
        method="none",
        failure_reason="no_equation_blocks",
        blocks=blocks,
    )


from app.formula.tokens import direction_flags


_EXP_HINT = re.compile(r"e\s*\^|\\exp\b|e\^\{-", re.I)
_PT1Q_HINT = re.compile(r"p_\{?\s*t\s*\+\s*1|mathbf\{p\}_\{t\+1\}", re.I)
_Q_HINT = re.compile(r"(?<![A-Za-z])Q(?![A-Za-z])")


def _pick_block_by_original(
    blocks: list[EquationBlock], original_latex: str
) -> EquationBlock | None:
    """多块 OCR 时按原文 max/min / exp / Q 方向选式，避免同页串位。"""
    if not blocks or not (original_latex or "").strip():
        return None
    orig = original_latex or ""
    orig_max, orig_min = direction_flags(orig)
    if orig_max or orig_min:
        hits: list[EquationBlock] = []
        for b in blocks:
            b_max, b_min = direction_flags(b.latex_or_text or "")
            if orig_max and b_max:
                hits.append(b)
            elif orig_min and b_min:
                hits.append(b)
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            hits.sort(key=lambda b: _formula_score(b.latex_or_text or ""), reverse=True)
            return hits[0]
    if _EXP_HINT.search(orig) and not _PT1Q_HINT.search(orig):
        hits = [b for b in blocks if _EXP_HINT.search(b.latex_or_text or "")]
        if len(hits) == 1:
            return hits[0]
        if hits:
            hits.sort(key=lambda b: _formula_score(b.latex_or_text or ""), reverse=True)
            return hits[0]
    if _PT1Q_HINT.search(orig) or _Q_HINT.search(orig):
        hits = [
            b
            for b in blocks
            if _PT1Q_HINT.search(b.latex_or_text or "")
            or _Q_HINT.search(b.latex_or_text or "")
        ]
        if len(hits) == 1:
            return hits[0]
        if hits:
            hits.sort(key=lambda b: _formula_score(b.latex_or_text or ""), reverse=True)
            return hits[0]
    return None


def extract_formula_crop(
    markdown: str,
    *,
    eq_number: str = "",
    context_before: str = "",
    context_after: str = "",
    original_latex: str = "",
) -> ExtractResult:
    """Formula crop 主路径：宽提取；编号匹配失败不否决。"""
    text = strip_ocr_noise(markdown or "")
    base = EquationExtractor()
    blocks = base.parse(text)
    n = str(eq_number or "").strip()

    if blocks:
        by_orig = _pick_block_by_original(blocks, original_latex)
        if by_orig is not None:
            return ExtractResult(
                block=by_orig,
                method="formula_crop_original_hint",
                blocks=blocks,
            )
        # 有编号时优先 exact，但失败不直接死
        if n:
            exact = [b for b in blocks if b.equation_number == n]
            if exact:
                exact.sort(key=lambda b: _formula_score(b.latex_or_text), reverse=True)
                return ExtractResult(
                    block=exact[0], method="formula_crop_exact_number", blocks=blocks
                )
        if len(blocks) == 1:
            body = blocks[0].latex_or_text or ""
            if _looks_like_formula(body) and _prose_contamination_ok(body):
                return ExtractResult(
                    block=blocks[0], method="formula_crop_single", blocks=blocks
                )
        # 多块：标签提示 → 否则 best
        sel = base.select(
            blocks,
            eq_number=n,
            context_before=context_before,
            context_after=context_after,
            markdown=text,
        )
        if sel.block:
            return ExtractResult(
                block=sel.block,
                method=f"formula_crop_{sel.method}",
                blocks=blocks,
            )
        scored = sorted(blocks, key=lambda b: _formula_score(b.latex_or_text), reverse=True)
        if scored and _formula_score(scored[0].latex_or_text) >= 0:
            return ExtractResult(
                block=scored[0],
                method="formula_crop_best_unnumbered",
                blocks=blocks,
            )

    # 无标准块 → salvage
    return salvage_formula_from_raw(text)


def _formula_score(s: str) -> float:
    t = (s or "").strip()
    if not t:
        return -10.0
    score = 0.0
    if "=" in t:
        score += 2.0
    if "\\" in t:
        score += 2.0
    if re.search(r"\\frac|\\sum|\\int|\\left|\\mathrm", t):
        score += 3.0
    words = re.findall(r"[A-Za-z]{4,}", t)
    if len(words) > 12:
        score -= 4.0
    if not _looks_like_formula(t):
        score -= 5.0
    return score


def _prose_contamination_ok(body: str) -> bool:
    """拒绝明显整段散文；允许短标签+公式。"""
    t = body or ""
    words4 = re.findall(r"[A-Za-z]{4,}", t)
    if (
        len(words4) >= 3
        and t.count("=") == 0
        and not re.search(
            r"\\(?:frac|sum|int|left|begin|mathrm|min|max|hat|bar)", t
        )
    ):
        return False
    words = re.findall(r"[A-Za-z]{3,}", t)
    if len(words) > 20 and t.count("=") == 0 and "\\" not in t:
        return False
    # 句子过长且公式符号少
    if len(t) > 400 and t.count("\\") < 2:
        return False
    return True


def salvage_meta(er: ExtractResult) -> dict[str, Any]:
    return {
        "method": er.method,
        "failure_reason": er.failure_reason,
        "salvaged": er.method.startswith("formula_crop") and bool(er.latex),
        "block_count": len(er.blocks),
    }
