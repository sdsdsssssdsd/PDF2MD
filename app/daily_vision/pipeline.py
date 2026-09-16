"""日常识图 Pipeline：vision_json + JSON Mode。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.daily_vision.exporter import parse_daily_response
from app.daily_vision.models import DailyVisionResult
from app.daily_vision.prompts import build_daily_prompt
from app.daily_vision.validator import validate_daily_result
from app.deepseek_api.client import DeepSeekClient
from app.deepseek_api.config import DeepSeekApiConfig, VisionApiConfig
from app.deepseek_api.profiles import DAILY_VISION


class DailyVisionPipeline:
    def __init__(
        self,
        *,
        config: VisionApiConfig | DeepSeekApiConfig | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._client = DeepSeekClient(config=config, log=log)
        self._log = log or (lambda _m: None)

    def transcribe(self, image_paths: list[Path]) -> DailyVisionResult:
        paths = [Path(p) for p in image_paths if Path(p).is_file()]
        if not paths:
            raise ValueError("没有有效图片")
        prompt = build_daily_prompt(image_count=len(paths))
        self._log(f"[daily] 识别 {len(paths)} 张图片…")
        payload = self._client.vision_json(
            paths,
            prompt,
            profile=DAILY_VISION,
            prefer_files=False,
        )
        parsed = parse_daily_response(payload)
        if not parsed.markdown.strip():
            parsed.markdown = str(payload.get("markdown") or "")
        val_errs = validate_daily_result(parsed)
        if val_errs and not parsed.markdown.strip():
            raise ValueError("；".join(val_errs))
        return parsed
