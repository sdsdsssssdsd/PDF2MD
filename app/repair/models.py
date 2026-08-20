"""Repair 数据模型（为后续 Vision / DeepSeek 预留接口）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class IssueType(str, Enum):
    DECIMAL_SPLIT = "decimal_split"
    SUSPICIOUS_SUBSCRIPT = "suspicious_subscript"
    DETACHED_SCRIPT = "detached_script"
    HAT_CORRUPTION = "hat_corruption"
    SPLIT_MATH_WORD = "split_math_word"
    PROSE_IN_MATH = "prose_in_math"
    MALFORMED_DELIMITER = "malformed_delimiter"
    DISPLAY_CONTAMINATION = "display_contamination"
    FORMULA_NOT_DECODED = "formula_not_decoded"
    UNICODE_MATH = "unicode_math"
    OTHER = "other"


class RepairAction(str, Enum):
    KEEP = "keep"
    REPLACE = "replace"
    UNCERTAIN = "uncertain"


@dataclass
class RepairConfig:
    """修复管线配置。当前：safe + 保守几何。"""

    enabled: bool = True
    # safe | smart | strong —— 后续接 olmOCR / DeepSeek
    mode: str = "safe"
    keep_formulas: bool = True
    fix_bold: bool = True
    write_raw_md: bool = True
    write_repair_json: bool = True
    use_geometry: bool = True  # O-024：safe 后保守几何；可关
    use_vision: bool = False
    use_reasoning: bool = False


@dataclass
class RepairIssue:
    type: IssueType
    severity: float
    message: str = ""
    paragraph: int | None = None
    start: int | None = None
    end: int | None = None
    original: str | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    evidence: list[str] = field(default_factory=list)


@dataclass
class RepairEvidence:
    original_markdown: str
    pdf_native_text: str | None = None
    geometry_candidate: str | None = None
    vision_candidate: str | None = None
    previous_context: str | None = None
    next_context: str | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class RepairDecision:
    action: RepairAction
    target: str | None = None
    replacement: str | None = None
    confidence: float = 1.0
    issue_type: str | None = None
    method: str = "safe"


@dataclass
class RepairResult:
    markdown_path: Path
    raw_markdown_path: Path | None = None
    report_path: Path | None = None
    issues_detected: int = 0
    issues_repaired: int = 0
    methods: dict[str, int] = field(default_factory=dict)
    quality_before: float | None = None
    quality_after: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class VisionProvider(Protocol):
    def transcribe(self, image_path: Path, task: str) -> str: ...


class ReasoningProvider(Protocol):
    def reconcile(self, evidence: RepairEvidence) -> RepairDecision: ...
