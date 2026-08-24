"""浏览器 Adapter 包。"""
from __future__ import annotations

from app.vision_transcribe.browser.base import VisionWebAdapter, AdapterResult, NeedsUserError
from app.vision_transcribe.browser.manual_clipboard import ManualClipboardAdapter

__all__ = [
    "VisionWebAdapter",
    "AdapterResult",
    "NeedsUserError",
    "ManualClipboardAdapter",
]


def create_adapter(mode: str, **kwargs):
    mode = (mode or "clipboard").lower()
    if mode in ("playwright", "deepseek", "auto"):
        # GUI 默认走子进程客户端，避免 Qt 线程内 sync Playwright 卡死界面
        from app.vision_transcribe.browser.playwright_session_client import (
            PlaywrightSessionClient,
        )

        allowed = {"profile_dir", "url", "python_exe", "log"}
        kw = {k: v for k, v in kwargs.items() if k in allowed}
        # deepseek_web 用 url= ，客户端也用 url=
        if "url" not in kw and "deepseek_url" in kwargs:
            kw["url"] = kwargs["deepseek_url"]
        return PlaywrightSessionClient(**kw)
    return ManualClipboardAdapter()
