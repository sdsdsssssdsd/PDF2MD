"""上传/站点限流冷却。不在 Adapter 里吞异常后换下一种抽取。"""
from __future__ import annotations

from app.vision_transcribe.browser.base import (
    ServerBusyCooldownError,
    server_busy_from_response,
)

__all__ = ["ServerBusyCooldownError", "server_busy_from_response"]
