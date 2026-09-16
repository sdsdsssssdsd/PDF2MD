"""DeepSeek API 局部 patch 审校。"""
from __future__ import annotations

import json
from typing import Any

from app.correction.models import CorrectionIssue, CorrectionPatch
from app.correction.prompt import build_batch_messages
from app.deepseek_api.config import DEFAULT_MODEL
from app.deepseek_api.profiles import CORRECTION_REVIEW

TEXT_MODELS = {
    "fast": DEFAULT_MODEL,
    "strict": DEFAULT_MODEL,
}


def review_issues(
    issues: list[CorrectionIssue],
    *,
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 20,
) -> dict[str, Any]:
    if not issues:
        return {"checked": 0, "edits": [], "uncertain": []}
    from app.deepseek_api.client import DeepSeekClient

    client = DeepSeekClient()
    all_edits: list[dict] = []
    uncertain: list[str] = []
    checked = 0
    for i in range(0, len(issues), batch_size):
        batch = issues[i : i + batch_size]
        payload = [
            {
                "issue_id": it.issue_id,
                "type": it.kind,
                "before": it.before,
                "left_context": it.left_context[-300:],
                "right_context": it.right_context[:300],
                "environment": it.environment,
                "suggested_after": it.after,
            }
            for it in batch
        ]
        messages = build_batch_messages(payload)
        fragment = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        from app.correction.cache import cache_get, cache_set

        cached = cache_get(fragment=fragment, issue_type="batch_review", model=model_name)
        if cached is not None:
            data = cached
        else:
            data = client.chat_json(
                messages, model=model_name, max_tokens=4096, profile=CORRECTION_REVIEW
            )
            cache_set(
                fragment=fragment,
                issue_type="batch_review",
                model=model_name,
                payload=data,
            )
        checked += len(batch)
        for item in (data.get("edits") or []):
            if isinstance(item, dict):
                all_edits.append(item)
        for item in (data.get("uncertain") or []):
            uncertain.append(str(item))
    return {
        "model": model_name,
        "checked": checked,
        "edits": all_edits,
        "uncertain": uncertain,
    }


def edits_to_patches(
    review: dict[str, Any],
    *,
    min_confidence: float = 0.85,
) -> list[CorrectionPatch]:
    patches: list[CorrectionPatch] = []
    for item in review.get("edits") or []:
        if not isinstance(item, dict):
            continue
        conf = float(item.get("confidence") or 0)
        if conf < min_confidence:
            continue
        before = str(item.get("before") or "")
        after = str(item.get("after") or "")
        if not before or before == after:
            continue
        patches.append(
            CorrectionPatch(
                issue_id=str(item.get("issue_id") or ""),
                before=before,
                after=after,
                source=str(review.get("model") or "deepseek"),
                confidence=conf,
                reason=str(item.get("reason") or item.get("category") or "api"),
            )
        )
    return patches
