# -*- coding: utf-8 -*-
"""Phase 7.2B0.1：cost-aware candidate prioritization + number plausibility。

硬约束：
- 禁止使用本篇最终 document profile / accept_rate / failure_class_counts
- 禁止 production early-stop（B1 才开）
- 特征仅限 OCR 前已知量 + 跨文档历史粗粒度 prior
"""
from __future__ import annotations

import re
from typing import Any, Sequence

from app.formula.types import FormulaCandidate
from app.ocr.executor import eq_number_from_candidate

_MATH_TOKEN = re.compile(
    r"\\[a-zA-Z]+|[_^]|\{|\}|=|\\frac|\\sum|\\int|\\left|\\right|\\mathrm|\\mathbf"
)
_EQ_MARK = re.compile(r"(?:Eq\.?|Equation|式)\s*\(\s*\d+\s*\)", re.I)
_EQ_MARK_LOOSE = re.compile(r"(?:Eq\.?|Equation|式)\s*\(\s*(\d+)\s*\)|\((\d+)\)", re.I)
_NON_EQ_CTX = re.compile(
    r"\b(fig(?:ure)?|table|tab\.?|section|sec\.?|chapter|chap\.?|year|vol\.?|pp\.?|"
    r"page|pages|doi|isbn|issn)\b",
    re.I,
)
_PCT = re.compile(r"^\d+%$")
_FLOAT = re.compile(r"^\d+\.\d+$")
_YEAR_CTX = re.compile(
    r"\b(19|20)\d{2}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|"
    r"\b(published|copyright|©|arxiv)\b",
    re.I,
)

# number plausibility classes（观测用 taxonomy，不是策略标签）
NUM_CONFIRMED = "confirmed_equation_number"
NUM_PLAUSIBLE = "plausible_equation_number"
NUM_SUSPICIOUS = "suspicious_number"
NUM_NON_EQ = "non_equation_number"
NUM_UNNUMBERED = "unnumbered"
NUM_NONE = "none"


def _math_density(text: str) -> float:
    t = (text or "").strip()
    if not t:
        return 0.0
    hits = len(_MATH_TOKEN.findall(t))
    return min(1.0, hits / max(8.0, len(t) / 12.0))


def _bbox_area(cand: FormulaCandidate) -> float:
    b = cand.bbox
    if not b or len(b) != 4:
        return 0.0
    return max(0.0, float(b[2]) - float(b[0])) * max(0.0, float(b[3]) - float(b[1]))


def _bbox_right_bias(cand: FormulaCandidate) -> float:
    """右侧编号常见：bbox 越靠右略加分（无 page width 时用 x0 粗信号）。"""
    b = cand.bbox
    if not b or len(b) != 4:
        return 0.0
    x0 = float(b[0])
    # 学术 PDF 常见页宽 ~600pt；x0>350 偏右栏/右缘编号区
    if x0 >= 350:
        return 0.12
    if x0 >= 250:
        return 0.06
    return 0.0


def structural_math_score(cand: FormulaCandidate) -> float:
    """残串里仍有数学结构 → 更可能 OCR 后可抽取。"""
    blob = " ".join(x for x in (cand.raw_text or "", cand.text or "") if x)
    dens = _math_density(blob)
    q = cand.quality
    corr = float(q.corruption_score) if q else 0.5
    return round(0.55 * dens + 0.25 * min(1.0, corr) + 0.20 * min(1.0, dens * corr), 4)


