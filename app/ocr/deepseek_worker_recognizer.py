"""Worker 后端的 DeepSeek Recognizer 适配器（主进程用，无本地 transformers DeepSeek）。"""
from __future__ import annotations

import base64
import io
import time
from typing import Any

from app.ocr import DocumentOCRResult, OCRMode
from app.ocr.deepseek_worker_client import DeepSeekWorkerClient, get_deepseek_worker_client


class WorkerBackedDeepSeekRecognizer:
    """与 DeepSeekOCR2Recognizer 同接口；OCR 走持久 Worker。"""

    name = "deepseek-ocr-2-worker"
    _load_count: int = 0

    def __init__(self, client: DeepSeekWorkerClient | None = None) -> None:
        self.client = client or get_deepseek_worker_client()

    @classmethod
    def model_load_count(cls) -> int:
        return int(cls._load_count)

    @classmethod
    def reset_class_model(cls) -> None:
        cls._load_count = 0

    def _ensure_model(self) -> None:
        """兼容 FormulaPipeline 预热钩子。"""
        r = self.client.load()
        if r.get("ok") and float(r.get("load_this_call") or 0) > 0.5:
            WorkerBackedDeepSeekRecognizer._load_count += 1

    def on_inference_timeout(self) -> None:
        """Executor 线程超时兜底：强制 kill + restart（不可复用卡死进程）。"""
        self.client.on_inference_timeout()

    def recognize(
        self,
        image: Any,
        *,
        mode: OCRMode | str = OCRMode.FORMULA,
        prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> DocumentOCRResult:
        inject = None
        if isinstance(context, dict):
            inject = context.get("inject_fault")
        mode_s = mode.value if isinstance(mode, OCRMode) else str(mode)
        t0 = time.perf_counter()
        try:
            from PIL import Image

            if not isinstance(image, Image.Image):
                # numpy / path
                if hasattr(image, "save"):
                    im = image
                else:
                    im = Image.fromarray(image)
            else:
                im = image
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as e:
            return DocumentOCRResult(
                raw_output="",
                markdown=None,
                recognizer=self.name,
                mode=mode_s,
                elapsed_seconds=time.perf_counter() - t0,
                success=False,
                error=f"image_encode_failed:{e}",
            )

        # 冷加载：load 可能嵌在 recognize 里；client 会把 load+infer 超时合并
        health = self.client.health()
        was_loaded = bool(health.get("model_loaded"))
        r = self.client.recognize(
            image_b64=b64, mode=mode_s, prompt=prompt, inject_fault=inject
        )
        if not was_loaded and r.get("metadata", {}).get("model_load_seconds"):
            WorkerBackedDeepSeekRecognizer._load_count = max(
                WorkerBackedDeepSeekRecognizer._load_count,
                int(r.get("metadata", {}).get("worker_load_count") or 1),
            )
        elif not was_loaded and r.get("ok"):
            WorkerBackedDeepSeekRecognizer._load_count = max(
                1, WorkerBackedDeepSeekRecognizer._load_count
            )

        meta = dict(r.get("metadata") or {})
        meta["via"] = "persistent_worker"
        if r.get("worker_restarted") is not None:
            meta["worker_restarted"] = bool(r.get("worker_restarted"))
        if r.get("lifecycle"):
            meta["lifecycle"] = r.get("lifecycle")
        return DocumentOCRResult(
            raw_output=str(r.get("raw_output") or r.get("text") or ""),
            markdown=r.get("markdown"),
            recognizer=self.name,
            mode=str(r.get("mode") or mode_s),
            elapsed_seconds=float(r.get("elapsed_seconds") or (time.perf_counter() - t0)),
            success=bool(r.get("success") or r.get("ok")),
            error=r.get("error"),
            metadata=meta,
        )
