"""DeepSeek 文档级预检（一次；结果可缓存到进程）。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.ocr.deepseek_paths import (
    DEEPSEEK_MODEL_DIR,
    DSOCR2_PYTHON,
    resolve_deepseek_model_name,
)

_CACHED: "DeepSeekHealthReport | None" = None


@dataclass
class DeepSeekHealthReport:
    ok: bool
    reason: str = ""
    cuda: bool = False
    transformers_version: str = ""
    model_path_ok: bool = False
    dsocr2_python_ok: bool = False
    detail: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def reset_health_cache() -> None:
    global _CACHED
    _CACHED = None


def deepseek_health_check(*, force: bool = False) -> DeepSeekHealthReport:
    global _CACHED
    if _CACHED is not None and not force:
        return _CACHED

    detail: dict[str, Any] = {}
    cuda = False
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
        if cuda:
            detail["gpu"] = torch.cuda.get_device_name(0)
            detail["vram_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024**3), 2
            )
    except Exception as e:
        _CACHED = DeepSeekHealthReport(ok=False, reason=f"torch:{e}", detail=detail)
        return _CACHED

    if not cuda:
        _CACHED = DeepSeekHealthReport(ok=False, reason="cuda_unavailable", detail=detail)
        return _CACHED

    tf_ver = ""
    try:
        import transformers

        tf_ver = str(getattr(transformers, "__version__", "") or "")
    except Exception:
        tf_ver = ""

    model_ok = DEEPSEEK_MODEL_DIR.is_dir() or bool(resolve_deepseek_model_name())
    ds_ok = DSOCR2_PYTHON.is_file()

    # 主进程 transformers 常为 4.57；只要 dsocr2 子进程可用即放行
    if ds_ok:
        _CACHED = DeepSeekHealthReport(
            ok=True,
            reason="dsocr2_subprocess_ready",
            cuda=cuda,
            transformers_version=tf_ver,
            model_path_ok=model_ok,
            dsocr2_python_ok=True,
            detail=detail,
        )
        return _CACHED

    # 无子进程则要求本机 4.46.x
    parts = tf_ver.split(".")
    compat = False
    try:
        compat = int(parts[0]) == 4 and int(parts[1]) == 46
    except (TypeError, ValueError, IndexError):
        compat = False
    if not compat:
        _CACHED = DeepSeekHealthReport(
            ok=False,
            reason=f"transformers_incompatible:{tf_ver or 'missing'}",
            cuda=cuda,
            transformers_version=tf_ver,
            model_path_ok=model_ok,
            dsocr2_python_ok=False,
            detail=detail,
        )
        return _CACHED

    if not model_ok:
        _CACHED = DeepSeekHealthReport(
            ok=False,
            reason="model_path_missing",
            cuda=cuda,
            transformers_version=tf_ver,
            model_path_ok=False,
            dsocr2_python_ok=False,
            detail=detail,
        )
        return _CACHED

    _CACHED = DeepSeekHealthReport(
        ok=True,
        reason="inprocess_ready",
        cuda=cuda,
        transformers_version=tf_ver,
        model_path_ok=True,
        dsocr2_python_ok=False,
        detail=detail,
    )
    return _CACHED
