"""日常识图 Pipeline。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.daily_vision.exporter import parse_daily_response
from app.daily_vision.models import DailyVisionResult
from app.daily_vision.prompts import build_daily_prompt
from app.daily_vision.validator import validate_daily_result
from app.vision_api.client import DeepSeekVisionClient
from app.vision_api.config import VisionApiConfig


class DailyVisionPipeline:
    def __init__(
        self,
        *,
        config: VisionApiConfig | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._client = DeepSeekVisionClient(config=config, log=log)
        self._log = log or (lambda _m: None)

    def transcribe(self, image_paths: list[Path]) -> DailyVisionResult:
        paths = [Path(p) for p in image_paths if Path(p).is_file()]
        if not paths:
            raise ValueError("没有有效图片")
        prompt = build_daily_prompt(image_count=len(paths))
        self._log(f"[daily] 识别 {len(paths)} 张图片…")
        api_result = self._client.transcribe(paths, prompt)
        parsed = parse_daily_response(api_result.markdown)
        if not parsed.markdown.strip():
            parsed.markdown = api_result.markdown
        val_errs = validate_daily_result(parsed)
        if val_errs and not parsed.markdown.strip():
            raise ValueError("；".join(val_errs))
        return parsed
