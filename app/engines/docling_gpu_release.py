"""Phase 5E：Docling GPU 资源释放（仅用于 benchmark，默认不自动 empty_cache）。"""
from __future__ import annotations

from typing import Any


def docling_gpu_snapshot() -> dict[str, Any]:
    try:
        import torch

        if not torch.cuda.is_available():
            return {"cuda": False}
        free_b, total_b = torch.cuda.mem_get_info(0)
        return {
            "cuda": True,
            "allocated_mb": round(torch.cuda.memory_allocated(0) / (1024**2), 1),
            "reserved_mb": round(torch.cuda.memory_reserved(0) / (1024**2), 1),
            "free_mb": round(free_b / (1024**2), 1),
            "total_mb": round(total_b / (1024**2), 1),
        }
    except Exception as e:
        return {"cuda": False, "error": str(e)}


def release_docling_gpu(*, empty_cache: bool = False) -> dict[str, Any]:
    """尝试释放本进程 Docling converter 缓存；可选 empty_cache（可能有副作用）。"""
    before = docling_gpu_snapshot()
    notes: list[str] = []
    try:
        from app.engines import docling_engine

        n = len(getattr(docling_engine, "_converter_cache", {}) or {})
        docling_engine._converter_cache.clear()  # noqa: SLF001
        notes.append(f"cleared_converter_cache:{n}")
    except Exception as e:
        notes.append(f"converter_clear_failed:{e}")

    # 尽力删除可能挂在 pipeline 上的 CUDA 模块引用
    try:
        import gc

        gc.collect()
        notes.append("gc_collect")
    except Exception:
        pass

    if empty_cache:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                notes.append("torch.cuda.empty_cache")
        except Exception as e:
            notes.append(f"empty_cache_failed:{e}")

    after = docling_gpu_snapshot()
    return {"before": before, "after": after, "notes": notes, "empty_cache": empty_cache}
