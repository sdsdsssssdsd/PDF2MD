"""格式修正模式的数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RepairConfig:
    review_model: str = "fast"  # fast | strict
    generate_report: bool = False
    normalize_math: bool = True
    compact_display_math: bool = True
    auto_inline_threshold: int = 70
    ambiguous_min_score: int = 40


@dataclass
class FormatIssue:
    id: str
    kind: str
    start: int
    end: int
    original: str = ""
    replacement: str = ""
    reason: str = ""
    confidence: float = 1.0
    source: str = "local_rule"


@dataclass
class RepairEdit:
    kind: str
    before: str
    after: str
    reason: str
    source: str = "deepseek"
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class FileSnapshot:
    path: Path | None = None
    encoding: str = "utf-8"
    newline: str = "\n"
    bom: str = ""
    mtime_ns: int | None = None


@dataclass
class FormatRepairResult:
    input_text: str = ""
    output_text: str = ""
    edits: list[RepairEdit] = field(default_factory=list)
    rejected_edits: list[RepairEdit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    integrity_ok: bool = True
    snapshot: FileSnapshot = field(default_factory=FileSnapshot)
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.integrity_ok and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "edits": [e.to_dict() for e in self.edits],
            "warnings": self.warnings,
            "errors": self.errors,
            "report": self.report,
        }
