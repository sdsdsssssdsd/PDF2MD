"""日常识图 Pipeline：分批 + 流式进度 + JSON Mode。

为什么分批：一次请求塞 39 张图时，模型输出会超过 max_tokens 被截断，JSON 直接解析失败。
按 DAILY_BATCH_SIZE 分批后，每批输出有界，同时天然给出「第 k/N 批」真实进度。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.daily_vision.batching import merge_batch
from app.daily_vision.exporter import parse_daily_response
from app.daily_vision.models import (
    DailyVisionCancelled,
    DailyVisionResult,
    ProgressFn,
)
from app.daily_vision.prompts import build_daily_prompt
from app.daily_vision.validator import validate_daily_result
from app.deepseek_api.client import DeepSeekClient
from app.deepseek_api.config import DeepSeekApiConfig, VisionApiConfig
from app.deepseek_api.errors import VisionApiError
from app.deepseek_api.profiles import DAILY_VISION
from app.utils.progress import MODEL_PERCENT, StreamProgress

# 与 API 高精度视觉一致：每批 6 张，单批输出稳定落在 max_tokens 之内
DAILY_BATCH_SIZE = 6


class DailyVisionPipeline:
    def __init__(
        self,
        *,
        config: VisionApiConfig | DeepSeekApiConfig | None = None,
        log: Callable[[str], None] | None = None,
        batch_size: int = DAILY_BATCH_SIZE,
    ) -> None:
        self._client = DeepSeekClient(config=config, log=log)
        self._log = log or (lambda _m: None)
        self._batch_size = max(1, int(batch_size))

    def transcribe(
        self,
        image_paths: list[Path],
        *,
        progress: ProgressFn | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> DailyVisionResult:
        emit = progress or (lambda _text, _percent: None)
        is_cancelled = cancelled or (lambda: False)
        paths = [Path(p) for p in image_paths if Path(p).is_file()]
        if not paths:
            raise ValueError("没有有效图片")

        total = len(paths)
        batches = [
            paths[i : i + self._batch_size] for i in range(0, total, self._batch_size)
        ]
        merged = DailyVisionResult()
        errors: list[str] = []
        done = 0
        self._log(f"[daily] 识别 {total} 张图片（{len(batches)} 批 × ≤{self._batch_size} 张）…")

        for index, batch in enumerate(batches, start=1):
            if is_cancelled():
                raise DailyVisionCancelled("已取消")
            base = MODEL_PERCENT * done / total
            span = MODEL_PERCENT * len(batch) / total
            emit(
                f"第 {index}/{len(batches)} 批：DeepSeek 识别中…（等待模型返回）",
                int(base),
            )
            try:
                batch_result = self._transcribe_batch(
                    batch,
                    index=index,
                    batches=len(batches),
                    base=base,
                    span=span,
                    emit=emit,
                    is_cancelled=is_cancelled,
                )
            except VisionApiError as exc:
                errors.append(f"第 {index}/{len(batches)} 批失败：{exc}")
                self._log(f"[daily] 第 {index}/{len(batches)} 批失败：{exc}")
                done += len(batch)
                continue

            merge_batch(merged, batch_result, offset=done)
            merged.warnings.extend(batch_result.warnings)
            done += len(batch)
            emit(f"已完成 {done}/{total} 张", int(MODEL_PERCENT * done / total))

        if not merged.markdown.strip():
            reason = (
                "；".join(errors)
                or "；".join(validate_daily_result(merged))
                or "识别结果为空"
            )
            raise ValueError(reason)
        merged.warnings.extend(errors)
        return merged

    def _transcribe_batch(
        self,
        batch: list[Path],
        *,
        index: int,
        batches: int,
        base: float,
        span: float,
        emit: ProgressFn,
        is_cancelled: Callable[[], bool],
    ) -> DailyVisionResult:
        prompt = build_daily_prompt(image_count=len(batch))
        reporter = StreamProgress(
            emit, base=base, span=span, label=f"第 {index}/{batches} 批"
        )

        def _on_delta(total_chars: int) -> None:
            if is_cancelled():  # 流式每段都是取消检查点
                raise DailyVisionCancelled("已取消")
            reporter.feed(total_chars)

        payload = self._client.vision_json(
            batch,
            prompt,
            profile=DAILY_VISION,
            prefer_files=False,
            on_delta=_on_delta,
            salvage_truncated=True,
        )
        parsed = parse_daily_response(payload)
        if payload.get("_salvaged"):
            parsed.warnings.append(
                f"第 {index}/{batches} 批输出被截断，该批内容可能不完整"
            )
            self._log(f"[daily] 第 {index}/{batches} 批输出被截断，已保留可解析部分")
        if not parsed.markdown.strip():
            parsed.warnings.append(f"第 {index}/{batches} 批未返回内容（已跳过）")
        return parsed
