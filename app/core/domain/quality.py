"""QualityCheckResult / QualityReport：评价独立于 DocumentIR。schema_version=1.0。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"

# 终态唯一优先级（左高右低）。decide_status 必须与此一致且与 check 顺序无关。
VERDICT_PRIORITY: tuple[str, ...] = (
    "FAILED",
    "INCOMPLETE",
    "DONE / WARNINGS",
    "DONE / VERIFIED",
)


class QualityVerdict(str, Enum):
    VERIFIED = "DONE / VERIFIED"
    WARNINGS = "DONE / WARNINGS"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _stable(value[k]) for k in sorted(value, key=lambda x: str(x))}
    if isinstance(value, set):
        items = [_stable(x) for x in value]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, default=str))
    if isinstance(value, tuple):
        return [_stable(x) for x in value]
    if isinstance(value, list):
        return [_stable(x) for x in value]
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass
class QualityCheckResult:
    check_id: str
    scope: str = "document"  # document | page | block
    status: str = CheckStatus.PASS.value
    severity: str = ""
    blocking: bool = False
    score: float | None = None
    threshold: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    affected_ids: list[str] = field(default_factory=list)
    provider: str = "pdf2md.qa"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.severity:
            self.severity = self.status
        self.evidence = _stable(dict(self.evidence or {}))
        self.affected_ids = [str(x) for x in (self.affected_ids or [])]
        self.metadata = _stable(dict(self.metadata or {}))


def make_check(
    check_id: str,
    *,
    status: str,
    scope: str = "document",
    blocking: bool | None = None,
    fatal: bool = False,
    evidence: dict[str, Any] | None = None,
    affected_ids: list[str] | None = None,
    score: float | None = None,
    threshold: float | None = None,
    metadata: dict[str, Any] | None = None,
    provider: str = "pdf2md.qa",
) -> QualityCheckResult:
    """构造契约完整的 QualityCheckResult。fail 默认 blocking；fatal 才升到 FAILED。"""
    if blocking is None:
        blocking = status == CheckStatus.FAIL.value
    meta = dict(metadata or {})
    if fatal:
        meta["fatal"] = True
    return QualityCheckResult(
        check_id=check_id,
        scope=scope,
        status=status,
        severity=status,
        blocking=bool(blocking),
        score=score,
        threshold=threshold,
        evidence=dict(evidence or {}),
        affected_ids=list(affected_ids or []),
        provider=provider,
        metadata=meta,
    )


@dataclass
class QualityReport:
    schema_version: str = SCHEMA_VERSION
    status: str = QualityVerdict.WARNINGS.value
    checks: list[QualityCheckResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    blocking_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evaluator: str = "unified"

    @property
    def verdict(self) -> str:
        return self.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "evaluator": self.evaluator,
            "checks": [asdict(c) for c in self.checks],
            "summary": _stable(dict(self.summary)),
            "blocking_failures": list(self.blocking_failures),
            "warnings": list(self.warnings),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        """Gold / benchmark 用：键排序后的纯 JSON 结构，不含运行时时间戳。"""
        return json.loads(json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, default=str))

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QualityReport:
        checks: list[QualityCheckResult] = []
        for raw in data.get("checks") or []:
            if not isinstance(raw, dict):
                continue
            item = {k: v for k, v in raw.items() if k in QualityCheckResult.__dataclass_fields__}
            if "blocking" not in item:
                item["blocking"] = item.get("status") == CheckStatus.FAIL.value
            checks.append(QualityCheckResult(**item))
        return cls(
            schema_version=str(data.get("schema_version") or SCHEMA_VERSION),
            status=str(data.get("status") or data.get("verdict") or QualityVerdict.WARNINGS.value),
            checks=checks,
            summary=dict(data.get("summary") or {}),
            blocking_failures=list(data.get("blocking_failures") or []),
            warnings=list(data.get("warnings") or data.get("reasons") or []),
            evaluator=str(data.get("evaluator") or "unified"),
        )


def quality_from_markdown(*args: Any, **kwargs: Any) -> QualityReport:
    """兼容入口；实现在 qa.engine，避免与检查器循环导入。"""
    from app.core.qa.engine import quality_from_markdown as _impl

    return _impl(*args, **kwargs)


def _contribution(check: QualityCheckResult) -> str | None:
    if check.status == CheckStatus.SKIP.value:
        return None
    if check.status == CheckStatus.FAIL.value:
        fatal = bool((check.metadata or {}).get("fatal")) or check.check_id == "empty_document"
        if fatal:
            return QualityVerdict.FAILED.value
        if check.blocking:
            return QualityVerdict.INCOMPLETE.value
        return QualityVerdict.WARNINGS.value
    if check.status == CheckStatus.WARN.value:
        return QualityVerdict.WARNINGS.value
    if check.status == CheckStatus.PASS.value:
        return QualityVerdict.VERIFIED.value
    return None


def decide_status(checks: list[QualityCheckResult]) -> str:
    """FAILED > INCOMPLETE > WARNINGS > VERIFIED；与 check 顺序无关。全 skip 视为 WARNINGS。"""
    rank = {name: i for i, name in enumerate(VERDICT_PRIORITY)}
    best: str | None = None
    for check in checks:
        verdict = _contribution(check)
        if verdict is None:
            continue
        if best is None or rank[verdict] < rank[best]:
            best = verdict
    return best or QualityVerdict.WARNINGS.value


def build_report(
    checks: list[QualityCheckResult],
    *,
    evaluator: str = "unified",
    extra_summary: dict[str, Any] | None = None,
) -> QualityReport:
    status = decide_status(checks)
    blocking = [
        c.check_id
        for c in checks
        if c.status == CheckStatus.FAIL.value and c.blocking
    ]
    warnings = [
        c.check_id
        for c in checks
        if c.status in {CheckStatus.WARN.value, CheckStatus.FAIL.value}
    ]
    summary = {
        "pass": sum(1 for c in checks if c.status == CheckStatus.PASS.value),
        "warn": sum(1 for c in checks if c.status == CheckStatus.WARN.value),
        "fail": sum(1 for c in checks if c.status == CheckStatus.FAIL.value),
        "skip": sum(1 for c in checks if c.status == CheckStatus.SKIP.value),
    }
    if extra_summary:
        summary.update(_stable(dict(extra_summary)))
    return QualityReport(
        status=status,
        checks=checks,
        summary=summary,
        blocking_failures=blocking
        if status in {QualityVerdict.FAILED.value, QualityVerdict.INCOMPLETE.value}
        else [],
        warnings=warnings,
        evaluator=evaluator,
    )


def pipeline_failure_report(error: str, *, cancelled: bool = False) -> QualityReport:
    if cancelled:
        return build_report(
            [
                make_check(
                    "pipeline_cancelled",
                    status=CheckStatus.SKIP.value,
                    blocking=False,
                    evidence={"reason": "cancelled"},
                )
            ],
            evaluator="pipeline",
        )
    return build_report(
        [
            make_check(
                "pipeline_failed",
                status=CheckStatus.FAIL.value,
                blocking=True,
                fatal=True,
                evidence={"error": error or "failed"},
            )
        ],
        evaluator="pipeline",
    )
