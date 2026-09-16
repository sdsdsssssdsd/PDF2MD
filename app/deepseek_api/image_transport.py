"""图片传输：Base64 / Files API。BMP 转 PNG；超限走 Files。"""
from __future__ import annotations

import base64
import json
import mimetypes
import tempfile
import uuid
from pathlib import Path
from typing import Callable

from app.deepseek_api.config import DeepSeekApiConfig
from app.deepseek_api.errors import NetworkError, RequestTooLargeError, UnsupportedMediaError
from app.deepseek_api.models import ImagePayload

API_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
LOCAL_EXTS = API_IMAGE_EXTS | {".bmp"}
INLINE_RAW_MAX = 28 * 1024 * 1024
FILES_RAW_MAX = 64 * 1024 * 1024

# 兼容旧名
SUPPORTED = LOCAL_EXTS
UnsupportedImageError = UnsupportedMediaError


def guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".gif":
        return "image/gif"
    if ext == ".webp":
        return "image/webp"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def convert_bmp_to_png(path: Path) -> Path:
    try:
        from PIL import Image
    except ImportError as exc:
        raise UnsupportedMediaError("BMP 需先转为 PNG，当前环境缺少 Pillow") from exc
    dest = Path(tempfile.mkdtemp(prefix="pdf2md_bmp_")) / f"{path.stem}.png"
    with Image.open(path) as img:
        img.save(dest, format="PNG")
    return dest


def ensure_api_image(path: Path) -> Path:
    p = Path(path)
    if p.suffix.lower() == ".bmp":
        return convert_bmp_to_png(p)
    if p.suffix.lower() not in API_IMAGE_EXTS:
        raise UnsupportedMediaError(f"不支持的图片格式: {p.suffix}")
    return p


def encode_base64(path: Path) -> ImagePayload:
    api_path = ensure_api_image(path)
    data = api_path.read_bytes()
    if len(data) > INLINE_RAW_MAX:
        raise RequestTooLargeError(f"图片过大: {path.name}")
    mime = guess_mime(api_path)
    b64 = base64.standard_b64encode(data).decode("ascii")
    return ImagePayload(path=api_path, mime=mime, data_url=f"data:{mime};base64,{b64}")


def prepare_images(
    paths: list[Path],
    *,
    config: DeepSeekApiConfig,
    api_key: str,
    http_post: Callable[..., dict],
    log: Callable[[str], None] | None = None,
    cache_file: Path | None = None,
    prefer_files: bool = False,
) -> list[ImagePayload]:
    transport = (config.transport or "auto").lower()
    force_files = transport == "file_id" or (transport == "auto" and prefer_files)
    out: list[ImagePayload] = []
    for p in paths:
        p = Path(p)
        if not p.is_file():
            raise UnsupportedMediaError(f"图片不存在: {p}")
        p = ensure_api_image(p)
        raw_size = p.stat().st_size
        if raw_size > FILES_RAW_MAX:
            raise RequestTooLargeError(f"图片超过 Files API 限制: {p.name}")

        if cache_file is not None:
            from app.vision_api.file_cache import lookup

            cached = lookup(p, cache_file=cache_file)
            if cached:
                if log:
                    log(f"[api] 复用 file_id · {p.name}")
                out.append(
                    ImagePayload(
                        path=p,
                        mime=guess_mime(p),
                        file_id=str(cached["file_id"]),
                    )
                )
                continue

        use_files = force_files or (transport == "auto" and raw_size > INLINE_RAW_MAX)
        if use_files:
            out.append(
                _upload_with_cache(
                    p,
                    config=config,
                    api_key=api_key,
                    http_post=http_post,
                    log=log,
                    cache_file=cache_file,
                )
            )
            continue

        try:
            out.append(encode_base64(p))
        except RequestTooLargeError:
            if transport == "base64":
                raise
            out.append(
                _upload_with_cache(
                    p,
                    config=config,
                    api_key=api_key,
                    http_post=http_post,
                    log=log,
                    cache_file=cache_file,
                )
            )
    return out


def _upload_with_cache(
    path: Path,
    *,
    config: DeepSeekApiConfig,
    api_key: str,
    http_post: Callable[..., dict],
    log: Callable[[str], None] | None,
    cache_file: Path | None,
) -> ImagePayload:
    payload = _upload_file(
        path,
        config=config,
        api_key=api_key,
        http_post=http_post,
        log=log,
    )
    if cache_file is not None and payload.file_id:
        from app.vision_api.file_cache import store

        store(path, cache_file=cache_file, file_id=payload.file_id)
    return payload


def _upload_file(
    path: Path,
    *,
    config: DeepSeekApiConfig,
    api_key: str,
    http_post: Callable[..., dict],
    log: Callable[[str], None] | None,
) -> ImagePayload:
    import urllib.error
    import urllib.request

    boundary = f"----pdf2md-{uuid.uuid4().hex}"
    mime = guess_mime(path)
    body_parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="purpose"\r\n\r\n',
        b"user_data\r\n",
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(body_parts)
    req = urllib.request.Request(
        config.files_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=config.timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise NetworkError(f"Files API 上传失败 HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise NetworkError(f"Files API 网络错误: {e}") from e

    data = json.loads(raw)
    file_id = str(data.get("id") or "")
    if not file_id:
        raise NetworkError(f"Files API 未返回 file_id: {raw[:200]}")
    if log:
        log(f"[api] 已上传 {path.name} → file_id")
    return ImagePayload(path=path, mime=mime, file_id=file_id)
