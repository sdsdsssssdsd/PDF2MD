"""已删除的兼容层：请改用 app.deepseek_api。"""
from __future__ import annotations

import warnings

warnings.warn(
    "app.vision_api.compatibility 已在 R14 删除；请 from app.deepseek_api 导入",
    DeprecationWarning,
    stacklevel=2,
)

from app.deepseek_api.client import DeepSeekClient, DeepSeekVisionClient
from app.deepseek_api.config import DeepSeekApiConfig, VisionApiConfig

__all__ = [
    "DeepSeekClient",
    "DeepSeekVisionClient",
    "DeepSeekApiConfig",
    "VisionApiConfig",
]
