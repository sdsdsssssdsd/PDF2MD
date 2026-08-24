# -*- coding: utf-8 -*-
"""Phase 7.2D：Sequential Ranking — 只动态重排，不 stop / 不减 OCR。

硬约束：
- 不使用本篇最终 profile / 未执行 candidate 的未来结果
- 特征仅限「当时已观测」的 trajectory + 该 candidate 的静态分
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.formula.types import FormulaCandidate
from app.ocr.executor import eq_number_from_candidate
from app.ocr.prioritization import (
    NUM_CONFIRMED,
    NUM_PLAUSIBLE,
    candidate_priority_score,
    classify_equation_number_plausibility,
)


@dataclass
class TrajectoryState:
    """截至当前 attempt 的已观测恢复轨迹（无未来泄漏）。"""

    n_done: int = 0
    n_accepted: int = 0
    failure_counts: Counter[str] = field(default_factory=Counter)
    consecutive_extraction: int = 0
    consecutive_context_conflict: int = 0
    page_attempts: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    page_accepts: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    numbered_attempts: int = 0
    numbered_accepts: int = 0
    source_attempts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    source_accepts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    recent_outcomes: list[bool] = field(default_factory=list)  # True=accept

    def observe(self, row: dict[str, Any], cand: FormulaCandidate | None = None) -> None:
        self.n_done += 1
        accepted = bool(row.get("gate_accepted"))
        fc = str(row.get("failure_class") or ("accepted" if accepted else "unknown"))
        page = row.get("page")
        if page is None and cand is not None:
            page = cand.page
        try:
            page_i = int(page) if page is not None else -1
        except (TypeError, ValueError):
            page_i = -1

        self.page_attempts[page_i] += 1
        src = ""
        numbered = False
        if cand is not None:
            src = str(getattr(cand, "source_type", "") or "")
            plaus = classify_equation_number_plausibility(cand)
            numbered = plaus["class"] in {NUM_CONFIRMED, NUM_PLAUSIBLE}
        else:
            eq = str(row.get("eq_number") or "").strip()
            numbered = bool(eq) and not (
                eq.isdigit() and 1900 <= int(eq) <= 2100
            )

        if src:
            self.source_attempts[src] += 1
        if numbered:
            self.numbered_attempts += 1

        self.recent_outcomes.append(accepted)
        if len(self.recent_outcomes) > 6:
            self.recent_outcomes = self.recent_outcomes[-6:]

        if accepted:
            self.n_accepted += 1
            self.page_accepts[page_i] += 1
            if numbered:
                self.numbered_accepts += 1
            if src:
                self.source_accepts[src] += 1
            self.consecutive_extraction = 0
            self.consecutive_context_conflict = 0
            return

        self.failure_counts[fc] += 1
        if fc == "extraction_failure" or "no_equation_blocks" in str(
            row.get("gate_reason") or ""
        ):
            self.consecutive_extraction += 1
            self.consecutive_context_conflict = 0
        elif fc in {"context_strong_conflict", "context_insufficient"} or (
            "ocr_context_conflict" in str(row.get("gate_reason") or "")
        ):
            self.consecutive_context_conflict += 1
            self.consecutive_extraction = 0
        else:
            self.consecutive_extraction = 0
            self.consecutive_context_conflict = 0

    @property
    def recent_accept_rate(self) -> float:
        if not self.recent_outcomes:
            return 0.5
        return sum(1 for x in self.recent_outcomes if x) / len(self.recent_outcomes)

    def same_page_success_rate(self, page: int | None) -> float | None:
        if page is None:
            return None
        try:
            p = int(page)
        except (TypeError, ValueError):
            return None
        att = int(self.page_attempts.get(p, 0))
        if att <= 0:
            return None
        return float(self.page_accepts.get(p, 0)) / float(att)

    def numbered_success_rate(self) -> float | None:
        if self.numbered_attempts <= 0:
            return None
        return self.numbered_accepts / self.numbered_attempts

    def source_success_rate(self, source: str) -> float | None:
        att = int(self.source_attempts.get(source, 0))
        if att <= 0:
            return None
        return float(self.source_accepts.get(source, 0)) / float(att)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_done": self.n_done,
            "n_accepted": self.n_accepted,
            "recent_accept_rate": round(self.recent_accept_rate, 4),
            "failure_class_counts_so_far": dict(self.failure_counts),
            "consecutive_extraction_failures": self.consecutive_extraction,
            "consecutive_context_conflicts": self.consecutive_context_conflict,
            "numbered_success_rate_so_far": self.numbered_success_rate(),
        }


def dynamic_score_for_candidate(
    cand: FormulaCandidate,
    *,
    static_score: float,
    traj: TrajectoryState,
) -> tuple[float, float, list[str]]:
    """返回 (dynamic_total, dynamic_delta, reasons)。"""
    reasons: list[str] = []
    delta = 0.0
    plaus = classify_equation_number_plausibility(cand)
    numbered = plaus["class"] in {NUM_CONFIRMED, NUM_PLAUSIBLE}
    page = cand.page
    src = str(getattr(cand, "source_type", "") or "")

    # same-page success
    spr = traj.same_page_success_rate(page)
    if spr is not None:
        if spr >= 0.5:
            b = 0.55 + 0.35 * spr
            delta += b
            reasons.append(f"+{b:.2f} same_page_success({spr:.2f})")
        elif spr == 0.0 and traj.page_attempts.get(int(page) if page is not None else -1, 0) >= 2:
            pen = 0.45
            delta -= pen
            reasons.append(f"-{pen:.2f} same_page_all_failed")

    # numbered success pattern so far
    nsr = traj.numbered_success_rate()
    if numbered and nsr is not None:
        if nsr >= 0.5:
            b = 0.5
            delta += b
            reasons.append(f"+{b:.2f} numbered_success_pattern({nsr:.2f})")
        elif nsr == 0.0 and traj.numbered_attempts >= 2:
            pen = 0.35
            delta -= pen
            reasons.append(f"-{pen:.2f} numbered_failing_streak")

    # source success
    if src:
        ssr = traj.source_success_rate(src)
        if ssr is not None and ssr >= 0.5:
            b = 0.25
            delta += b
            reasons.append(f"+{b:.2f} source_success({src},{ssr:.2f})")

    # recent failure pattern penalties（作用于剩余队列整体偏好）
    if traj.consecutive_extraction >= 2 and numbered:
        # 连续 extraction 失败后，略压 numbered（可能是 crop 编号噪声），抬 unnumbered 试探
        pen = 0.25 * min(3, traj.consecutive_extraction - 1)
        delta -= pen
        reasons.append(f"-{pen:.2f} consecutive_extraction_on_numbered")
    if traj.consecutive_extraction >= 2 and not numbered:
        b = 0.35
        delta += b
        reasons.append(f"+{b:.2f} explore_unnumbered_after_extract_streak")

    if traj.consecutive_context_conflict >= 2 and not numbered:
        pen = 0.4
        delta -= pen
        reasons.append(f"-{pen:.2f} repeated_context_conflict_pattern")
    if traj.consecutive_context_conflict >= 2 and numbered:
        b = 0.3
        delta += b
        reasons.append(f"+{b:.2f} prefer_numbered_after_conflict_streak")

    # recent accept rate：整体很差时略抬高与成功页同页的（已在 same_page 处理）
    if traj.recent_accept_rate <= 0.2 and traj.n_done >= 3 and numbered and nsr and nsr > 0:
        b = 0.2
        delta += b
        reasons.append(f"+{b:.2f} sparse_accept_keep_numbered_working")

    total = float(static_score) + delta
    if not reasons:
        reasons.append("+0.00 no_dynamic_signal")
    return round(total, 4), round(delta, 4), reasons


def reorder_remaining(
    remaining: list[FormulaCandidate],
    *,
    static_scores: dict[int, float],
    traj: TrajectoryState,
    after_attempt: int,
) -> tuple[list[FormulaCandidate], dict[str, Any]]:
    """对剩余 candidate 按 dynamic_score 重排；写解释日志。"""
    if len(remaining) <= 1:
        return list(remaining), {
            "reorder_at_attempt": after_attempt,
            "n_remaining": len(remaining),
            "changes": [],
        }

    old_rank = {id(c): i + 1 for i, c in enumerate(remaining)}
    scored: list[tuple[float, int, FormulaCandidate, float, float, list[str]]] = []
    for i, c in enumerate(remaining):
        sid = id(c)
        static = float(static_scores.get(sid, candidate_priority_score(c)["total"]))
        total, delta, reasons = dynamic_score_for_candidate(
            c, static_score=static, traj=traj
        )
        scored.append((-total, i, c, static, delta, reasons))
    scored.sort()
    new_order = [t[2] for t in scored]
    changes: list[dict[str, Any]] = []
    for new_i, t in enumerate(scored, start=1):
        c = t[2]
        oid = id(c)
        prev = old_rank.get(oid, new_i)
        if prev == new_i and abs(t[4]) < 1e-9:
            continue
        changes.append(
            {
                "candidate_id": f"p{c.page}_eq{eq_number_from_candidate(c) or 'x'}",
                "eq": eq_number_from_candidate(c),
                "page": c.page,
                "old_rank": prev,
                "new_rank": new_i,
                "static_score": t[3],
                "dynamic_delta": t[4],
                "dynamic_total": round(-t[0], 4),
                "reasons": t[5],
            }
        )
    # 按 rank 变化幅度排序，方便阅读
    changes.sort(key=lambda x: abs(int(x["old_rank"]) - int(x["new_rank"])), reverse=True)
    return new_order, {
        "reorder_at_attempt": after_attempt,
        "n_remaining": len(new_order),
        "trajectory_snapshot": traj.to_dict(),
        "changes": changes,
    }


def build_static_score_map(
    ordered: list[FormulaCandidate],
    order_meta: dict[str, Any] | None,
) -> dict[int, float]:
    """从初始 prioritize 结果建立 id→static_score。"""
    out: dict[int, float] = {}
    scores = list((order_meta or {}).get("scores") or [])
    if scores and len(scores) == len(ordered):
        for c, s in zip(ordered, scores):
            out[id(c)] = float(s.get("total") or 0.0)
        return out
    for c in ordered:
        out[id(c)] = float(candidate_priority_score(c)["total"])
    return out
