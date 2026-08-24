"""DeepSeek / OCR 错误分类与文档级熔断（Phase 5B-Perf）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OcrFailureClass(str, Enum):
    OK = "ok"
    OCR_RESULT_BAD = "ocr_result_bad"
    OCR_TIMEOUT = "ocr_timeout"
    OCR_RUNTIME_ERROR = "ocr_runtime_error"
    OCR_OOM = "ocr_oom"
    MODEL_LOAD_ERROR = "model_load_error"
    CUDA_ERROR = "cuda_error"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    UNKNOWN = "unknown"


BACKEND_TRIP_CLASSES = frozenset(
    {
        OcrFailureClass.OCR_RUNTIME_ERROR,
        OcrFailureClass.OCR_OOM,
        OcrFailureClass.MODEL_LOAD_ERROR,
        OcrFailureClass.CUDA_ERROR,
        OcrFailureClass.BACKEND_UNAVAILABLE,
        # 注意：OCR_TIMEOUT 不熔断——冷加载/偶发慢推理 ≠ 后端死亡
    }
)


def classify_ocr_failure(error: str | None, *, success: bool = False) -> OcrFailureClass:
    if success and not error:
        return OcrFailureClass.OK
    err = (error or "").lower()
    if not err and not success:
        return OcrFailureClass.OCR_RESULT_BAD
    if "oom" in err or "out of memory" in err:
        return OcrFailureClass.OCR_OOM
    if "timeout" in err or "timed out" in err:
        return OcrFailureClass.OCR_TIMEOUT
    if "cuda" in err or "cublas" in err or "cudnn" in err:
        return OcrFailureClass.CUDA_ERROR
    if "load" in err and ("model" in err or "weight" in err):
        return OcrFailureClass.MODEL_LOAD_ERROR
    if "runtimeerror" in err or "runtime error" in err:
        return OcrFailureClass.OCR_RUNTIME_ERROR
    if "ocr_failed" in err and "runtime" in err:
        return OcrFailureClass.OCR_RUNTIME_ERROR
    if "unavailable" in err or "backend" in err:
        return OcrFailureClass.BACKEND_UNAVAILABLE
    if not success or error:
        # 普通识别失败（无式、空结果）≠ 后端挂了
        if any(x in err for x in ("formula_not_found", "empty", "no_equation", "gate")):
            return OcrFailureClass.OCR_RESULT_BAD
        if "ocr_failed" in err and "runtime" in err:
            return OcrFailureClass.OCR_RUNTIME_ERROR
        return OcrFailureClass.OCR_RESULT_BAD
    return OcrFailureClass.UNKNOWN


@dataclass
class CircuitBreaker:
    """文档/会话级熔断：后端异常后禁止继续烧 DeepSeek。"""

    tripped: bool = False
    reason: str = ""
    failure_class: str = ""
    trip_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def trip(self, failure_class: OcrFailureClass | str, detail: str = "") -> None:
        fc = (
            failure_class.value
            if isinstance(failure_class, OcrFailureClass)
            else str(failure_class)
        )
        self.tripped = True
        self.reason = detail or fc
        self.failure_class = fc
        self.trip_count += 1
        self.events.append({"failure_class": fc, "detail": detail})

    def observe_error(self, error: str | None, *, success: bool = False) -> OcrFailureClass:
        cls = classify_ocr_failure(error, success=success)
        if cls in BACKEND_TRIP_CLASSES:
            self.trip(cls, error or cls.value)
        return cls

    def to_dict(self) -> dict[str, Any]:
        return {
            "tripped": self.tripped,
            "reason": self.reason,
            "failure_class": self.failure_class,
            "trip_count": self.trip_count,
            "events": list(self.events),
        }
