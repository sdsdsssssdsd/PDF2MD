"""兼容占位：实际转换统一由 ConversionWorker 调度。"""
from app.workers.docling_worker import ConversionWorker

__all__ = ["ConversionWorker"]
