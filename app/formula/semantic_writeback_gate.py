# -*- coding: utf-8 -*-
"""写回前语义槽位门：仅拦截「明显章节错配」（窄上下文窗口）。"""
from __future__ import annotations

import re

_LATEX_SIGNAL = re.compile(r"\\[a-zA-Z]+|[_^]|\\frac|\\sum|\\begin")

# (ctx 触发词, ctx 需命中数, latex 冲突词)
_TOPIC_RULES: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    (
        "isotonic",
        ("isotonic", "nondecreasing", "non-decreasing", "least squares", "xi-1", "x_{i-1}"),
        ("pr(m", "pr(m_", "m_1|d", "m_2|d", "bayes factor", "\\frac{pr("),
    ),
    (
        "bayes",
        ("bayes factor", "bayes factors", "model comparison", "models m_1", "models m 1"),
        ("isotonic", "nondecreasing", "x_{i-1}", "least squaresfit"),
    ),
    (
        "membership",
        ("membership matrix", "belongs to community", "node i belongs"),
        ("p_{t+1}", "p_t q", "mathbf{p}_{t+1}", "transition matrix"),
    ),
    (
        "transition",
        ("transition matrix", "discrete-time process", "random walk", "p_{t+1}"),
        ("h_{lc}", "h_{i c}", "membership matrix", "belongs to community"),
    ),
    (
        "markov_stability",
        ("markov stability", "autocovariance matrix", "block autocovariance", "cost function, the markov"),
        ("h_{lc}=", "belongs to community", "isotonic"),
    ),
]

_CTX_WINDOW = 280


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower())


def semantic_slot_conflict(context_before: str, latex: str) -> tuple[bool, str]:
    """返回 (ok, reason)。仅当局部上下文强指向 A、LaTeX 强指向 B≠A 时拒写。"""
    lat = _norm(latex)
    if not lat or not _LATEX_SIGNAL.search(latex or ""):
        return True, ""

    ctx = _norm((context_before or "")[-_CTX_WINDOW:])

    for tag, ctx_needles, lat_conflict in _TOPIC_RULES:
        ctx_hits = sum(1 for n in ctx_needles if n in ctx)
        if ctx_hits < 1:
            continue
        lat_hits = sum(1 for n in lat_conflict if n in lat)
        if lat_hits >= 1:
            return False, f"semantic_context_conflict:{tag}"
    return True, ""
