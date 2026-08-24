"""UniMERNet（MinerU MFR）专用公式识别：忽略 context，优先 CUDA。"""
from __future__ import annotations

import os
from typing import Any

import numpy as np

from app.formula.preprocess import to_pil_image
from app.formula.recognizer import FormulaRecognitionResult


def _resolve_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass
    return "cpu"


def _resolve_weight_dir() -> str:
    """解析本机已缓存的 UniMERNet small 权重目录。"""
    from mineru.utils.enum_class import ModelPath
    from mineru.utils.models_download_utils import auto_download_and_get_model_root_path

    rel = ModelPath.unimernet_small
    root = auto_download_and_get_model_root_path(rel)
    weight_dir = os.path.join(str(root), rel)
    if not os.path.isdir(weight_dir):
        # 个别缓存布局已直接指向模型根
        if os.path.isfile(os.path.join(str(root), "config.json")):
            return str(root)
        raise FileNotFoundError(f"unimernet_weights_missing:{weight_dir}")
    return weight_dir


class UniMERNetRecognizer:
    """懒加载 MinerU UnimernetModel；有 CUDA 则 float16 上 GPU。"""

    name = "unimernet"

    def __init__(self, device: str | None = None) -> None:
        self._model = None
        self._load_error: str | None = None
        self._device = device or _resolve_device()

    def _ensure_model(self) -> None:
        if self._model is not None or self._load_error:
            return
        os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("USE_TORCH", "1")
        try:
            from mineru.model.mfr.unimernet.Unimernet import UnimernetModel
        except Exception as e:
            self._load_error = f"import_failed:{type(e).__name__}:{e}"
            return
        try:
            weight_dir = _resolve_weight_dir()
            self._model = UnimernetModel(weight_dir, self._device)
            self._device = str(getattr(self._model, "device", self._device))
        except Exception as e:
            self._load_error = f"init_failed:{type(e).__name__}:{e}"
            self._model = None

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
                recognizer=self.name,
                success=False,
                error=self._load_error,
                issues=["unimernet_unavailable"],
            )
        try:
            self._ensure_model()
            if self._model is None:
                return FormulaRecognitionResult(
                    latex=None,
                    recognizer=self.name,
                    success=False,
                    error=self._load_error or "unimernet_unavailable",
                    issues=["unimernet_unavailable"],
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
            arr = np.asarray(pil.convert("RGB"))
            if arr.ndim != 3 or arr.shape[0] < 2 or arr.shape[1] < 2:
                return FormulaRecognitionResult(
                    latex=None,
                    recognizer=self.name,
                    success=False,
                    error="bad_image_shape",
                    issues=["bad_image"],
                )
            h, w = int(arr.shape[0]), int(arr.shape[1])
            # 已是公式裁图：整图当作一条 display_formula
            mfd = [
                {
                    "bbox": [0, 0, w, h],
                    "score": 1.0,
                    "label": "display_formula",
                }
            ]
            out = self._model.predict(mfd, arr, batch_size=1)
            latex = None
            if out and isinstance(out, list) and out[0]:
                item = out[0]
                if isinstance(item, dict):
                    latex = item.get("latex")
                elif isinstance(item, str):
                    latex = item
            text = (str(latex).strip() if latex is not None else "") or None
            if not text:
                return FormulaRecognitionResult(
                    latex=None,
                    recognizer=self.name,
                    success=False,
                    error="empty_output",
                    issues=["empty_output"],
                )
            if text.startswith("$$") and text.endswith("$$"):
                text = text[2:-2].strip()
            elif text.startswith("$") and text.endswith("$"):
                text = text[1:-1].strip()
            return FormulaRecognitionResult(
                latex=text,
                confidence=None,
                recognizer=self.name,
                success=True,
                raw=text,
                meta={
                    "ignored_context": True,
                    "device": self._device,
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
