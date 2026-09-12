"""Correction Core 数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CorrectionConfig:
    """终稿审校配置。mode: off | auto | strict。"""

    mode: str = "auto"
    normalize_math: bool = True
    compact_display_math: bool = True
    text_model: str = "deepseek-v4-flash"
    strict_model: str = "deepseek-v4-pro"
    save_report: bool = True
    vision_verify: bool = True
    vision_model: str = "deepseek-v4-flash-vision-exp"
    batch_size: int = 20
    context_chars: int = 300
    auto_inline_threshold: int = 70
    ambiguous_min_score: int = 40

    @classmethod
    def from_settings(cls, *, mode: str | None = None) -> CorrectionConfig:
        try:
            from app.dialogs.settings_dialog import settings

            s = settings()
            resolved = str(mode or s.value("correction_mode", "auto") or "auto").strip().lower()
            if resolved not in {"off", "auto", "strict"}:
                resolved = "auto"
            text_model = str(
                s.value("correction_text_model", "deepseek-v4-flash") or "deepseek-v4-flash"
            )
            strict_model = str(
                s.value("correction_strict_model", "deepseek-v4-pro") or "deepseek-v4-pro"
            )
            vision_model = str(
                s.value("correction_vision_model", "deepseek-v4-flash-vision-exp")
                or "deepseek-v4-flash-vision-exp"
            )
            return cls(
                mode=resolved,
                normalize_math=bool(s.value("correction_normalize_math", True, type=bool)),
                compact_display_math=bool(
                    s.value("correction_compact_display", True, type=bool)
                ),
                text_model=text_model,
                strict_model=strict_model,
                vision_model=vision_model,
                vision_verify=bool(s.value("correction_vision_verify", True, type=bool)),
                save_report=bool(s.value("correction_save_report", True, type=bool)),
            )
        except Exception:
            return cls(mode=str(mode or "auto"))


@dataclass
class CorrectionContext:
    """可选源上下文（PDF / 截图 / 输出路径）。"""

    pdf_path: Path | None = None
    source_images: list[Path] = field(default_factory=list)
    output_md_path: Path | None = None
    repair_report_path: Path | None = None


@dataclass
class CorrectionIssue:
    issue_id: str
    kind: str
    start: int
    end: int
    before: str
    after: str = ""
    severity: str = "medium"
    left_context: str = ""
    right_context: str = ""
    environment: str = "prose"
    source: str = "detector"
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "before": self.before,
            "after": self.after,
            "severity": self.severity,
            "left_context": self.left_context,
            "right_context": self.right_context,
            "environment": self.environment,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class CorrectionPatch:
    issue_id: str
    before: str
    after: str
    source: str = "local"
    confidence: float = 1.0
    gate: str = "accepted"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "before": self.before,
            "after": self.after,
            "source": self.source,
            "confidence": self.confidence,
            "gate": self.gate,
            "reason": self.reason,
        }


@dataclass
class CorrectionResult:
    input_text: str = ""
    output_text: str = ""
    issues_detected: list[CorrectionIssue] = field(default_factory=list)
    patches_applied: list[CorrectionPatch] = field(default_factory=list)
    patches_rejected: list[CorrectionPatch] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    integrity_ok: bool = True
    api_summary: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.integrity_ok and not self.errors

    def to_report_dict(self) -> dict[str, Any]:
        return {
            "mode": self.stats.get("mode"),
            "model": self.stats.get("model"),
            "detected": len(self.issues_detected),
            "local_fixed": self.stats.get("local_fixed", 0),
            "api_checked": self.stats.get("api_checked", 0),
            "api_applied": self.stats.get("api_applied", 0),
            "vision_verified": self.stats.get("vision_verified", 0),
            "rejected": len(self.patches_rejected),
            "uncertain": self.stats.get("uncertain", 0),
            "patches": [p.to_dict() for p in self.patches_applied[:200]],
            "rejected_patches": [p.to_dict() for p in self.patches_rejected[:100]],
            "warnings": self.warnings[:50],
            "api_summary": self.api_summary,
        }