def classify_equation_number_plausibility(cand: FormulaCandidate) -> dict[str, Any]:
    """方程编号可信度（替代「见数字就加分」）。

    classes:
      confirmed_equation_number | plausible_equation_number |
      suspicious_number | non_equation_number | unnumbered | none
    """
    ns = (getattr(cand, "number_status", "") or "").strip()
    bound = (cand.equation_number or "").strip()
    token = bound or eq_number_from_candidate(cand)
    ctx = f"{cand.context_before or ''} {cand.context_after or ''} {cand.text or ''}"
    reasons: list[str] = []

    if not token:
        if ns == "unnumbered_confirmed":
            return {
                "class": NUM_UNNUMBERED,
                "token": "",
                "score": 0.35,
                "reasons": ["unnumbered_confirmed"],
            }
        return {
            "class": NUM_NONE,
            "token": "",
            "score": 0.15,
            "reasons": ["no_number_token"],
        }

    if _PCT.match(token) or _FLOAT.match(token):
        return {
            "class": NUM_NON_EQ,
            "token": token,
            "score": 0.05,
            "reasons": ["percent_or_float_token"],
        }

    try:
        n = int(token)
    except ValueError:
        return {
            "class": NUM_SUSPICIOUS,
            "token": token,
            "score": 0.2,
            "reasons": ["non_int_token"],
        }

    if n == 0:
        return {
            "class": NUM_NON_EQ,
            "token": token,
            "score": 0.05,
            "reasons": ["equation_index_zero"],
        }

    # 年份带：四位 + 散文/年语境 + 无 Eq. 定界 → 强降权
    if 1900 <= n <= 2100:
        reasons.append("year_band")
        has_eq_delim = bool(
            re.search(rf"(?:Eq\.?|Equation|式)\s*\(\s*{n}\s*\)", ctx, re.I)
        )
        yearish = bool(_YEAR_CTX.search(ctx)) or not has_eq_delim
        if yearish and not has_eq_delim:
            reasons.append("year_or_prose_without_eq_delim")
            return {
                "class": NUM_NON_EQ,
                "token": token,
                "score": 0.05,
                "reasons": reasons,
            }
        reasons.append("year_band_but_eq_delim_present")
        return {
            "class": NUM_SUSPICIOUS,
            "token": token,
            "score": 0.15,
            "reasons": reasons,
        }

    if _NON_EQ_CTX.search(ctx):
        has_eq_for_n = bool(
            re.search(rf"(?:Eq\.?|Equation|式)\s*\(\s*{n}\s*\)", ctx, re.I)
        )
        if not has_eq_for_n:
            reasons.append("fig_table_section_context")
            return {
                "class": NUM_SUSPICIOUS,
                "token": token,
                "score": 0.2,
                "reasons": reasons,
            }

    if n > 200:
        reasons.append("large_equation_index")
        return {
            "class": NUM_SUSPICIOUS,
            "token": token,
            "score": 0.25,
            "reasons": reasons,
        }

    # 可信编号
    if ns == "numbered_confirmed" or bound:
        reasons.append("structure_bound_or_confirmed")
        return {
            "class": NUM_CONFIRMED,
            "token": token,
            "score": 1.0,
            "reasons": reasons,
        }
    if re.search(rf"(?:Eq\.?|Equation|式)\s*\(\s*{n}\s*\)", ctx, re.I):
        reasons.append("eq_marker_in_context")
        return {
            "class": NUM_PLAUSIBLE,
            "token": token,
            "score": 0.85,
            "reasons": reasons,
        }
    # 裸 (n) / 弱绑定
    if 1 <= n <= 200:
        reasons.append("bare_or_weak_number")
        return {
            "class": NUM_PLAUSIBLE,
            "token": token,
            "score": 0.55,
            "reasons": reasons,
        }
    return {
        "class": NUM_SUSPICIOUS,
        "token": token,
        "score": 0.25,
        "reasons": reasons or ["fallback"],
    }


def equation_number_score(cand: FormulaCandidate) -> float:
    """兼容旧名：返回 plausibility score。"""
    return float(classify_equation_number_plausibility(cand)["score"])


def context_support_score(cand: FormulaCandidate) -> float:
    """上下文是否像在指向编号公式（非事后 Gate）。"""
    ctx = f"{cand.context_before or ''} {cand.context_after or ''}"
    # 只用真正的 Eq./Equation/式，避免把任意 (n) 当支持
    marks = len(_EQ_MARK.findall(ctx))
    if marks >= 2:
        return 1.0
    if marks == 1:
        return 0.7
    if "$" in ctx or "\\" in ctx:
        return 0.35
    return 0.1


