"""Copy / 多源抽取共识（P0：2-of-3）。"""
from __future__ import annotations

import hashlib

from app.vision_transcribe.transcript_quality import pick_best_transcript, transcript_rank


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def pick_copy_consensus(
    rounds: list[tuple[str, str]],
) -> tuple[str, str, bool, str]:
    """从多轮 (source_label, text) 中 2-of-3 择优。

    返回 (label, text, stable, failure_class)。
    """
    valid = [(label, (t or "").strip()) for label, t in rounds if (t or "").strip()]
    if not valid:
        return "", "", False, "COPY_NOT_FIRED"

    buckets: dict[str, list[tuple[str, str]]] = {}
    for label, text in valid:
        buckets.setdefault(content_hash(text), []).append((label, text))

    best_hash = max(buckets.keys(), key=lambda h: len(buckets[h]))
    group = buckets[best_hash]
    text = group[0][1]
    labels = [g[0] for g in group]

    if len(group) >= 2:
        label = "+".join(sorted(set(labels)))
        return label, text, True, ""

    if len(valid) >= 2:
        lengths = [len(t) for _, t in valid]
        if max(lengths) - min(lengths) > max(800, int(max(lengths) * 0.08)):
            return valid[0][0], valid[0][1], False, "EXTRACTION_UNSTABLE"

    return valid[0][0], valid[0][1], False, ""


def diagnose_transport_mismatch(
    *,
    copy_api_text: str,
    clipboard_text: str,
    dom_text: str = "",
) -> str:
    """诊断剪贴板通道问题（执行3 §十四）。"""
    api = (copy_api_text or "").strip()
    clip = (clipboard_text or "").strip()
    dom = (dom_text or "").strip()
    if api and clip and len(api) > len(clip) + max(800, int(len(api) * 0.05)):
        return "CLIPBOARD_TRUNCATED"
    if api and dom and len(dom) > len(api) + max(1200, int(len(api) * 0.08)):
        if len(api) >= len(clip) - 200:
            return "COPY_SOURCE_TRUNCATED"
    return ""


def pick_extraction_consensus(
    *,
    copy_text: str,
    dom_md: str,
    dom_katex: str,
    html_md: str = "",
) -> tuple[str, str]:
    """Copy 共识通过后，与 DOM 等证据择优（禁止静默丢式）。"""
    copy_s = (copy_text or "").strip()
    if copy_s:
        rank = transcript_rank(copy_s)
        if rank >= 0:
            return "copy-consensus", copy_s
    return pick_best_transcript(
        ("dom-md", (dom_md or "").strip()),
        ("dom-katex", (dom_katex or "").strip()),
        ("clipboard-html", (html_md or "").strip()),
        ("copy-consensus", copy_s),
    )
