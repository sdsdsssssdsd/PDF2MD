"""FormulaRecognitionResult + Recognizer Protocol / Factory（debug5：专用 OCR，不接 VLM）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.formula.config import FormulaConfig


@dataclass
class FormulaRecognitionResult:
    latex: str | None
    confidence: float | None = None
    recognizer: str = "null"
    success: bool = False
    error: str | None = None
    raw: str | None = None
    issues: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class FormulaRecognizer(Protocol):
    name: str

    def recognize(
        self,
        image: Any,
        context: dict[str, Any] | None = None,
    ) -> FormulaRecognitionResult:
        """专用公式 OCR 必须忽略 context（禁止根据 Recall 等语义猜写）。"""
        ...


class NullFormulaRecognizer:
    """无可用 OCR 时的占位。"""

    name = "null"

    def __init__(self, error: str = "recovery_disabled") -> None:
        self._error = error

    def recognize(
        self,
        image: Any,
        context: dict[str, Any] | None = None,
    ) -> FormulaRecognitionResult:
        del image, context
        return FormulaRecognitionResult(
            latex=None,
            confidence=None,
            recognizer=self.name,
            success=False,
            error=self._error,
            issues=[self._error],
        )


def build_recognizer(cfg: FormulaConfig | None = None) -> FormulaRecognizer:
    """按配置构建主识别器。默认 UniMERNet（GPU）；VLM 不进主链路。"""
    cfg = cfg or FormulaConfig()
    primary = (cfg.recognizer_primary or "unimernet").lower().strip()

    if primary in {"null", "none", "off"}:
        return NullFormulaRecognizer("recognizer_disabled")

    if primary in {"unimernet", "unimer", "mfr", "mineru_mfr"}:
        try:
            from app.formula.unimernet_recognizer import UniMERNetRecognizer

            return UniMERNetRecognizer()
        except Exception as e:
            # 显式要求 unimernet 时不再静默退回 pix2tex，避免质量预期错位
            return NullFormulaRecognizer(f"unimernet_unavailable:{type(e).__name__}")

    if primary in {"pix2tex", "latexocr", "latex-ocr"}:
        try:
            from app.formula.pix2tex_recognizer import Pix2TexRecognizer

            return Pix2TexRecognizer()
        except Exception as e:
            return NullFormulaRecognizer(f"pix2tex_unavailable:{type(e).__name__}")

    from app.formula.backends import is_paddle_vl, is_pp_formulanet, paddle_model_name

    if is_pp_formulanet(primary) or is_paddle_vl(primary):
        model = paddle_model_name(primary)
        try:
            from app.formula.ppformula_worker_recognizer import PPFormulaWorkerRecognizer

            rec = PPFormulaWorkerRecognizer(model_name=model)
            if rec.worker_reachable():
                return rec
        except Exception as e:
            return NullFormulaRecognizer(f"ppformula_worker_error:{type(e).__name__}")
        return NullFormulaRecognizer("ppformula_worker_unavailable")

    return NullFormulaRecognizer(f"unknown_recognizer:{primary}")