def historical_recovery_prior(cand: FormulaCandidate) -> float:
    """跨文档粗粒度 prior（可选；读不到则中性 0.5）。"""
    try:
        from app.diagnostics.failure_memory import default_failure_memory_root
        import json

        path = default_failure_memory_root() / "summary.json"
        if not path.is_file():
            return 0.5
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0.5

    totals = data.get("failure_class_totals") or {}
    conflict = int(totals.get("context_strong_conflict") or 0)
    extraction = int(totals.get("extraction_failure") or 0)
    insufficient = int(totals.get("context_insufficient") or 0)
    denom = max(1, conflict + extraction + insufficient)
    base = 0.55
    plaus = classify_equation_number_plausibility(cand)
    if plaus["class"] in {NUM_CONFIRMED, NUM_PLAUSIBLE}:
        base += 0.15
    elif plaus["class"] == NUM_NON_EQ:
        base -= 0.1
    if cand.source_type == "parser_math":
        base += 0.05
    if conflict / denom > 0.45:
        base -= 0.05
    return round(min(1.0, max(0.0, base)), 4)


def historical_conflict_penalty(cand: FormulaCandidate) -> float:
    """历史 conflict 占比带来的弱惩罚（0~0.3）。"""
    try:
        from app.diagnostics.failure_memory import default_failure_memory_root
        import json

        path = default_failure_memory_root() / "summary.json"
        if not path.is_file():
            return 0.0
        data = json.loads(path.read_text(encoding="utf-8"))
        totals = data.get("failure_class_totals") or {}
        conflict = int(totals.get("context_strong_conflict") or 0)
        all_n = sum(int(v) for v in totals.values()) or 1
        ratio = conflict / all_n
        plaus = classify_equation_number_plausibility(cand)
        if plaus["class"] in {NUM_NONE, NUM_UNNUMBERED, NUM_NON_EQ} and ratio > 0.4:
            return round(min(0.3, ratio * 0.4), 4)
        return 0.0
    except Exception:
        return 0.0


def candidate_priority_score(cand: FormulaCandidate) -> dict[str, Any]:
    """返回分项 + 总分 + 编号可信度诊断字段。"""
    blob = " ".join(x for x in (cand.raw_text or "", cand.text or "") if x)
    dens = _math_density(blob)
    plaus = classify_equation_number_plausibility(cand)
    s_struct = structural_math_score(cand)
    s_num = float(plaus["score"])
    s_ctx = context_support_score(cand)
    s_hist = historical_recovery_prior(cand)
    pen = historical_conflict_penalty(cand)
    area = _bbox_area(cand)
    geo = 0.0
    if area > 0:
        geo = min(1.0, area / 8000.0) * 0.15
    right = _bbox_right_bias(cand)
    # 非方程编号：额外硬罚，避免 2019 挤占前排
    non_eq_pen = 0.8 if plaus["class"] == NUM_NON_EQ else (
        0.35 if plaus["class"] == NUM_SUSPICIOUS else 0.0
    )
    total = (
        1.0 * s_struct
        + 1.2 * s_num
        + 0.8 * s_ctx
        + 0.6 * s_hist
        + geo
        + right
        - pen
        - non_eq_pen
    )
    return {
        "structural_math": s_struct,
        "equation_number": s_num,
        "equation_number_plausibility": plaus["class"],
        "number_token": plaus["token"],
        "number_reasons": list(plaus["reasons"]),
        "math_density": round(dens, 4),
        "context_support": s_ctx,
        "historical_prior": s_hist,
        "geometry_bonus": round(geo, 4),
        "right_margin_bonus": round(right, 4),
        "conflict_penalty": pen,
        "non_eq_number_penalty": non_eq_pen,
        "number_status": (getattr(cand, "number_status", "") or ""),
        "candidate_source": getattr(cand, "source_type", "") or "",
        "total": round(total, 4),
    }


