"""Fallback：仅 RECOVERY_FAILED 后调用。

生产默认 clean：**必须留下可见占位**，禁止静默删除公式
（否则 Eq.(4) 后整块空白，读者无法发现失败）。
详细诊断仍写入 formula_qa.json。
"""
from __future__ import annotations

from app.formula.config import FormulaConfig
from app.formula.types import FormulaCandidate

_DEFAULT_VISIBLE = (
    "*[公式未能可靠提取 / Formula extraction failed"
    "{reason_part}. 详见同目录 `*.formula_qa.json`]*"
)


def fallback_markup(candidate: FormulaCandidate, cfg: FormulaConfig | None = None) -> str:
    """返回应写入 Markdown 的字符串；clean/strict 也必须可见。"""
    cfg = cfg or FormulaConfig()
    mode = (cfg.fallback_mode or "clean").lower()
    reason = ",".join(candidate.issues[:3]) if candidate.issues else "recovery_failed"

    if mode == "debug":
        page = f"\npage={candidate.page}" if candidate.page is not None else ""
        bbox = f"\nbbox={candidate.bbox}" if candidate.bbox is not None else ""
        return (
            f"<!-- formula-not-decoded{page}{bbox}\n"
            f"reason={reason}\n"
            f"attempts={candidate.recovery_attempts}\n"
            f"-->\n"
            f"*[公式未能可靠提取 — `{reason}`]*"
        )

    # clean / strict：正文可见报错，不吞掉公式位置
    placeholder = (cfg.clean_placeholder or "").strip()
    if placeholder:
        try:
            return placeholder.format(reason=reason)
        except (KeyError, ValueError, IndexError):
            return placeholder
    reason_part = f" — `{reason}`" if reason else ""
    return _DEFAULT_VISIBLE.format(reason_part=reason_part)


def infer_failure_stage(
    candidate: FormulaCandidate,
    *,
    gate_reason: str = "",
) -> str:
    """k3：公式失败主归因（geometry / crop_prose / ocr / gate / writeback）。"""
    if getattr(candidate, "failure_stage", ""):
        return str(candidate.failure_stage)

    issues = ",".join(candidate.issues or [])
    reason = gate_reason or issues
    parts = {p.strip() for p in reason.split(",") if p.strip()}
    crop = (getattr(candidate, "crop_class", "") or "").lower()

    if not candidate.page or not candidate.bbox:
        return "geometry"
    if crop in {"likely_prose", "likely_table"} or "crop_hits" in issues:
        return "crop_prose"
    if crop == "likely_too_small":
        return "geometry"
    if "ocr_context_conflict" in parts:
        return "gate"
    if parts & {
        "insufficient_without_strong_evidence",
        "ocr_context_insufficient",
        "low_gain",
        "syntax_invalid",
    }:
        return "gate"
    if parts & {
        "no_equation_blocks",
        "ocr_result_bad",
        "ocr_empty",
        "ocr_timeout",
        "no_ocr",
    } or any(
        p.startswith("ocr_") and p != "ocr_context_insufficient" for p in parts
    ):
        return "ocr"
    if parts & {"writeback", "identity", "page_mismatch", "candidate_id"}:
        return "writeback"
    if "no_bbox" in parts or "docling_formula_not_decoded" in parts:
        if candidate.bbox:
            return "ocr"
        return "geometry"
    if candidate.recovery_attempts > 0 and candidate.status == "recovery_failed":
        return "gate"
    return "ocr"


def failure_record(
    candidate: FormulaCandidate,
    *,
    gate_reason: str = "",
) -> dict:
    stage = infer_failure_stage(candidate, gate_reason=gate_reason)
    return {
        "page": candidate.page,
        "bbox": candidate.bbox,
        "block_id": None,
        "candidate_id": getattr(candidate, "candidate_id", "") or "",
        "reason": ",".join(candidate.issues[:6]) if candidate.issues else "recovery_failed",
        "failure_stage": stage,
        "crop_class": getattr(candidate, "crop_class", "") or "",
        "geometry_source": getattr(candidate, "geometry_source", "") or "",
        "raw": (candidate.raw_text or candidate.text or "")[:500],
        "attempts": candidate.recovery_attempts,
        "recovery_log": candidate.recovery_log,
        "lifecycle": getattr(candidate.lifecycle, "value", str(candidate.lifecycle)),
        "display_mode": candidate.display_mode,
        "equation_number": getattr(candidate, "equation_number", "") or "",
        "context_before": candidate.context_before[-200:],
        "context_after": (candidate.context_after or "")[:200],
    }
