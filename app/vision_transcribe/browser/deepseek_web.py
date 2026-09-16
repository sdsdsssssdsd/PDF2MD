"""兼容入口：DeepSeek Web Adapter 已拆到 adapter / session / capture / policies。"""
from __future__ import annotations

from app.vision_transcribe.browser.adapter.deepseek import DeepSeekPlaywrightAdapter
from app.vision_transcribe.browser.base import (
    AdapterResult,
    NeedsUserError,
    VisionWebAdapter,
)
from app.vision_transcribe.browser.contracts.fingerprint import (
    DEEPSEEK_SITE_ADAPTER,
    IncompatibleSiteError,
    SiteAdapterVersion,
)

__all__ = [
    "AdapterResult",
    "DEEPSEEK_SITE_ADAPTER",
    "DeepSeekPlaywrightAdapter",
    "IncompatibleSiteError",
    "NeedsUserError",
    "SiteAdapterVersion",
    "VisionWebAdapter",
]
