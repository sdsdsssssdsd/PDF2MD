"""DeepSeek API → VisionWebAdapter。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.deepseek_api.client import DeepSeekClient
from app.deepseek_api.config import DeepSeekApiConfig, VisionApiConfig
from app.deepseek_api.errors import AuthenticationError, VisionApiError
from app.deepseek_api.profiles import PDF_VISION
from app.vision_api.file_cache import cache_path
from app.vision_transcribe.browser.base import AdapterResult, VisionWebAdapter


class DeepSeekApiVisionAdapter(VisionWebAdapter):
    """PDF 高精度：submit_batch → DeepSeekClient.vision_text(PDF_VISION)。"""

    def __init__(
        self,
        *,
        config: VisionApiConfig | DeepSeekApiConfig | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._client = DeepSeekClient(config=config, log=log)
        self._log = log or (lambda _m: None)
        self._output_dir: Path | None = None
        self._batch_id: int | None = None

    def set_capture_context(self, output_dir: Path, batch_id: int) -> None:
        self._output_dir = Path(output_dir)
        self._batch_id = int(batch_id)

    def submit_batch(self, images: list[Path], prompt: str) -> AdapterResult:
        cache_file = cache_path(self._output_dir)
        transport = (self._client.config.transport or "auto").lower()
        prefer = True if transport == "auto" else transport == "file_id"
        try:
            result = self._client.vision_text(
                images,
                prompt,
                profile=PDF_VISION,
                cache_file=cache_file,
                prefer_files=prefer,
            )
            stats = {
                "backend": "deepseek_api",
                "source": "deepseek_api",
                "provider": "deepseek",
                "model": self._client.config.model,
                "model_family": "DeepSeek-V4.1-Flash",
                "task_profile": PDF_VISION.name,
                "thinking": "disabled",
                "request_id": result.request_id,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": result.latency_ms,
                "transport": result.transport,
                "semantic_retry_count": result.semantic_retry_count,
                "transport_retry_count": result.transport_retry_count,
                "finish_reason": result.finish_reason,
                "batch_id": self._batch_id,
            }
            return AdapterResult(markdown=result.markdown, extract_stats=stats)
        except AuthenticationError as e:
            return AdapterResult(
                markdown="",
                needs_user=False,
                message=f"API 认证失败：{e}",
            )
        except VisionApiError as e:
            return AdapterResult(markdown="", needs_user=False, message=str(e))
        except Exception as e:
            return AdapterResult(markdown="", message=str(e))

    def prepare_manual_batch(
        self,
        images: list[Path],
        prompt: str,
        *,
        bookfigures_dir: Path | None = None,
    ) -> str:
        return ""
