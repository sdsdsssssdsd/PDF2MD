# -*- coding: utf-8 -*-
"""Phase 7.2C-read：Post-OCR Actionability Audit（只读，不改恢复行为）。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.diagnostics.anomaly_detector import assess_anomaly
from app.ocr.failure_class import re_search_math

# 弱数学线索（不升格为 high actionable；仅观测）
_WEAK_MATH = re.compile(
    r"\barg\s*min\b|\barg\s*max\b|\bmin\b|\bmax\b|"
    r"[A-Za-z]\s*\([^)]*\)|"  # f(x) / VI(t,t')
    r"[≤≥≠≈∈∑∫∏√]|"
    r"\^\s*\{|\^\d|_\d|\\frac",
    re.I,
)


def _ocr_seconds(row: dict[str, Any]) -> float:
    timing = row.get("timing") if isinstance(row.get("timing"), dict) else {}
    return float(
        timing.get("ocr_seconds")
        or timing.get("worker_inference_seconds")
        or row.get("ocr_seconds")
        or 0.0
    )


def _raw_preview(raw: str, n: int = 160) -> str:
    t = re.sub(r"<\|[^|]+\|>", " ", raw or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n]


def audit_post_ocr_rows(
    rows: list[dict[str, Any]],
    *,
    document_id: str = "",
    numbered_front_n: int = 5,
) -> dict[str, Any]:
    """对 would_replace 行做 post-OCR actionability 审计。"""
    rows = list(rows or [])
    total_ocr = sum(_ocr_seconds(r) for r in rows)
    wasted_ocr = sum(_ocr_seconds(r) for r in rows if not r.get("gate_accepted"))

    detailed: list[dict[str, Any]] = []
    by_anomaly: dict[str, dict[str, float | int]] = {}
    extractor_missed_secs = 0.0
    no_eq_blocks_secs = 0.0
    numbered_front_extract_secs = 0.0
    numbered_front_missed_secs = 0.0

    for i, r in enumerate(rows, start=1):
        raw = str(r.get("raw_output") or "")
        selected = str(r.get("selected_latex") or r.get("recovered") or "").strip()
        gate = str(r.get("gate_reason") or "")
        fc = str(r.get("failure_class") or "")
        eq = str(r.get("eq_number") or "").strip()
        ocr_s = _ocr_seconds(r)
        mathy = re_search_math(raw)
        weak = bool(_WEAK_MATH.search(raw))
        assess = assess_anomaly(r)
        is_numbered = False
        if eq.isdigit():
            try:
                n = int(eq)
                is_numbered = not (1900 <= n <= 2100)
            except ValueError:
                is_numbered = True
        elif eq:
            is_numbered = True

        in_front = i <= int(numbered_front_n)
        entry = {
            "attempt_index": i,
            "eq_number": eq,
            "numbered": is_numbered,
            "in_numbered_front_window": in_front and is_numbered,
            "accepted": bool(r.get("gate_accepted")),
            "failure_class": fc,
            "gate_reason": gate,
            "extractor_method": r.get("extractor_method"),
            "salvage_used": bool(r.get("salvage_used")),
            "has_selected_latex": bool(selected),
            "re_search_math": mathy,
            "weak_math_heuristic": weak,
            "ocr_seconds": round(ocr_s, 3),
            "anomaly_class": assess.anomaly_class,
            "actionability": assess.actionability,
            "assess_reason": assess.reason,
            "raw_preview": _raw_preview(raw),
        }
        detailed.append(entry)

        if not r.get("gate_accepted"):
            key = assess.anomaly_class or fc or "unknown"
            bucket = by_anomaly.setdefault(
                key, {"count": 0, "ocr_seconds": 0.0, "actionability": assess.actionability}
            )
            bucket["count"] = int(bucket["count"]) + 1
            bucket["ocr_seconds"] = float(bucket["ocr_seconds"]) + ocr_s

        if assess.anomaly_class == "extractor_missed_valid_raw":
            extractor_missed_secs += ocr_s
            if in_front and is_numbered:
                numbered_front_missed_secs += ocr_s

        if "no_equation_blocks" in gate or "no_equation_blocks" in str(r.get("error") or ""):
            no_eq_blocks_secs += ocr_s

        if (
            in_front
            and is_numbered
            and not r.get("gate_accepted")
            and fc == "extraction_failure"
        ):
            numbered_front_extract_secs += ocr_s

    missed_share = (
        extractor_missed_secs / wasted_ocr if wasted_ocr > 1e-6 else 0.0
    )
    front_extract_share = (
        numbered_front_extract_secs / wasted_ocr if wasted_ocr > 1e-6 else 0.0
    )

    # 决策建议
    if missed_share >= 0.35:
        recommendation = "narrow_extractor_fix"
        rationale = (
            f"extractor_missed_valid_raw 占 wasted OCR {missed_share:.0%} ≥ 35%"
        )
    elif front_extract_share >= 0.25 and missed_share < 0.15:
        recommendation = "sequential_ranking_or_crop_quality"
        rationale = (
            f"numbered 前排 extraction_failure 占 wasted {front_extract_share:.0%}，"
            f"但 extractor_missed_valid_raw 仅 {missed_share:.0%}："
            f"raw 多半不是可抽取数学（no_equation_blocks / 散文），"
            f"优先 7.2D sequential 或查 crop，而非扩 extractor"
        )
    else:
        recommendation = "sequential_ranking_72d"
        rationale = (
            f"extractor_missed_valid_raw 仅 {missed_share:.0%} wasted，"
            f"不达 30–35% 门槛 → 进入 7.2D Sequential Ranking（只 reorder 不 stop）"
        )

    return {
        "document": document_id,
        "n_attempts": len(rows),
        "total_ocr_seconds": round(total_ocr, 3),
        "wasted_ocr_seconds": round(wasted_ocr, 3),
        "extractor_missed_valid_raw_seconds": round(extractor_missed_secs, 3),
        "extractor_missed_share_of_wasted": round(missed_share, 4),
        "no_equation_blocks_seconds": round(no_eq_blocks_secs, 3),
        "numbered_front_extraction_failure_seconds": round(
            numbered_front_extract_secs, 3
        ),
        "numbered_front_extraction_share_of_wasted": round(front_extract_share, 4),
        "numbered_front_missed_valid_raw_seconds": round(
            numbered_front_missed_secs, 3
        ),
        "by_anomaly_class": {
            k: {
                "count": int(v["count"]),
                "ocr_seconds": round(float(v["ocr_seconds"]), 3),
                "actionability": v["actionability"],
            }
            for k, v in sorted(
                by_anomaly.items(), key=lambda kv: -float(kv[1]["ocr_seconds"])
            )
        },
        "rows": detailed,
        "recommendation": recommendation,
        "rationale": rationale,
        "thresholds": {
            "extractor_fix_if_missed_share_ge": 0.35,
            "note": "7.2C-read only; no behavior change",
        },
    }


def audit_formula_qa_path(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    qa = json.loads(path.read_text(encoding="utf-8"))
    sm = (qa.get("deepseek_shadow") or {}).get("summary") or {}
    rows = sm.get("would_replace") or []
    doc = path.name.replace(".formula_qa.json", "")
    return audit_post_ocr_rows(rows, document_id=doc)


def main() -> None:
    import sys

    target = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("logs/experiment/O-003_Peach2019_DataDrivenClustering")
        / "O-003_Peach2019_DataDrivenClustering.formula_qa.json"
    )
    if target.is_dir():
        cands = list(target.glob("*.formula_qa.json"))
        target = cands[0] if cands else target
    out = audit_formula_qa_path(target)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
