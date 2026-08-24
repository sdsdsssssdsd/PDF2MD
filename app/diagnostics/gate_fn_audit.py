# -*- coding: utf-8 -*-
"""Phase 7.3A：Gate false-negative 只读审计（不改 Gate 行为）。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.diagnostics.anomaly_detector import assess_anomaly
from app.formula.gain import evaluate_recovery_gain, looks_truncated
from app.formula.types import FormulaQuality
from app.formula.validator import validate_latex

_HALLUC = re.compile(
    r"\b(?:lorem|ipsum|as an ai|i cannot|sorry)\b|"
    r"(?:sinn|cosn)\b|"
    r"the following table shows",
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


def _context_status(gate_reason: str) -> str:
    g = gate_reason or ""
    if "ocr_context_conflict" in g:
        return "conflict"
    if "ocr_context_insufficient" in g:
        return "insufficient"
    if "accept_despite_insufficient" in g:
        return "insufficient_accepted"
    return "other"


def classify_fn_bucket(
    *,
    latex: str,
    valid: bool,
    corruption: float,
    truncated: bool,
    context_status: str,
    gate_accepted: bool,
    number_status: str,
    eq_number: str,
) -> str | None:
    """返回 FN 细分桶；context_conflict 永不进 FN。"""
    if context_status == "conflict":
        return None  # 硬拒，不混入 FN
    if gate_accepted:
        return None
    if context_status not in {"insufficient", "insufficient_accepted"}:
        return None
    if not latex.strip():
        return None

    numbered = bool(eq_number) or number_status == "numbered_confirmed"
    unnumbered = number_status == "unnumbered_confirmed" or (
        not eq_number and number_status != "numbered_confirmed"
    )

    if valid and corruption <= 0.45 and not truncated:
        base = "clean_latex+validation_pass+context_insufficient"
    elif valid and corruption <= 0.45 and truncated:
        base = "clean_latex+validation_pass+false_truncated_flag+context_insufficient"
    elif valid and truncated:
        base = "valid_but_truncated_flag+context_insufficient"
    else:
        base = "context_insufficient_other"

    if numbered:
        return f"numbered::{base}"
    if unnumbered:
        return f"unnumbered::{base}"
    return base


def audit_gate_fn_row(row: dict[str, Any], *, attempt_index: int = 0) -> dict[str, Any]:
    latex = str(row.get("selected_latex") or row.get("recovered") or "").strip()
    raw = str(row.get("raw_output") or "")
    gate_reason = str(row.get("gate_reason") or "")
    accepted = bool(row.get("gate_accepted"))
    ctx = _context_status(gate_reason)
    assess = assess_anomaly(row)

    vr = validate_latex(latex) if latex else None
    valid = bool(vr.valid) if vr else False
    q = vr.quality if vr else None
    corr = float(q.corruption_score) if q else 1.0
    trunc = looks_truncated(latex) if latex else False
    hallu = bool(_HALLUC.search(raw) or _HALLUC.search(latex))

    # 反事实：若去掉 truncated 误判，insufficient 路径是否会 accept
    counterfactual_accept = False
    counterfactual_reasons: list[str] = []
    if latex and ctx == "insufficient" and not accepted:
        after_q = FormulaQuality(
            corruption_score=corr,
            syntax_score=float(q.syntax_score) if q else 0.0,
            semantic_score=float(q.semantic_score) if q else 0.0,
            valid=valid,
        )
        # 用占位 before + 空指标上下文触发 insufficient；并人为绕过 trunc 检测
        # 通过把 trailing comma 去掉模拟「非截断」
        latex_cf = latex.rstrip().rstrip(",")
        # cases 环境：不在这里「修」括号，只测 trailing comma 场景
        vr2 = validate_latex(latex_cf)
        g = evaluate_recovery_gain(
            before_quality=FormulaQuality(corruption_score=0.95, valid=False),
            after_quality=vr2.quality,
            before_latex="<!-- formula-not-decoded -->",
            after_latex=latex_cf,
            context_before="see clustering details in the text.",
            context_after="",
            after_valid=bool(latex_cf) and bool(vr2.valid),
        )
        counterfactual_accept = bool(g.accept)
        counterfactual_reasons = list(g.reasons)

    eq = str(row.get("eq_number") or "").strip()
    # shadow 行通常无 number_status；用 eq 近似
    number_status = "numbered_confirmed" if eq else "unnumbered_confirmed"

    bucket = classify_fn_bucket(
        latex=latex,
        valid=valid,
        corruption=corr,
        truncated=trunc,
        context_status=ctx,
        gate_accepted=accepted,
        number_status=number_status,
        eq_number=eq,
    )

    safe_accept_candidate = bool(
        (not accepted)
        and ctx == "insufficient"
        and valid
        and corr <= 0.45
        and not hallu
        and (
            (not trunc)
            or counterfactual_accept
            or bucket
            and "false_truncated_flag" in (bucket or "")
        )
    )

    cid = row.get("candidate_id")
    if not cid and isinstance(row.get("timing"), dict):
        cid = row["timing"].get("candidate_id")

    return {
        "attempt_index": attempt_index,
        "candidate_id": cid,
        "page": row.get("page"),
        "eq_number": eq,
        "selected_latex": latex[:300],
        "validation_status": "pass" if valid else "fail",
        "corruption_score": round(corr, 4),
        "looks_truncated": trunc,
        "identity_status": "unknown_in_sidecar",  # 当前 would_replace 未持久化
        "number_status": number_status,
        "context_status": ctx,
        "gate_reason": gate_reason,
        "failure_class": row.get("failure_class"),
        "extractor_method": row.get("extractor_method"),
        "salvage_used": bool(row.get("salvage_used")),
        "accepted": accepted,
        "hallucination_signal": hallu,
        "anomaly_class": assess.anomaly_class,
        "actionability": assess.actionability,
        "fn_bucket": bucket,
        "safe_accept_candidate": safe_accept_candidate,
        "counterfactual_strip_comma_accept": counterfactual_accept,
        "counterfactual_reasons": counterfactual_reasons,
        "ocr_seconds": round(_ocr_seconds(row), 3),
        "raw_preview": re.sub(r"\s+", " ", raw)[:180],
    }


def audit_gate_fn_rows(
    rows: list[dict[str, Any]],
    *,
    document_id: str = "",
) -> dict[str, Any]:
    detailed = [
        audit_gate_fn_row(r, attempt_index=i)
        for i, r in enumerate(rows or [], start=1)
    ]
    fns = [d for d in detailed if d.get("fn_bucket")]
    safe = [d for d in detailed if d.get("safe_accept_candidate")]
    conflicts = [
        d
        for d in detailed
        if d.get("context_status") == "conflict" and not d.get("accepted")
    ]
    buckets: dict[str, int] = {}
    for d in fns:
        b = str(d.get("fn_bucket"))
        buckets[b] = buckets.get(b, 0) + 1

    safe_secs = sum(float(d["ocr_seconds"]) for d in safe)
    # 7.3B 建议门槛
    recommend_73b = len(safe) >= 2 and all(
        d.get("context_status") == "insufficient" for d in safe
    )

    return {
        "document": document_id,
        "n_attempts": len(detailed),
        "fn_count": len(fns),
        "safe_accept_candidate_count": len(safe),
        "safe_accept_ocr_seconds": round(safe_secs, 3),
        "context_conflict_rejects": len(conflicts),
        "fn_buckets": buckets,
        "safe_accept_candidates": safe,
        "all_insufficient_rejects": [
            d for d in detailed if d.get("context_status") == "insufficient" and not d["accepted"]
        ],
        "recommend_73b_narrow_fix": recommend_73b,
        "rationale": (
            f"safe_accept_candidates={len(safe)} "
            f"(need >=2 stable insufficient+clean); "
            f"conflict_rejects={len(conflicts)} kept as HARD REJECT"
        ),
        "rows": detailed,
    }


def audit_experiment_roots(roots: list[Path] | None = None) -> dict[str, Any]:
    from app.utils.paths import EXPERIMENT_DIR, ensure_dirs

    ensure_dirs()
    roots = roots or [EXPERIMENT_DIR]
    docs: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for qa in sorted(root.rglob("*.formula_qa.json")):
            try:
                data = json.loads(qa.read_text(encoding="utf-8"))
            except Exception:
                continue
            sm = (data.get("deepseek_shadow") or {}).get("summary") or {}
            rows = sm.get("would_replace") or []
            if not rows:
                continue
            doc = qa.name.replace(".formula_qa.json", "")
            docs.append(audit_gate_fn_rows(rows, document_id=doc))

    safe_total = sum(int(d["safe_accept_candidate_count"]) for d in docs)
    docs_with_safe = [d["document"] for d in docs if d["safe_accept_candidate_count"] > 0]
    return {
        "documents_scanned": len(docs),
        "documents_with_safe_fn": docs_with_safe,
        "safe_accept_candidate_total": safe_total,
        "per_document": docs,
        "cross_doc_recommend_73b": safe_total >= 2 and len(docs_with_safe) >= 1,
    }


def main() -> None:
    import sys

    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        qa = json.loads(path.read_text(encoding="utf-8"))
        sm = (qa.get("deepseek_shadow") or {}).get("summary") or {}
        out = audit_gate_fn_rows(
            sm.get("would_replace") or [],
            document_id=path.name.replace(".formula_qa.json", ""),
        )
    else:
        out = audit_experiment_roots()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
