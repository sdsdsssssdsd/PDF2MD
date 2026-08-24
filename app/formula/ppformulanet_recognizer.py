# -*- coding: utf-8 -*-
"""PP-FormulaNet 进程内识别器（仅 .venv-paddle-formula；GUI 环境不要 import）。"""
from __future__ import annotations

from typing import Any

from app.formula.recognizer import FormulaRecognitionResult


class PPFormulaNetRecognizer:
    """PaddleOCR FormulaRecognition → rec_formula。不伪造 confidence。"""

    def __init__(self, model_name: str = "PP-FormulaNet_plus-M") -> None:
        self.model_name = model_name
        self.name = f"pp-formulanet:{model_name}".lower()
        self._model = None

    def _ensure(self) -> Any:
        if self._model is not None:
            return self._model
        from paddleocr import FormulaRecognition  # type: ignore

        self._model = FormulaRecognition(model_name=self.model_name)
        return self._model

    def recognize(
        self,
        image: Any,
        context: dict[str, Any] | None = None,
    ) -> FormulaRecognitionResult:
        del context
        try:
            model = self._ensure()
            result = model.predict(image)
            row = result[0] if isinstance(result, list) and result else result
            if hasattr(row, "get"):
                latex = (row.get("rec_formula") or row.get("latex") or "").strip()
            elif isinstance(row, dict):
                latex = str(row.get("rec_formula") or "").strip()
            else:
                latex = str(getattr(row, "rec_formula", "") or "").strip()
            if not latex:
                return FormulaRecognitionResult(
                    latex=None,
                    confidence=None,
                    recognizer=self.name,
                    success=False,
                    error="empty_rec_formula",
                    issues=["empty_rec_formula"],
                )
            return FormulaRecognitionResult(
                latex=latex,
                confidence=None,
                recognizer=self.name,
                success=True,
                raw=latex,
                meta={"via": "inprocess", "model": self.model_name},
            )
        except Exception as e:
            return FormulaRecognitionResult(
                latex=None,
                confidence=None,
                recognizer=self.name,
                success=False,
                error=f"ppformula_unavailable:{type(e).__name__}",
                issues=["ppformula_unavailable"],
            )
