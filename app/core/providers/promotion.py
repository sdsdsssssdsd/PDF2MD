"""Provider 晋级：experimental → candidate → supported → default-eligible。

质量 / 稳定性 / 资源 / 许可 / 可分发性 五门全过才晋级。
Benchmark 第一名不够；default-eligible 还要有可接受的 delta。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.providers.descriptor import ProviderDescriptor

GATES = ("quality", "stability", "resources", "license", "distributability")

DEFAULT_BLOCKED_LICENSES = frozenset({"openrail-m", "unknown", "proprietary-site"})


class PromotionTrack:
    EXPERIMENTAL = "experimental"
    CANDIDATE = "candidate"
    SUPPORTED = "supported"
    DEFAULT_ELIGIBLE = "default-eligible"

    ORDER = (EXPERIMENTAL, CANDIDATE, SUPPORTED, DEFAULT_ELIGIBLE)


@dataclass
class PromotionDecision:
    provider_id: str
    current: str
    target: str
    allowed: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "current": self.current,
            "target": self.target,
            "allowed": self.allowed,
            "reasons": list(self.reasons),
        }


def track_of(descriptor: ProviderDescriptor) -> str:
    track = str(getattr(descriptor, "track", "") or "")
    if track:
        return track
    return PromotionTrack.EXPERIMENTAL if descriptor.experimental else PromotionTrack.SUPPORTED


def evaluate_promotion(
    descriptor: ProviderDescriptor,
    *,
    target: str,
    gates: dict[str, bool],
    benchmark_allowed: bool | None = None,
) -> PromotionDecision:
    current = track_of(descriptor)
    reasons: list[str] = []
    if target not in PromotionTrack.ORDER:
        return PromotionDecision(descriptor.id, current, target, False, ["unknown_target"])
    cur_i = PromotionTrack.ORDER.index(current) if current in PromotionTrack.ORDER else 0
    tgt_i = PromotionTrack.ORDER.index(target)
    if tgt_i <= cur_i:
        reasons.append("not_an_upgrade")
    missing = [name for name in GATES if not bool(gates.get(name))]
    if missing:
        reasons.extend(f"gate:{name}" for name in missing)
    if target == PromotionTrack.DEFAULT_ELIGIBLE:
        license_class = str(descriptor.license_class or "unknown").lower()
        if license_class in DEFAULT_BLOCKED_LICENSES:
            reasons.append("license_not_default_eligible")
        if descriptor.experimental:
            reasons.append("still_experimental")
        if benchmark_allowed is not True:
            reasons.append("benchmark_delta_required")
    allowed = not reasons
    return PromotionDecision(
        provider_id=descriptor.id,
        current=current,
        target=target,
        allowed=allowed,
        reasons=reasons,
    )
