"""DeepSeek 公共 Chat Client。"""
from app.vision_api.client import DeepSeekVisionClient


class DeepSeekClient(DeepSeekVisionClient):
    """兼容旧 Vision 调用；新增 chat_json 公共文本能力。"""

