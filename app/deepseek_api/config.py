"""DeepSeek 公共配置别名。"""
from app.vision_api.config import (
    DEFAULT_STRICT_TEXT_MODEL,
    DEFAULT_TEXT_MODEL,
    DEFAULT_VISION_MODEL,
    VisionApiConfig,
)

DeepSeekApiConfig = VisionApiConfig

__all__ = [
    "DeepSeekApiConfig",
    "DEFAULT_TEXT_MODEL",
    "DEFAULT_STRICT_TEXT_MODEL",
    "DEFAULT_VISION_MODEL",
]
