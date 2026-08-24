# -*- coding: utf-8 -*-
"""Phase 7.2D sequential ranking 单测。"""
from __future__ import annotations

from app.formula.types import FormulaCandidate, FormulaQuality
from app.ocr.sequential_ranking import (
    TrajectoryState,
    dynamic_score_for_candidate,
    reorder_remaining,
)


def _cand(**kw) -> FormulaCandidate:
    base = dict(
        text="x",
        quality=FormulaQuality(corruption_score=0.8),
    )
    base.update(kw)
    return FormulaCandidate(**base)  # type: ignore[arg-type]


def test_extraction_streak_boosts_unnumbered():
    traj = TrajectoryState()
    numbered = _cand(
        page=3,
        equation_number="11",
        number_status="numbered_confirmed",
        context_before="Eq.(11)",
    )
    unnumbered = _cand(page=8, number_status="unnumbered_confirmed")
    # 模拟两次 numbered extraction 失败
    for _ in range(2):
        traj.observe(
            {
                "gate_accepted": False,
                "failure_class": "extraction_failure",
                "gate_reason": "no_equation_blocks",
                "page": 3,
                "eq_number": "11",
            },
            numbered,
        )
    assert traj.consecutive_extraction >= 2
    _, d_num, r_num = dynamic_score_for_candidate(
        numbered, static_score=2.0, traj=traj
    )
    _, d_un, r_un = dynamic_score_for_candidate(
        unnumbered, static_score=1.2, traj=traj
    )
    assert d_un > d_num
    assert any("explore_unnumbered" in x for x in r_un)


def test_same_page_success_promotes_peers():
    traj = TrajectoryState()
    a = _cand(
        page=9,
        equation_number="12",
        number_status="numbered_confirmed",
        context_before="Eq.(12)",
    )
    b = _cand(
        page=9,
        equation_number="11",
        number_status="numbered_confirmed",
        context_before="Eq.(11)",
    )
    other = _cand(page=3, number_status="unnumbered_confirmed")
    traj.observe(
        {
            "gate_accepted": True,
            "failure_class": "accepted",
            "page": 9,
            "eq_number": "12",
        },
        a,
    )
    remaining = [other, b]
    static = {id(other): 1.5, id(b): 1.4}
    new_order, expl = reorder_remaining(
        remaining, static_scores=static, traj=traj, after_attempt=1
    )
    assert new_order[0] is b
    assert expl["reorder_at_attempt"] == 1
    assert any(c["eq"] == "11" for c in expl["changes"]) or new_order[0] is b


def test_reorder_log_has_reasons():
    traj = TrajectoryState()
    c1 = _cand(page=1, number_status="unnumbered_confirmed")
    c2 = _cand(
        page=1,
        equation_number="2",
        number_status="numbered_confirmed",
        context_before="Eq.(2)",
    )
    traj.observe(
        {
            "gate_accepted": False,
            "failure_class": "context_strong_conflict",
            "gate_reason": "ocr_context_conflict",
            "page": 1,
        },
        c1,
    )
    traj.observe(
        {
            "gate_accepted": False,
            "failure_class": "context_strong_conflict",
            "gate_reason": "ocr_context_conflict",
            "page": 1,
        },
        c1,
    )
    new_order, expl = reorder_remaining(
        [c1, c2],
        static_scores={id(c1): 1.2, id(c2): 1.1},
        traj=traj,
        after_attempt=3,
    )
    assert new_order[0] is c2
    assert expl["changes"]
    assert any(ch.get("reasons") for ch in expl["changes"])
