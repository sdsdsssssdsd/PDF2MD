"""Benchmark delta：没有正向/可接受 delta，就不能改默认 Provider / Router。"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.benchmark.report import BenchmarkReport


@dataclass
class SliceDelta:
    name: str
    baseline: float
    candidate: float
    delta: float
    cases_hint: str = ""


@dataclass
class BenchmarkDelta:
    slices: dict[str, SliceDelta] = field(default_factory=dict)
    baseline_cases: int = 0
    candidate_cases: int = 0
    allowed: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "baseline_cases": self.baseline_cases,
            "candidate_cases": self.candidate_cases,
            "slices": {
                name: {
                    "baseline": item.baseline,
                    "candidate": item.candidate,
                    "delta": item.delta,
                }
                for name, item in self.slices.items()
            },
        }


def compare_reports(baseline: BenchmarkReport, candidate: BenchmarkReport) -> BenchmarkDelta:
    names = sorted(set(baseline.slices) | set(candidate.slices) | {"overall"})
    slices: dict[str, SliceDelta] = {}
    for name in names:
        b = float(baseline.slices.get(name, 0.0) if name in baseline.slices else 0.0)
        c = float(candidate.slices.get(name, 0.0) if name in candidate.slices else 0.0)
        if name not in baseline.slices and name not in candidate.slices and name != "overall":
            continue
        if name == "overall":
            b = float(baseline.overall or 0.0)
            c = float(candidate.overall or 0.0)
        slices[name] = SliceDelta(name=name, baseline=b, candidate=c, delta=c - b)
    delta = BenchmarkDelta(
        slices=slices,
        baseline_cases=baseline.cases,
        candidate_cases=candidate.cases,
    )
    allowed, reason = default_change_allowed(delta)
    delta.allowed = allowed
    delta.reason = reason
    return delta


def default_change_allowed(
    delta: BenchmarkDelta,
    *,
    min_cases: int = 1,
    max_overall_regression: float = 0.0,
    max_slice_regression: float = 0.05,
) -> tuple[bool, str]:
    """默认 Provider / Router 变更门：缺 delta 或整体回退则拒绝。"""
    if delta.baseline_cases < min_cases or delta.candidate_cases < min_cases:
        return False, "insufficient_cases"
    overall = delta.slices.get("overall")
    if overall is None:
        return False, "missing_overall"
    if overall.delta < -abs(max_overall_regression):
        return False, "overall_regression"
    for name, item in delta.slices.items():
        if name == "overall" or name.startswith("suite:"):
            continue
        if item.delta < -abs(max_slice_regression):
            return False, f"slice_regression:{name}"
    return True, "ok"
