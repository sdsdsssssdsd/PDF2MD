"""兼容层。"""
from app.deepseek_api.errors import (
    AuthenticationError,
    DeepSeekApiError,
    EmptyContentError,
    IntegrityViolationError,
    InvalidJsonError,
    ModelError,
    NetworkError,
    RateLimitError,
    RequestTooLargeError,
    ResponseValidationError,
    UnsupportedImageError,
    UnsupportedMediaError,
    VisionApiError,
    VisionModelError,
)

__all__ = [
    "AuthenticationError",
    "DeepSeekApiError",
    "EmptyContentError",
    "IntegrityViolationError",
    "InvalidJsonError",
    "ModelError",
    "NetworkError",
    "RateLimitError",
    "RequestTooLargeError",
    "ResponseValidationError",
    "UnsupportedImageError",
    "UnsupportedMediaError",
    "VisionApiError",
    "VisionModelError",
]
