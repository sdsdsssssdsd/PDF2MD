"""DeepSeek API 核心客户端：chat_text / chat_json / vision_text / vision_json。"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from app.deepseek_api.config import DEFAULT_MODEL, DeepSeekApiConfig
from app.deepseek_api.errors import (
    AuthenticationError,
    DeepSeekApiError,
    EmptyContentError,
    InvalidJsonError,
    ModelError,
    NetworkError,
    RateLimitError,
    RequestTooLargeError,
    ResponseValidationError,
    UnsupportedMediaError,
    VisionApiError,
)
from app.deepseek_api.image_transport import prepare_images
from app.deepseek_api.key_store import get_api_key
from app.deepseek_api.models import ImagePayload, TranscribeResult
from app.deepseek_api.profiles import (
    DAILY_VISION,
    FORMAT_REPAIR,
    PDF_VISION,
    DeepSeekTaskProfile,
    get_profile,
)

JSON_ONLY_HINT = "必须仅输出合法 JSON 对象，不要输出任何前后文字，不要使用 markdown 围栏。"
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def normalize_detail(detail: str) -> str:
    d = (detail or "original").strip().lower()
    if d in ("low", "high", "original", "auto"):
        return d
    return "original"


def extract_assistant_text(message: dict[str, Any], choice: dict[str, Any] | None = None) -> str:
    """只取最终 content，不用 reasoning_content 充当正文。"""
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
                "请增大 max_tokens，或确认 thinking=disabled 已生效。"
            )
        return "输出 token 预算不足（finish_reason=length），请增大 max_tokens。"
    if has_reasoning:
        return "content 为空但存在 reasoning_content（已忽略推理内容，需重试最终输出）。"
    return f"API 返回空内容（finish_reason={finish or '未知'}）"


def build_message_content(
    prompt: str,
    payloads: list[ImagePayload],
    detail: str,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    detail_level = normalize_detail(detail)
    for pl in payloads:
        if pl.file_id:
            content.append({"type": "file", "file_id": pl.file_id})
        else:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": pl.data_url, "detail": detail_level},
                }
            )
    return content


class DeepSeekClient:
    """业务层唯一 HTTP 入口。模型始终来自 config.model（默认 deepseek-flash）。"""

    def __init__(
        self,
        config: DeepSeekApiConfig | None = None,
        *,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config or DeepSeekApiConfig.from_settings()
        self.config.model = self.config.model or DEFAULT_MODEL
        self._log = log or (lambda _m: None)
        self.last_semantic_retries = 0
        self.last_transport_retries = 0

    def chat_text(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        profile: DeepSeekTaskProfile | str | None = None,
    ) -> str:
        prof = get_profile(profile or FORMAT_REPAIR)
        result = self._complete_text(messages, profile=prof, max_tokens=max_tokens)
        return result.markdown

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        profile: DeepSeekTaskProfile | str | None = None,
    ) -> dict:
        prof = get_profile(profile or "correction_review")
        return self._complete_json(messages, profile=prof, max_tokens=max_tokens)

    def vision_text(
        self,
        images: list[Path],
        prompt: str,
        *,
        profile: DeepSeekTaskProfile | str | None = None,
        detail: str | None = None,
        cache_file: Path | None = None,
        prefer_files: bool | None = None,
    ) -> TranscribeResult:
        prof = get_profile(profile or PDF_VISION)
        return self._vision_call(
            images,
            prompt,
            profile=prof,
            detail=detail,
            cache_file=cache_file,
            prefer_files=prefer_files,
            as_json=False,
        )

    def vision_json(
        self,
        images: list[Path],
        prompt: str,
        *,
        profile: DeepSeekTaskProfile | str | None = None,
        detail: str | None = None,
        cache_file: Path | None = None,
        prefer_files: bool | None = None,
    ) -> dict:
        prof = get_profile(profile or DAILY_VISION)
        result = self._vision_call(
            images,
            prompt,
            profile=prof,
            detail=detail,
            cache_file=cache_file,
            prefer_files=prefer_files,
            as_json=True,
        )
        return self._parse_json_text(result.markdown)

    def transcribe(
        self,
        images: list[Path],
        prompt: str,
        *,
        detail: str | None = None,
        cache_file: Path | None = None,
        prefer_files: bool = False,
    ) -> TranscribeResult:
        return self.vision_text(
            images,
            prompt,
            profile=PDF_VISION,
            detail=detail,
            cache_file=cache_file,
            prefer_files=prefer_files,
        )

    def test_connection(self) -> TranscribeResult:
        api_key = get_api_key()
        if not api_key:
            raise AuthenticationError("未配置 DeepSeek API Key")
        body = self._base_body(
            [{"role": "user", "content": "只回复一个单词：OK"}],
            max_tokens=64,
            profile=FORMAT_REPAIR,
        )
        data = self._request_with_retry(body, api_key=api_key)
        return self._parse_response(data, allow_empty_if_ok=True, profile=FORMAT_REPAIR)

    def test_vision(self) -> TranscribeResult:
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
            profile=DAILY_VISION,
        )
        data = self._request_with_retry(body, api_key=api_key)
        return self._parse_response(data, allow_empty_if_ok=True, profile=DAILY_VISION)

    def _complete_text(
        self,
        messages: list[dict[str, Any]],
        *,
        profile: DeepSeekTaskProfile,
        max_tokens: int | None,
        json_mode: bool = False,
    ) -> TranscribeResult:
        api_key = self._require_key()
        body = self._base_body(
            messages, max_tokens=max_tokens, profile=profile, json_mode=json_mode
        )
        data = self._request_with_retry(body, api_key=api_key)
        return self._parse_response(data, profile=profile)

    def _complete_json(
        self,
        messages: list[dict[str, Any]],
        *,
        profile: DeepSeekTaskProfile,
        max_tokens: int | None,
    ) -> dict:
        last_err: Exception | None = None
        working = list(messages)
        self.last_semantic_retries = 0
        for attempt in range(3):
            try:
                result = self._complete_text(
                    working, profile=profile, max_tokens=max_tokens, json_mode=True
                )
                return self._parse_json_text(result.markdown)
            except (EmptyContentError, InvalidJsonError, ResponseValidationError) as exc:
                last_err = exc
                if attempt >= 2:
                    break
                self.last_semantic_retries += 1
                self._log(f"[api] JSON 语义重试 {self.last_semantic_retries}: {exc}")
                working = _append_json_hint(working)
        raise last_err or InvalidJsonError("API 未返回合法 JSON")

    def _vision_call(
        self,
        images: list[Path],
        prompt: str,
        *,
        profile: DeepSeekTaskProfile,
        detail: str | None = None,
        cache_file: Path | None = None,
        prefer_files: bool | None = None,
        as_json: bool = False,
    ) -> TranscribeResult:
        api_key = self._require_key()
        detail_level = detail or self.config.detail
        use_files = self.config.transport == "file_id" or (
            prefer_files if prefer_files is not None else profile.prefer_files
        )
        last_err: Exception | None = None
        working_prompt = prompt
        semantic = 0
        attempts = 3 if as_json else 1
        for attempt in range(attempts):
            try:
                return self._transcribe_once(
                    images,
                    working_prompt,
                    api_key=api_key,
                    detail=detail_level,
                    cache_file=cache_file,
                    prefer_files=use_files,
                    use_cache=True,
                    profile=profile,
                    as_json=as_json,
                    semantic_retries=semantic,
                )
            except VisionApiError as e:
                msg = str(e).lower()
                if cache_file and (use_files or "file" in msg or "file_id" in msg):
                    self._log("[api] Files 路径失败，回退 Base64 重试…")
                    from app.vision_api.file_cache import invalidate_paths

                    invalidate_paths([Path(p) for p in images], cache_file=cache_file)
                    return self._transcribe_once(
                        images,
                        working_prompt,
                        api_key=api_key,
                        detail=detail_level,
                        cache_file=cache_file,
                        prefer_files=False,
                        use_cache=False,
                        profile=profile,
                        as_json=as_json,
                        semantic_retries=semantic,
                    )
                if as_json and isinstance(
                    e, (EmptyContentError, InvalidJsonError, ResponseValidationError)
                ) and attempt < attempts - 1:
                    last_err = e
                    semantic += 1
                    self.last_semantic_retries = semantic
                    working_prompt = f"{prompt}\n\n{JSON_ONLY_HINT}"
                    self._log(f"[api] 视觉 JSON 语义重试 {semantic}: {e}")
                    continue
                raise
        raise last_err or ResponseValidationError("视觉 JSON 调用失败")

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
        profile: DeepSeekTaskProfile,
        as_json: bool,
        semantic_retries: int,
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
        body = self._base_body(
            [{"role": "user", "content": content}],
            max_tokens=profile.max_tokens,
            profile=profile,
            json_mode=as_json or profile.response_format == "json_object",
        )
        data = self._request_with_retry(body, api_key=api_key)
        result = self._parse_response(data, profile=profile)
        result.semantic_retry_count = semantic_retries
        result.transport = "file_id" if any(p.file_id for p in payloads) else "base64"
        if as_json:
            self._parse_json_text(result.markdown)
        return result

    def _base_body(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        profile: DeepSeekTaskProfile | None = None,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        prof = profile or PDF_VISION
        tokens = int(max_tokens or prof.max_tokens or self.config.max_output_tokens or 16384)
        body: dict[str, Any] = {
            "model": self.config.model or DEFAULT_MODEL,
            "messages": messages,
            "temperature": float(prof.temperature),
            "max_tokens": tokens,
            "stream": False,
        }
        thinking = (self.config.thinking or prof.thinking or "disabled").strip() or "disabled"
        body["thinking"] = {"type": thinking}
        if json_mode or prof.response_format == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    def _request_with_retry(self, body: dict[str, Any], *, api_key: str) -> dict[str, Any]:
        max_tries = max(1, self.config.max_retries + 1) if self.config.auto_retry else 1
        last_err: Exception | None = None
        transport_retries = 0
        for attempt in range(max_tries):
            try:
                t0 = time.perf_counter()
                data = self._post_json(body, api_key=api_key)
                latency = int((time.perf_counter() - t0) * 1000)
                data["_latency_ms"] = latency
                self.last_transport_retries = transport_retries
                return data
            except DeepSeekApiError as e:
                last_err = e
                if not e.retryable or attempt >= max_tries - 1:
                    raise
                transport_retries += 1
                delay = min(60.0, (2**attempt) + random.uniform(0, 0.5))
                self._log(f"[api] 传输重试 {attempt + 1}/{max_tries - 1}，{delay:.1f}s 后… ({e})")
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
        last_err: DeepSeekApiError | None = None
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
                if e.code == 400 and "thinking" in body and "thinking" in detail.lower():
                    if self.config.compatibility_mode:
                        self._log("[api] 兼容模式：网关不接受 thinking，去掉后重试")
                        slim = {k: v for k, v in body.items() if k != "thinking"}
                        return self._post_json(slim, api_key=api_key)
                    raise ModelError(
                        "当前网关不接受 thinking 参数。官方 DeepSeek API 需显式 thinking=disabled；"
                        "若使用第三方兼容网关，请在设置中打开「兼容第三方网关」。"
                        f" HTTP 400: {detail[:400]}"
                    ) from e
                if e.code == 404 and url != self.config.chat_completion_urls()[-1]:
                    last_err = err
                    continue
                raise err from e
            except urllib.error.URLError as e:
                raise NetworkError(str(e)) from e
        raise last_err or NetworkError("API 请求失败")

    def _parse_response(
        self,
        data: dict[str, Any],
        *,
        allow_empty_if_ok: bool = False,
        profile: DeepSeekTaskProfile | None = None,
    ) -> TranscribeResult:
        if data.get("error"):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise ModelError(str(msg))
        choices = data.get("choices") or []
        if not choices:
            raise ResponseValidationError("API 响应缺少 choices")
        choice = choices[0]
        message = choice.get("message") or {}
        finish = str(choice.get("finish_reason") or "")
        text = extract_assistant_text(message, choice)
        prof = profile or PDF_VISION
        if not text:
            if allow_empty_if_ok:
                usage = data.get("usage") or {}
                return TranscribeResult(
                    markdown="OK",
                    request_id=str(data.get("id") or ""),
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    latency_ms=data.get("_latency_ms"),
                    finish_reason=finish,
                    task_profile=prof.name,
                    thinking=self.config.thinking,
                    transport_retry_count=self.last_transport_retries,
                    raw=data,
                )
            raise EmptyContentError(empty_content_hint(message, choice))
        usage = data.get("usage") or {}
        return TranscribeResult(
            markdown=text,
            request_id=str(data.get("id") or ""),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=data.get("_latency_ms"),
            finish_reason=finish,
            task_profile=prof.name,
            thinking=self.config.thinking,
            transport_retry_count=self.last_transport_retries,
            raw=data,
        )

    def _parse_json_text(self, text: str) -> dict:
        raw = (text or "").strip()
        if not raw:
            raise EmptyContentError("API 返回空 JSON 文本")
        candidate = raw
        if not raw.startswith("{") and "{" in raw and "}" in raw:
            candidate = raw[raw.find("{") : raw.rfind("}") + 1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise InvalidJsonError(f"API 未返回合法 JSON: {raw[:200]}") from exc
        return parsed if isinstance(parsed, dict) else {"raw": parsed}

    def _require_key(self) -> str:
        api_key = get_api_key()
        if not api_key:
            raise AuthenticationError("未配置 DeepSeek API Key（设置或 DEEPSEEK_API_KEY）")
        return api_key


def _append_json_hint(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [dict(m) for m in messages]
    if not out:
        return [{"role": "user", "content": JSON_ONLY_HINT}]
    last = dict(out[-1])
    content = last.get("content")
    if isinstance(content, str):
        last["content"] = f"{content}\n\n{JSON_ONLY_HINT}"
    out[-1] = last
    return out


def _http_error(code: int, detail: str) -> DeepSeekApiError:
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
        return UnsupportedMediaError(
            f"HTTP 400（视觉/图片不支持）: {snippet}。"
            f"请确认模型为 {DEFAULT_MODEL}，且图片在 user 消息中。"
        )
    if code >= 500:
        return ModelError(f"HTTP {code}: {snippet}")
    return ModelError(f"HTTP {code}: {snippet}")


DeepSeekVisionClient = DeepSeekClient
