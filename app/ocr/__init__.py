"""Document-level OCR（DeepSeek-OCR 2 等）— 与 FormulaRecognizer 分离。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class OCRMode(str, Enum):
    FORMULA = "formula"
    REGION = "region"
    PAGE = "page"


@dataclass
class DocumentOCRResult:
    raw_output: str
    markdown: str | None
    recognizer: str
    mode: str
    elapsed_seconds: float
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.markdown or self.raw_output or ""


class DeepSeekOCRUnavailable(RuntimeError):
    """模型不可用 / 强烈建议 GPU 时在 CPU 上拒绝跑。"""

    def __init__(self, reason: str, *, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        msg = reason if not detail else f"{reason}: {detail}"
        super().__init__(msg)


class DocumentOCRRecognizer(Protocol):
    name: str

    def recognize(
        self,
        image: Any,
        *,
        mode: OCRMode = OCRMode.PAGE,
        prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> DocumentOCRResult:
        ...


# 官方默认：带版面 grounding 的文档 → Markdown
PROMPT_DOCUMENT = "<image>\n<|grounding|>Convert the document to markdown."
# Benchmark 可选；不要作为生产默认
PROMPT_FREE_OCR = "<image>\nFree OCR."
# k4 A/B：单公式 crop → LaTeX（仅实验，不写入生产 Lean 路径）
PROMPT_FORMULA_LATEX = (
    "<image>\n"
    "Convert this cropped mathematical formula to LaTeX.\n"
    "Output LaTeX only. Do not output Markdown fences, explanations, or equation numbers."
)