def prioritize_candidates(
    candidates: Sequence[FormulaCandidate],
    *,
    enabled: bool = True,
) -> tuple[list[FormulaCandidate], dict[str, Any]]:
    """7.2B0.1：确定性重排。enabled=False 时退回 (page, eq) 阅读序。"""

    def reading_key(c: FormulaCandidate) -> tuple:
        page = int(c.page) if c.page is not None else 10**9
        plaus = classify_equation_number_plausibility(c)
        token = str(plaus.get("token") or "")
        # 非方程编号不参与 eq tie-break（避免 2019 干扰稳定序）
        if plaus["class"] in {NUM_NON_EQ, NUM_SUSPICIOUS}:
            eq_n = 10**6
        else:
            try:
                eq_n = int(token) if token else 10**6
            except ValueError:
                eq_n = 10**6
        return (page, eq_n)

    cands = list(candidates)
    if not enabled or len(cands) <= 1:
        ordered = sorted(cands, key=reading_key)
        return ordered, {
            "enabled": bool(enabled),
            "mode": "reading_order",
            "version": "b0.1",
            "n": len(ordered),
            "scores": [],
        }

    scored: list[tuple[float, tuple, int, FormulaCandidate, dict[str, Any]]] = []
    for i, c in enumerate(cands):
        parts = candidate_priority_score(c)
        scored.append((-float(parts["total"]), reading_key(c), i, c, parts))
    scored.sort()
    ordered = [t[3] for t in scored]
    return ordered, {
        "enabled": True,
        "mode": "priority_score_v1_plausibility",
        "version": "b0.1",
        "n": len(ordered),
        "scores": [
            {
                "attempt_index_if_run": rank,
                "eq": t[4].get("number_token") or eq_number_from_candidate(t[3]),
                "page": t[3].page,
                "total": t[4]["total"],
                "parts": {
                    k: v
                    for k, v in t[4].items()
                    if k
                    not in {
                        "total",
                        "number_reasons",
                        "equation_number_plausibility",
                        "number_token",
                        "number_status",
                        "candidate_source",
                    }
                },
                "equation_number_plausibility": t[4].get(
                    "equation_number_plausibility"
                ),
                "number_token": t[4].get("number_token"),
                "number_reasons": t[4].get("number_reasons"),
                "math_density": t[4].get("math_density"),
                "number_status": t[4].get("number_status"),
                "candidate_source": t[4].get("candidate_source"),
                "reading_rank": list(reading_key(t[3])),
            }
            for rank, t in enumerate(scored, start=1)
        ],
    }


def build_counterfactual_budget(
    rows: list[dict[str, Any]],
    *,
    budgets: Sequence[int] = (4, 6, 8, 10),
) -> dict[str, Any]:
    """事后反事实：stop_after=K 的 accepted / Recall@K（不真停 OCR）。"""
    rows = list(rows or [])
    n = len(rows)
    accepted_flags = [bool(r.get("gate_accepted")) for r in rows]
    total_accepted = sum(1 for a in accepted_flags if a)
    secs: list[float] = []
    for r in rows:
        timing = r.get("timing") if isinstance(r.get("timing"), dict) else {}
        secs.append(
            float(
                timing.get("ocr_seconds")
                or timing.get("worker_inference_seconds")
                or r.get("ocr_seconds")
                or 0.0
            )
        )
    total_secs = sum(secs)
    out: dict[str, Any] = {
        "n_attempts": n,
        "total_accepted": total_accepted,
        "total_ocr_seconds": round(total_secs, 3),
        "budgets": {},
        "recall_at_k": {},
    }
    for k in budgets:
        kk = int(k)
        if kk <= 0:
            continue
        head = accepted_flags[:kk]
        head_secs = secs[:kk]
        acc = sum(1 for a in head if a)
        recall = (acc / total_accepted) if total_accepted else 1.0
        saved_calls = max(0, n - min(kk, n))
        saved_secs = max(0.0, total_secs - sum(head_secs))
        entry = {
            "accepted": acc,
            "accept_recall": round(recall, 4),
            "ocr_calls_saved": saved_calls,
            "seconds_saved": round(saved_secs, 3),
        }
        out["budgets"][str(kk)] = entry
        out["recall_at_k"][str(kk)] = round(recall, 4)
    return out


