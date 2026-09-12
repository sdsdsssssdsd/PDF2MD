"""DeepSeek Vision API 客户端（项目唯一 HTTP 入口）。"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from app.vision_api.config import VisionApiConfig
from app.vision_api.errors import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
    RequestTooLargeError,
    ResponseValidationError,
    UnsupportedImageError,
    VisionApiError,
    VisionModelError,
)
from app.vision_api.image_transport import prepare_images
from app.vision_api.key_store import get_api_key
from app.vision_api.models import ImagePayload, TranscribeResult

# 1×1 透明 PNG，用于设置页「视觉连通性」探测
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def normalize_detail(detail: str) -> str:
    d = (detail or "original").strip().lower()
    if d in ("low", "high", "original", "auto"):
        return d
    return "original"


def extract_assistant_text(message: dict[str, Any], choice: dict[str, Any] | None = None) -> str:
    """从 DeepSeek Chat Completions 消息中提取可见文本（兼容 thinking / 多模态）。"""
    content = message.get("content")
    if content is None:
        content = ""
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block.get("text") or ""))
        content = "".join(parts)
    text = str(content).strip()
    if text:
        return text

    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()

    # 部分网关把正文放在 choice.text（旧兼容格式）
    if choice:
        legacy = choice.get("text")
        if isinstance(legacy, str) and legacy.strip():
            return legacy.strip()
    return ""


def empty_content_hint(message: dict[str, Any], choice: dict[str, Any]) -> str:
    finish = str(choice.get("finish_reason") or "")
    has_reasoning = bool(str(message.get("reasoning_content") or "").strip())
    if finish == "length":
        if has_reasoning:
            return (
                "输出 token 预算不足（finish_reason=length）："
                "thinking 占满 max_tokens，未生成可见 content。"
                "已尝试关闭 thinking；请增大 max_tokens 或换用 deepseek-v4-flash-vision-exp。"
            )
        return "输出 token 预算不足（finish_reason=length），请增大 max_tokens。"
    if has_reasoning:
        return "content 为空但存在 reasoning_content（thinking 模式）。"
    return f"API 返回空内容（finish_reason={finish or '未知'}）"


def build_message_content(
    prompt: str,
    payloads: list[ImagePayload],
    detail: str,
) -> list[dict[str, Any]]:
    """构造 DeepSeek Chat Completions 多模态 content（对齐官方 Vision 指南）。"""
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    detail_level = normalize_detail(detail)
    for pl in payloads:
        if pl.file_id:
            # 官方：Files API 引用必须用 type=file，而非 image_url.file_id
            content.append({"type": "file", "file_id": pl.file_id})
        else:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": pl.data_url, "detail": detail_level},
                }
            )
    return content


class DeepSeekVisionClient:
    """上层统一调用 transcribe()，不直接构造 chat.completions。"""

    def __init__(
        self,
        config: VisionApiConfig | None = None,
        *,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config or VisionApiConfig.from_settings()
        self._log = log or (lambda _m: None)

    def transcribe(
        self,
        images: list[Path],
        prompt: str,
        *,
        detail: str | None = None,
        cache_file: Path | None = None,
        prefer_files: bool = False,
    ) -> TranscribeResult:
        api_key = get_api_key()
        if not api_key:
            raise AuthenticationError("未配置 DeepSeek API Key（设置或 DEEPSEEK_API_KEY）")

        detail_level = detail or self.config.detail
        try:
            return self._transcribe_once(
                images,
                prompt,
                api_key=api_key,
                detail=detail_level,
                cache_file=cache_file,
                prefer_files=prefer_files,
                use_cache=True,
            )
        except VisionApiError as e:
            # Files/file_id 格式或缓存失效 → 清缓存后 Base64 重试
            msg = str(e).lower()
            if cache_file and (prefer_files or "file" in msg or "file_id" in msg):
                self._log("[api] Files 路径失败，回退 Base64 重试…")
                from app.vision_api.file_cache import invalidate_paths

                invalidate_paths([Path(p) for p in images], cache_file=cache_file)
                return self._transcribe_once(
                    images,
                    prompt,
                    api_key=api_key,
                    detail=detail_level,
                    cache_file=cache_file,
                    prefer_files=False,
                    use_cache=False,
                )
            raise

    def test_connection(self) -> TranscribeResult:
        """文本连通性：验证 Key 与 endpoint。"""
        api_key = get_api_key()
        if not api_key:
            raise AuthenticationError("未配置 DeepSeek API Key")
        body = self._base_body(
            [{"role": "user", "content": "只回复一个单词：OK"}],
            max_tokens=64,
        )
        data = self._request_with_retry(body, api_key=api_key)
        return self._parse_response(data, allow_empty_if_ok=True)

    def test_vision(self) -> TranscribeResult:
        """视觉连通性：小图 + 文本，验证模型是否支持识图。"""
        api_key = get_api_key()
        if not api_key:
            raise AuthenticationError("未配置 DeepSeek API Key")
        data_url = f"data:image/png;base64,{_TINY_PNG_B64}"
        body = self._base_body(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "用英文一个词描述图片颜色。"},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "low"},
                        },
                    ],
                }
            ],
            max_tokens=128,
        )
        data = self._request_with_retry(body, api_key=api_key)
        return self._parse_response(data, allow_empty_if_ok=True)

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """公共 JSON Chat Completions（格式复检等非视觉任务）。"""
        api_key = get_api_key()
        if not api_key:
            raise AuthenticationError("未配置 DeepSeek API Key")
        body: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": int(max_tokens or 4096),
            "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
        }
        data = self._request_with_retry(body, api_key=api_key)
        if data.get("error"):
            raise VisionModelError(str(data["error"]))
        choices = data.get("choices") or []
        if not choices:
            raise ResponseValidationError("API 响应缺少 choices")
        message = choices[0].get("message") or {}
        text = extract_assistant_text(message, choices[0])
        if not text:
            raise ResponseValidationError("API 返回空 JSON 文本")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ResponseValidationError(f"API 未返回合法 JSON: {text[:200]}") from exc
        return parsed if isinstance(parsed, dict) else {"raw": parsed}

    def chat_text(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """公共文本 Chat Completions（格式修正等：直接返回 Markdown）。"""
        api_key = get_api_key()
        if not api_key:
            raise AuthenticationError("未配置 DeepSeek API Key")
        body: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": int(max_tokens or 8192),
            "stream": False,
            "thinking": {"type": "disabled"},
        }
        data = self._request_with_retry(body, api_key=api_key)
        if data.get("error"):
            raise VisionModelError(str(data["error"]))
        choices = data.get("choices") or []
        if not choices:
            raise ResponseValidationError("API 响应缺少 choices")
        message = choices[0].get("message") or {}
        text = extract_assistant_text(message, choices[0])
        if not text:
            raise ResponseValidationError("API 返回空文本")
        return text

    def _transcribe_once(
        self,
        images: list[Path],
        prompt: str,
        *,
        api_key: str,
        detail: str,
        cache_file: Path | None,
        prefer_files: bool,
        use_cache: bool,
    ) -> TranscribeResult:
        payloads = prepare_images(
            [Path(p) for p in images],
            config=self.config,
            api_key=api_key,
            http_post=self._post_json,
            log=self._log,
            cache_file=cache_file if use_cache else None,
            prefer_files=prefer_files,
        )
        content = build_message_content(prompt, payloads, detail)
        body = self._base_body([{"role": "user", "content": content}])
        data = self._request_with_retry(body, api_key=api_key)
        return self._parse_response(data)

    def _base_body(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": int(max_tokens or self.config.max_output_tokens or 16384),
            "stream": False,
        }
        # 视觉转录需要 message.content；关闭 thinking 避免 reasoning 吃光 token 导致 content 为空
        body["thinking"] = {"type": "disabled"}
        return body

    def _request_with_retry(self, body: dict[str, Any], *, api_key: str) -> dict[str, Any]:
        max_tries = max(1, self.config.max_retries + 1) if self.config.auto_retry else 1
        last_err: Exception | None = None
        for attempt in range(max_tries):
            try:
                t0 = time.perf_counter()
                data = self._post_json(body, api_key=api_key)
                latency = int((time.perf_counter() - t0) * 1000)
                data["_latency_ms"] = latency
                return data
            except VisionApiError as e:
                last_err = e
                if not e.retryable or attempt >= max_tries - 1:
                    raise
                delay = min(60.0, (2**attempt) + random.uniform(0, 0.5))
                self._log(f"[api] 重试 {attempt + 1}/{max_tries - 1}，{delay:.1f}s 后… ({e})")
                time.sleep(delay)
        raise last_err or NetworkError("API 请求失败")

    def _post_json(self, body: dict[str, Any], *, api_key: str) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if len(payload) > 48 * 1024 * 1024:
            raise RequestTooLargeError("请求体超过 48 MiB 限制")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        last_err: VisionApiError | None = None
        bodies_to_try = [body]
        if "thinking" in body:
            bodies_to_try.append({k: v for k, v in body.items() if k != "thinking"})
        for attempt_body in bodies_to_try:
            payload = json.dumps(attempt_body, ensure_ascii=False).encode("utf-8")
            for url in self.config.chat_completion_urls():
                req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
                        raw = resp.read().decode("utf-8", errors="replace")
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError as e:
                        raise ResponseValidationError(f"响应非 JSON: {raw[:200]}") from e
                except urllib.error.HTTPError as e:
                    detail = e.read().decode("utf-8", errors="replace")
                    err = _http_error(e.code, detail)
                    # thinking 参数不被接受 → 去掉后重试
                    if (
                        e.code == 400
                        and "thinking" in attempt_body
                        and attempt_body is bodies_to_try[0]
                    ):
                        last_err = err
                        break
                    if e.code == 404 and url != self.config.chat_completion_urls()[-1]:
                        last_err = err
                        continue
                    raise err from e
                except urllib.error.URLError as e:
                    raise NetworkError(str(e)) from e
            if attempt_body is bodies_to_try[0] and len(bodies_to_try) > 1:
                continue
        raise last_err or NetworkError("API 请求失败")

    def _parse_response(
        self,
        data: dict[str, Any],
        *,
        allow_empty_if_ok: bool = False,
    ) -> TranscribeResult:
        if data.get("error"):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise VisionModelError(str(msg))
        choices = data.get("choices") or []
        if not choices:
            raise ResponseValidationError("API 响应缺少 choices")
        choice = choices[0]
        message = choice.get("message") or {}
        text = extract_assistant_text(message, choice)
        if not text:
            if allow_empty_if_ok:
                usage = data.get("usage") or {}
                return TranscribeResult(
                    markdown="OK",
                    request_id=str(data.get("id") or ""),
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    latency_ms=data.get("_latency_ms"),
                    raw=data,
                )
            raise ResponseValidationError(empty_content_hint(message, choice))
        usage = data.get("usage") or {}
        return TranscribeResult(
            markdown=text,
            request_id=str(data.get("id") or ""),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=data.get("_latency_ms"),
            raw=data,
        )


def _http_error(code: int, detail: str) -> VisionApiError:
    snippet = detail[:800]
    lower = snippet.lower()
    if code in (401, 403):
        return AuthenticationError(f"HTTP {code}: {snippet}")
    if code == 429:
        return RateLimitError(f"HTTP 429: {snippet}")
    if code == 413:
        return RequestTooLargeError(f"HTTP 413: {snippet}")
    if code == 400 and any(
        k in lower for k in ("image", "vision", "unsupported", "multimodal", "file_id", "file")
    ):
        return UnsupportedImageError(
            f"HTTP 400（视觉/图片不支持）: {snippet}。"
            "请确认模型为 deepseek-flash 或 deepseek-v4-flash-vision-exp，且图片在 user 消息中。"
        )
    if code >= 500:
        return VisionModelError(f"HTTP {code}: {snippet}")
    return VisionModelError(f"HTTP {code}: {snippet}")
