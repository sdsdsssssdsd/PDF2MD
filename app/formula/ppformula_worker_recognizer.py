# -*- coding: utf-8 -*-
"""GUI 进程适配器：公式 OCR 走独立 Paddle Worker，本进程不 import paddle。"""
from __future__ import annotations

import base64
import io
from typing import Any

from app.formula.ppformula_worker_client import (
    PPFormulaWorkerClient,
    get_ppformula_worker_client,
)
from app.formula.recognizer import FormulaRecognitionResult


class PPFormulaWorkerRecognizer:
    name = "pp-formulanet-worker"

    def __init__(
        self,
        model_name: str = "PP-FormulaNet_plus-M",
        client: PPFormulaWorkerClient | None = None,
    ) -> None:
        self.model_name = model_name
        self.client = client or get_ppformula_worker_client()
        self.name = f"pp-formulanet-worker:{model_name}"

    def worker_reachable(self) -> bool:
        return bool(self.client.ping())

    def recognize(
        self,
        image: Any,
        context: dict[str, Any] | None = None,
    ) -> FormulaRecognitionResult:
        del context
        try:
            from PIL import Image

            if isinstance(image, Image.Image):
                im = image
            elif hasattr(image, "save"):
                im = image
            else:
                im = Image.fromarray(image)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as e:
            return FormulaRecognitionResult(
                latex=None,
                confidence=None,
                recognizer=self.name,
                success=False,
                error=f"image_encode_failed:{e}",
                issues=["image_encode_failed"],
            )

        r = self.client.recognize(image_b64=b64, model_name=self.model_name)
        latex = (r.get("rec_formula") or r.get("latex") or "").strip() or None
        ok = bool(r.get("ok") and latex)
        return FormulaRecognitionResult(
            latex=latex,
            confidence=None,
            recognizer=self.name,
            success=ok,
            error=None if ok else str(r.get("error") or "paddle_recognize_failed"),
            raw=str(r.get("raw") or latex or ""),
            issues=[] if ok else [str(r.get("error") or "paddle_recognize_failed")],
            meta={"via": "paddle_worker", "model": self.model_name},
        )