def build_ranking_error_analysis(
    order_meta: dict[str, Any] | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """将 pre-OCR score components 与最终 accept 对齐，供 B0.1 诊断。

    回答：accepted 尾部是「打分错了」还是「事前不可区分」。
    """
    scores = list((order_meta or {}).get("scores") or [])
    rows = list(rows or [])
    n = min(len(scores), len(rows))
    joined: list[dict[str, Any]] = []
    for i in range(n):
        s = scores[i]
        r = rows[i]
        joined.append(
            {
                "attempt_index": i + 1,
                "priority_score": s.get("total"),
                "accepted": bool(r.get("gate_accepted")),
                "failure_class": r.get("failure_class"),
                "eq_number": r.get("eq_number") or s.get("eq"),
                "number_token": s.get("number_token"),
                "equation_number_plausibility": s.get(
                    "equation_number_plausibility"
                ),
                "number_status": s.get("number_status"),
                "math_density": s.get("math_density"),
                "candidate_source": s.get("candidate_source"),
                "parts": s.get("parts") or {},
                "number_reasons": s.get("number_reasons") or [],
                "page": s.get("page") if s.get("page") is not None else r.get("page"),
            }
        )
    accepted_rows = [j for j in joined if j["accepted"]]
    rejected_rows = [j for j in joined if not j["accepted"]]
    # 特征塌缩：accepted 与同档 rejected 的 score 是否几乎相同
    def _avg(key: str, items: list[dict[str, Any]]) -> float | None:
        vals = []
        for it in items:
            parts = it.get("parts") or {}
            if key == "total":
                vals.append(float(it.get("priority_score") or 0))
            elif key in parts:
                vals.append(float(parts[key]))
            elif key in it and isinstance(it[key], (int, float)):
                vals.append(float(it[key]))
        if not vals:
            return None
        return round(sum(vals) / len(vals), 4)

    late_acc = [j for j in accepted_rows if int(j["attempt_index"]) >= 8]
    early_rej = [j for j in rejected_rows if 2 <= int(j["attempt_index"]) <= 8]
    indistinguishable = False
    same_tier_note = ""
    if late_acc:
        a_tot = _avg("total", late_acc) or 0
        # 同档 rejected：分数与 late accepted 几乎相同（真正的事前不可分）
        same_tier_rej = [
            j
            for j in rejected_rows
            if abs(float(j.get("priority_score") or 0) - a_tot) < 0.08
        ]
        early_mid = [j for j in early_rej if j not in same_tier_rej]
        r_same = _avg("total", same_tier_rej)
        r_hot = _avg("total", early_rej)
        # 假设 B：late accepted 与同档 rejected 分差极小，且同档 rejected 数量>0
        indistinguishable = bool(same_tier_rej) and (
            r_same is None or abs(a_tot - float(r_same)) < 0.08
        )
        same_tier_note = (
            f"late_acc_avg={a_tot}; same_tier_rejected={len(same_tier_rej)}; "
            f"hot_rejected_2_8_avg={r_hot}"
        )
    else:
        same_tier_rej = []

    cf = build_counterfactual_budget(rows)
    return {
        "version": "b0.1",
        "n_joined": n,
        "rows": joined,
        "accepted_attempt_indices": [j["attempt_index"] for j in accepted_rows],
        "rejected_mid_vs_late_accepted": {
            "late_accepted": late_acc,
            "rejected_rank_2_to_8": early_rej,
            "same_tier_rejected": same_tier_rej,
            "avg_score_late_accepted": _avg("total", late_acc),
            "avg_score_rejected_2_8": _avg("total", early_rej),
            "avg_score_same_tier_rejected": _avg("total", same_tier_rej),
            "pre_ocr_indistinguishable_hypothesis_b": indistinguishable,
            "note": same_tier_note,
        },
        "recall_at_k": cf.get("recall_at_k") or {},
        "counterfactual_budget": cf,
        "non_eq_numbers_in_top5": [
            j
            for j in joined[:5]
            if j.get("equation_number_plausibility")
            in {NUM_NON_EQ, NUM_SUSPICIOUS}
        ],
    }
