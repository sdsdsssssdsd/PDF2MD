"""DeepSeek API Key 兼容层。"""
from app.vision_api.key_store import api_key_configured, get_api_key, set_api_key

__all__ = ["api_key_configured", "get_api_key", "set_api_key"]
