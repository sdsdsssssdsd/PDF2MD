"""高风险 patch 的源图 Vision 核验（Phase D）。"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Literal

VisionChoice = Literal["before", "after", "uncertain"]

VISION_MODEL_DEFAULT = "deepseek-v4-flash-vision-exp"

_VERIFY_PROMPT = """你是学术 PDF 公式 OCR 核验器。
根据图片中的局部公式/符号，判断下列两个候选哪一个更贴近原图。
禁止推导、禁止改写、禁止补充图片中没有的内容。
只返回 JSON：{"choice":"before"|"after"|"uncertain","confidence":0.0-1.0,"reason":"..."}

候选 A (before):
{candidate_before}

候选 B (after):
{candidate_after}

上下文:
{context}
"""


def patch_needs_vision(before: str, after: str, *, gate_reason: str) -> bool:
    if gate_reason in {"number_mismatch", "operator_mismatch"}:
        return True
    if _numbers(before) != _numbers(after):
        return True
    if _operators(before) != _operators(after):
        return True
    return False


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_OPERATOR_CHARS = frozenset("<>≤≥=≠∈∉+-∓±")


def _numbers(text: str) -> list[str]:
    return _NUMBER_RE.findall(text or "")


def _operators(text: str) -> set[str]:
    return {ch for ch in (text or "") if ch in _OPERATOR_CHARS}


def render_pdf_snippet(
    pdf_path: Path,
    *,
    needle: str,
    max_pages: int = 12,
) -> Path | None:
    if not pdf_path.is_file() or not (needle or "").strip():
        return None
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            return None

    needle_raw = (needle or "").strip()[:24]
    needle_norm = re.sub(r"[\s\\$]", "", needle_raw)
    doc = pymupdf.open(str(pdf_path))
    try:
        limit = min(len(doc), max_pages)
        for page_idx in range(limit):
            page = doc[page_idx]
            page_text = page.get_text() or ""
            page_norm = re.sub(r"\s+", "", page_text)
            if needle_norm and needle_norm[:8] not in page_norm and needle_raw[:6] not in page_text:
                continue
            pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            tmp = Path(tempfile.gettempdir()) / f"pdf2md_corr_{page_idx}_{pdf_path.stem}.png"
            pix.save(str(tmp))
            return tmp
    finally:
        doc.close()
    return None


def pick_verification_image(
    *,
    pdf_path: Path | None,
    source_images: list[Path],
    needle: str,
) -> Path | None:
    for img in source_images:
        p = Path(img)
        if p.is_file():
            return p
    if pdf_path is not None:
        return render_pdf_snippet(pdf_path, needle=needle)
    return None


def verify_patch(
    image_path: Path,
    *,
    before: str,
    after: str,
    left_context: str = "",
    right_context: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    from app.vision_api.client import DeepSeekVisionClient

    client = DeepSeekVisionClient()
    vision_model = model or VISION_MODEL_DEFAULT
    context = f"{left_context[-200:]}\n...\n{right_context[:200]}"
    prompt = _VERIFY_PROMPT.format(
        candidate_before=before,
        candidate_after=after,
        context=context,
    )
    old_model = client.config.model
    try:
        client.config.model = vision_model
        result = client.transcribe([Path(image_path)], prompt)
        text = (result.markdown or "").strip()
    finally:
        client.config.model = old_model

    if not text:
        return {"choice": "uncertain", "confidence": 0.0, "reason": "empty_response"}
    blob = text
    if "{" in text and "}" in text:
        blob = text[text.find("{") : text.rfind("}") + 1]
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return {"choice": "uncertain", "confidence": 0.0, "reason": "invalid_json"}
    if not isinstance(parsed, dict):
        return {"choice": "uncertain", "confidence": 0.0, "reason": "invalid_shape"}
    choice = str(parsed.get("choice") or "uncertain").lower()
    if choice not in {"before", "after", "uncertain"}:
        choice = "uncertain"
    return {
        "choice": choice,
        "confidence": float(parsed.get("confidence") or 0),
        "reason": str(parsed.get("reason") or ""),
        "model": vision_model,
    }


def verify_and_resolve(
    *,
    image_path: Path,
    before: str,
    after: str,
    left_context: str = "",
    right_context: str = "",
    model: str | None = None,
    min_confidence: float = 0.85,
) -> VisionChoice:
    result = verify_patch(
        image_path,
        before=before,
        after=after,
        left_context=left_context,
        right_context=right_context,
        model=model,
    )
    if float(result.get("confidence") or 0) < min_confidence:
        return "uncertain"
    choice = str(result.get("choice") or "uncertain").lower()
    if choice not in {"before", "after", "uncertain"}:
        return "uncertain"
    return choice  # type: ignore[return-value]
