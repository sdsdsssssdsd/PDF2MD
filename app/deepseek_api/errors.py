"""DeepSeek API 错误体系。Vision* 名称为兼容别名。"""
from __future__ import annotations


class DeepSeekApiError(RuntimeError):
    retryable: bool = False


class AuthenticationError(DeepSeekApiError):
    retryable = False


class RateLimitError(DeepSeekApiError):
    retryable = True


class NetworkError(DeepSeekApiError):
    retryable = True


class RequestTooLargeError(DeepSeekApiError):
    retryable = True


class UnsupportedMediaError(DeepSeekApiError):
    retryable = False


class ModelError(DeepSeekApiError):
    retryable = True


class ResponseValidationError(DeepSeekApiError):
    retryable = True


class EmptyContentError(ResponseValidationError):
    retryable = True


class InvalidJsonError(ResponseValidationError):
    retryable = True


class IntegrityViolationError(DeepSeekApiError):
    retryable = False


# 兼容旧名
VisionApiError = DeepSeekApiError
VisionModelError = ModelError
UnsupportedImageError = UnsupportedMediaError

__all__ = [
    "DeepSeekApiError",
    "AuthenticationError",
    "RateLimitError",
    "NetworkError",
    "RequestTooLargeError",
    "UnsupportedMediaError",
    "ModelError",
    "ResponseValidationError",
    "EmptyContentError",
    "InvalidJsonError",
    "IntegrityViolationError",
    "VisionApiError",
    "VisionModelError",
    "UnsupportedImageError",
]
