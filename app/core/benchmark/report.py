"""BenchmarkReport：工程决策用，不是生产 Unified QA。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"

METRIC_KEYS: tuple[str, ...] = (
    "quality",
    "formula",
    "table",
    "reading_order",
    "text",
    "page_coverage",
    "recovery_yield",
    "false_recovery_rate",
    "latency_p50",
    "latency_p95",
    "peak_vram",
    "peak_ram",
    "model_load_time",
    "api_calls",
    "tokens",
    "estimated_cost",
    "retry_rate",
    "failure_rate",
)


@dataclass
class BenchmarkReport:
    schema_version: str = SCHEMA_VERSION
    suite: str = "gold_v2"
    created_at: str = ""
    cases: int = 0
    passed: int = 0
    slices: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, float | None] = field(default_factory=dict)
    adapter: str = "gold_v2"
    skipped: bool = False
    skip_reason: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        merged = {k: None for k in METRIC_KEYS}
        merged.update(self.metrics or {})
        self.metrics = merged
        if "overall" not in self.slices and self.cases:
            self.slices = {"overall": self.passed / self.cases, **dict(self.slices)}

    @property
    def overall(self) -> float | None:
        if "overall" in self.slices:
            return float(self.slices["overall"])
        if self.cases:
            return self.passed / self.cases
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite": self.suite,
            "created_at": self.created_at,
            "cases": self.cases,
            "passed": self.passed,
            "slices": {k: float(v) for k, v in sorted(self.slices.items())},
            "metrics": {k: self.metrics.get(k) for k in METRIC_KEYS},
            "adapter": self.adapter,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "extras": dict(self.extras),
        }

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkReport:
        metrics = dict(data.get("metrics") or {})
        return cls(
            schema_version=str(data.get("schema_version") or SCHEMA_VERSION),
            suite=str(data.get("suite") or "gold_v2"),
            created_at=str(data.get("created_at") or ""),
            cases=int(data.get("cases") or 0),
            passed=int(data.get("passed") or 0),
            slices={str(k): float(v) for k, v in dict(data.get("slices") or {}).items()},
            metrics=metrics,
            adapter=str(data.get("adapter") or "gold_v2"),
            skipped=bool(data.get("skipped")),
            skip_reason=str(data.get("skip_reason") or ""),
            extras=dict(data.get("extras") or {}),
        )

    @classmethod
    def load(cls, path: Path) -> BenchmarkReport:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


def skipped_report(adapter: str, reason: str) -> BenchmarkReport:
    return BenchmarkReport(
        suite=adapter,
        adapter=adapter,
        skipped=True,
        skip_reason=reason,
        slices={"overall": 0.0},
        extras={"ci_policy": "nightly_or_manual"},
    )
