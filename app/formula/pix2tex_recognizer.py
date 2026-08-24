"""Pix2Tex / LaTeX-OCR 专用公式识别（忽略 context，不做语义猜写）。"""
from __future__ import annotations

from typing import Any

from app.formula.preprocess import to_pil_image
from app.formula.recognizer import FormulaRecognitionResult


class Pix2TexRecognizer:
    """真正懒加载 LatexOCR（首次 recognize 才加载，避免 GUI 卡住）。"""

    name = "pix2tex"

    def __init__(self) -> None:
        self._model = None
        self._load_error: str | None = None
        self._device: str | None = None
        # 不在 __init__ 里加载模型 —— 否则转换一开始就像死机

    def _ensure_model(self) -> None:
        if self._model is not None or self._load_error:
            return
        try:
            from pix2tex.cli import LatexOCR  # type: ignore
        except Exception as e:
            self._load_error = f"import_failed:{type(e).__name__}:{e}"
            return
        try:
            # LatexOCR() 无参时库内默认 no_cuda=True（强制 CPU）！
            # 有 CUDA 时必须显式 no_cuda=False，否则单次推理可到 20～30s。
            from munch import Munch  # type: ignore

            import torch

            use_cuda = bool(torch.cuda.is_available())
            args = Munch(
                {
                    "config": "settings/config.yaml",
                    "checkpoint": "checkpoints/weights.pth",
                    "no_cuda": not use_cuda,
                    "no_resize": False,
                }
            )
            self._model = LatexOCR(arguments=args)
            self._device = "cuda" if use_cuda else "cpu"
        except Exception as e:
            self._load_error = f"init_failed:{type(e).__name__}:{e}"
            self._model = None
            self._device = None

    def recognize(
        self,
        image: Any,
        context: dict[str, Any] | None = None,
    ) -> FormulaRecognitionResult:
        # 硬规则：专用 OCR 不得读取 context 猜写公式
        del context
        if self._load_error and self._model is None:
            return FormulaRecognitionResult(
                latex=None,
                confidence=None,
                recognizer=self.name,
                success=False,
                error=self._load_error,
                issues=["pix2tex_unavailable"],
            )
        try:
            self._ensure_model()
            if self._model is None:
                return FormulaRecognitionResult(
                    latex=None,
                    confidence=None,
                    recognizer=self.name,
                    success=False,
                    error=self._load_error or "pix2tex_unavailable",
                    issues=["pix2tex_unavailable"],
                )
            pil = to_pil_image(image)
            if pil is None:
                return FormulaRecognitionResult(
                    latex=None,
                    recognizer=self.name,
                    success=False,
                    error="bad_image",
                    issues=["bad_image"],
                )
            latex = self._model(pil)
            if isinstance(latex, (list, tuple)):
                latex = latex[0] if latex else None
            text = (str(latex).strip() if latex is not None else "") or None
            if not text:
                return FormulaRecognitionResult(
                    latex=None,
                    recognizer=self.name,
                    success=False,
                    error="empty_output",
                    issues=["empty_output"],
                )
            # 去掉 $$ 外壳（若模型带了）
            if text.startswith("$$") and text.endswith("$$"):
                text = text[2:-2].strip()
            elif text.startswith("$") and text.endswith("$"):
                text = text[1:-1].strip()
            return FormulaRecognitionResult(
                latex=text,
                confidence=None,  # pix2tex 通常无可靠 confidence；不以置信度决策
                recognizer=self.name,
                success=True,
                raw=text,
                meta={
                    "ignored_context": True,
                    "device": self._device or "unknown",
                },
            )
        except Exception as e:
            return FormulaRecognitionResult(
                latex=None,
                recognizer=self.name,
                success=False,
                error=f"{type(e).__name__}:{e}",
                issues=["recognize_exception"],
            )
