"""DeepSeek 任务配置：行为差异走 Profile，不换模型。"""
from __future__ import annotations

from dataclasses import dataclass

from app.deepseek_api.config import DEFAULT_MAX_OUTPUT_TOKENS, DEFAULT_MODEL


@dataclass(frozen=True)
class DeepSeekTaskProfile:
    name: str
    output: str  # markdown | json
    images: bool
    max_tokens: int
    thinking: str = "disabled"
    prefer_files: bool = False
    temperature: float = 0.0
    response_format: str | None = None  # json_object | None
    model: str = DEFAULT_MODEL


DAILY_VISION = DeepSeekTaskProfile(
    name="daily_vision",
    output="json",
    images=True,
    max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
    prefer_files=False,
    response_format="json_object",
)

PDF_VISION = DeepSeekTaskProfile(
    name="pdf_vision",
    output="markdown",
    images=True,
    max_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
    prefer_files=True,
)

FORMAT_REPAIR = DeepSeekTaskProfile(
    name="format_repair",
    output="markdown",
    images=False,
    max_tokens=8192,
)

CORRECTION_REVIEW = DeepSeekTaskProfile(
    name="correction_review",
    output="json",
    images=False,
    max_tokens=4096,
    response_format="json_object",
)

VISION_VERIFY = DeepSeekTaskProfile(
    name="vision_verify",
    output="json",
    images=True,
    max_tokens=4096,
    prefer_files=False,
    response_format="json_object",
)

PROFILES = {
    DAILY_VISION.name: DAILY_VISION,
    PDF_VISION.name: PDF_VISION,
    FORMAT_REPAIR.name: FORMAT_REPAIR,
    CORRECTION_REVIEW.name: CORRECTION_REVIEW,
    VISION_VERIFY.name: VISION_VERIFY,
}


def get_profile(name: str | DeepSeekTaskProfile | None) -> DeepSeekTaskProfile:
    if isinstance(name, DeepSeekTaskProfile):
        return name
    if not name:
        return PDF_VISION
    return PROFILES.get(str(name), PDF_VISION)
