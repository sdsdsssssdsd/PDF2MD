"""兼容层。"""
from app.deepseek_api.image_transport import (
    INLINE_RAW_MAX,
    LOCAL_EXTS as SUPPORTED,
    convert_bmp_to_png,
    encode_base64,
    ensure_api_image,
    guess_mime,
    prepare_images,
)

__all__ = [
    "INLINE_RAW_MAX",
    "SUPPORTED",
    "convert_bmp_to_png",
    "encode_base64",
    "ensure_api_image",
    "guess_mime",
    "prepare_images",
]
