"""可选 DeepSeek 复检器。"""
from __future__ import annotations

from typing import Any

from app.deepseek_api.config import DEFAULT_MODEL
from app.deepseek_api.profiles import CORRECTION_REVIEW
from app.format_repair.prompts import build_review_messages

MODELS = {
    "fast": DEFAULT_MODEL,
    "strict": DEFAULT_MODEL,
}


def review_format_issues(
    issues: list[dict],
    *,
    model_name: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    from app.deepseek_api.client import DeepSeekClient

    client = DeepSeekClient()
    messages = build_review_messages(issues)
    return client.chat_json(
        messages, model=model_name, max_tokens=4096, profile=CORRECTION_REVIEW
    )


def review_display_decisions(
    blocks: list[dict],
    *,
    model_name: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    from app.deepseek_api.client import DeepSeekClient

    client = DeepSeekClient()
    system = (
        "你是 Markdown 数学排版审计器。只判断传入的 display formula "
        "是否适合转换为行内公式。不得修改公式内容。"
    )
    user = (
        "输出 JSON：{\"decisions\":[{\"index\":0,\"decision\":\"inline\","
        "\"confidence\":0.9}]}。"
        f"\n\n{blocks}"
    )
    return client.chat_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=model_name,
        max_tokens=4096,
        profile=CORRECTION_REVIEW,
    )
