"""Formula 数据结构（Phase 2：状态机 + 质量三维）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from app.formula.versions import pipeline_versions


SourceType = Literal["parser_math", "text_suspect", "ocr_math"]
DisplayMode = Literal["inline", "display", "unknown"]


class FormulaLifecycle(str, Enum):
    """debug4.md 状态机。fallback 只能来自 RECOVERY_FAILED。"""

    DETECTED = "detected"
    VALID = "valid"
    CORRUPTED = "corrupted"
    RECOVERY_PENDING = "recovery_pending"
    RECOVERY_SUCCESS = "recovery_success"
    RECOVERY_FAILED = "recovery_failed"


# 兼容旧字面量
FormulaStatus = Literal[
    "detected",
    "recognized",
    "validated",
    "rejected",
    "fallback",
    "valid",
    "corrupted",
    "recovery_pending",
    "recovery_success",
    "recovery_failed",
]


@dataclass
class FormulaQuality:
    syntax_score: float = 1.0  # 1=语法干净
    corruption_score: float = 0.0  # 1=严重失真
    semantic_score: float = 1.0  # 1=与上下文不冲突
    valid: bool = True
    recoverable: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class FormulaCandidate:
    text: str
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    source_type: SourceType = "parser_math"
    display_mode: DisplayMode = "unknown"
    confidence: float | None = None
    raw_text: str | None = None
    status: FormulaStatus = "detected"
    lifecycle: FormulaLifecycle = FormulaLifecycle.DETECTED
    issues: list[str] = field(default_factory=list)
    quality: FormulaQuality | None = None
    start: int | None = None
    end: int | None = None
    context_before: str = ""
    context_after: str = ""
    recovery_attempts: int = 0
    recovery_log: list[dict[str, Any]] = field(default_factory=list)
    # Phase 5D：结构阶段绑定的 Eq.(n)；空表示未解析到
    equation_number: str = ""
    # Phase 6D：编号状态与内容身份解耦
    # numbered_confirmed | unnumbered_confirmed | number_unknown | conflict
    number_status: str = "number_unknown"
    # Phase 7.5：与 %dsid:% 槽位一致的稳定 ID（写回对齐）
    candidate_id: str = ""
    # k3 geometry / QA 归因
    crop_class: str = ""
    geometry_source: str = ""
    failure_stage: str = ""


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str] = field(default_factory=list)
    severity: float = 0.0
    quality: FormulaQuality | None = None


@dataclass
class DetectionHit:
    text: str
    score: float
    start: int
    end: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class DocumentContext:
    pdf_path: str | None = None
    markdown: str = ""
    block_id: str | None = None


@dataclass
class FormulaTelemetry:
    """debug6：分别统计防灾 / 真恢复 / 耗时，不以“去掉大报错”当准确率。"""

    parser_seconds: float = 0.0
    formula_detection_seconds: float = 0.0
    bbox_seconds: float = 0.0
    ocr_load_seconds: float = 0.0
    ocr_inference_seconds: float = 0.0
    ocr_calls: int = 0
    recovery_success: int = 0
    recovery_rejected: int = 0
    recovery_skipped_budget: int = 0
    corruption_suppressed: int = 0
    true_formula_recovery: int = 0
    total_seconds: float = 0.0
    preset: str = "balanced"

    def to_dict(self) -> dict[str, Any]:
        return {
            "parser_seconds": round(self.parser_seconds, 3),
            "formula_detection_seconds": round(self.formula_detection_seconds, 3),
            "bbox_seconds": round(self.bbox_seconds, 3),
            "ocr_load_seconds": round(self.ocr_load_seconds, 3),
            "ocr_inference_seconds": round(self.ocr_inference_seconds, 3),
            "ocr_calls": self.ocr_calls,
            "recovery_success": self.recovery_success,
            "recovery_rejected": self.recovery_rejected,
            "recovery_skipped_budget": self.recovery_skipped_budget,
            "corruption_suppression_count": self.corruption_suppressed,
            "true_formula_recovery_rate_num": self.true_formula_recovery,
            "total_seconds": round(self.total_seconds, 3),
            "preset": self.preset,
        }


@dataclass
class DocumentQuality:
    publishable: bool = True
    formula_failures: int = 0
    reasons: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | formula_incomplete


@dataclass
class FormulaQAReport:
    formula_count: int = 0
    validated: int = 0
    normalized: int = 0
    rejected: int = 0
    fallback: int = 0
    suspected_unwrapped: int = 0
    corrupted_formula_count: int = 0
    recovery_attempted_count: int = 0
    recovery_success_count: int = 0
    recovery_failed_count: int = 0
    formula_failures: list[dict] = field(default_factory=list)
    document_quality: DocumentQuality | None = None
    details: list[dict] = field(default_factory=list)
    telemetry: FormulaTelemetry | None = None
    # Phase 4B Shadow：Scheduler+Executor 旁路结果（不写回 Markdown）
    deepseek_shadow: dict | None = None
    # Phase 4C 写回审计
    writeback: dict | None = None
    # Phase 5H：公式编号身份 QA
    equation_identity: dict | None = None
    # k3 Round-1：几何定位 QA
    geometry_qa: list[dict] | None = None

    def to_dict(self) -> dict:
        return {
            "formula_count": self.formula_count,
            "validated": self.validated,
            "normalized": self.normalized,
            "rejected": self.rejected,
            "fallback": self.fallback,
            "suspected_unwrapped": self.suspected_unwrapped,
            "corrupted_formula_count": self.corrupted_formula_count,
            "recovery_attempted_count": self.recovery_attempted_count,
            "recovery_success_count": self.recovery_success_count,
            "recovery_failed_count": self.recovery_failed_count,
            "formula_failures": self.formula_failures,
            "document_quality": (
                {
                    "publishable": self.document_quality.publishable,
                    "formula_failures": self.document_quality.formula_failures,
                    "reasons": self.document_quality.reasons,
                    "status": self.document_quality.status,
                }
                if self.document_quality
                else None
            ),
            "details": self.details,
            "telemetry": self.telemetry.to_dict() if self.telemetry else None,
            "deepseek_shadow": self.deepseek_shadow,
            "writeback": self.writeback,
            "equation_identity": self.equation_identity,
            "geometry_qa": self.geometry_qa,
            "versions": pipeline_versions(),
        }
