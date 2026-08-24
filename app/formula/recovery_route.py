"""按损坏类型一次选路：禁止默认 UniMERNet→DeepSeek 串行。

k5：路由枚举改为语义型；旧 UNIMERNET / DEEPSEEK_DIRECT 保留为别名，测试与
legacy 生产路径不破。具体模型由 FormulaConfig.specialist_* / vlm_fallback_* 决定。
"""
from __future__ import annotations

from enum import Enum

from app.formula.backends import BACKEND_MODE_K5_SPECIALIST
from app.formula.types import FormulaCandidate, FormulaQuality


class RecoveryRoute(str, Enum):
    CHEAP_FIX = "cheap_fix"
    SPECIALIST_PRIMARY = "specialist_primary"
    VLM_FALLBACK = "vlm_fallback"
    ABSTAIN = "abstain"
    # legacy aliases（取值不变，供旧测试 / Lean DeepSeek 路径）
    UNIMERNET = "unimernet"
    DEEPSEEK_DIRECT = "deepseek_direct"
    SKIP = "skip"


def is_vlm_route(route: RecoveryRoute) -> bool:
    return route in {RecoveryRoute.VLM_FALLBACK, RecoveryRoute.DEEPSEEK_DIRECT}


def is_specialist_route(route: RecoveryRoute) -> bool:
    return route in {RecoveryRoute.SPECIALIST_PRIMARY, RecoveryRoute.UNIMERNET}


def is_abstain_route(route: RecoveryRoute) -> bool:
    return route in {RecoveryRoute.ABSTAIN, RecoveryRoute.SKIP}


def corruption_score_of(cand: FormulaCandidate) -> float:
    q = cand.quality
    if isinstance(q, FormulaQuality):
        return float(q.corruption_score or 0.0)
    return 0.0


def _is_severe(cand: FormulaCandidate) -> bool:
    text = (cand.raw_text or cand.text or "").strip()
    score = corruption_score_of(cand)
    issues = {str(x) for x in (cand.issues or [])}
    quad_heavy = text.count("\\quad") >= 8 or text.count("quad") >= 8
    very_long = len(text) > 400
    return score >= 0.8 or quad_heavy or very_long or "hallucination" in issues


def route_corrupted_formula(
    cand: FormulaCandidate,
    *,
    deepseek_available: bool,
    prefer_deepseek_primary: bool = True,
    lean_deepseek_only: bool = False,
    backend_mode: str = "legacy_deepseek",
    recovery_preset: str = "balanced",
    specialist_available: bool = True,
    vlm_available: bool | None = None,
) -> RecoveryRoute:
    """规则选路（无模型）。

    lean_deepseek_only=True（Phase 5E Lean Balanced）：
    有 DeepSeek 时一律 DEEPSEEK_DIRECT，永不默认 UniMERNet。

    backend_mode=k5_specialist：SPECIALIST_PRIMARY / VLM_FALLBACK / ABSTAIN。
    """
    vlm_ok = deepseek_available if vlm_available is None else bool(vlm_available)

    if (backend_mode or "").strip().lower() == BACKEND_MODE_K5_SPECIALIST:
        preset = (recovery_preset or "balanced").strip().lower()
        severe = _is_severe(cand)
        if preset == "fast":
            if specialist_available:
                return RecoveryRoute.SPECIALIST_PRIMARY
            return RecoveryRoute.ABSTAIN
        if preset == "quality":
            if severe and vlm_ok:
                return RecoveryRoute.VLM_FALLBACK
            if specialist_available:
                return RecoveryRoute.SPECIALIST_PRIMARY
            if vlm_ok:
                return RecoveryRoute.VLM_FALLBACK
            return RecoveryRoute.ABSTAIN
        # balanced：普通 → specialist；hard → VLM
        if severe:
            if vlm_ok:
                return RecoveryRoute.VLM_FALLBACK
            if specialist_available:
                return RecoveryRoute.SPECIALIST_PRIMARY
            return RecoveryRoute.ABSTAIN
        if specialist_available:
            return RecoveryRoute.SPECIALIST_PRIMARY
        if vlm_ok:
            return RecoveryRoute.VLM_FALLBACK
        return RecoveryRoute.ABSTAIN

    if lean_deepseek_only and deepseek_available:
        return RecoveryRoute.DEEPSEEK_DIRECT

    score = corruption_score_of(cand)
    severe = _is_severe(cand)

    if prefer_deepseek_primary and deepseek_available:
        if severe or score >= 0.5:
            return RecoveryRoute.DEEPSEEK_DIRECT
        return RecoveryRoute.UNIMERNET

    if severe and deepseek_available:
        return RecoveryRoute.DEEPSEEK_DIRECT
    return RecoveryRoute.UNIMERNET
