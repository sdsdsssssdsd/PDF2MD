# -*- coding: utf-8 -*-
"""k5 §8 / §28.11：把 bbox 错和 OCR 错拆开。只用于 benchmark / shadow。"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.formula.risk import assess_formula_risk
from app.ocr.match_eval_v2 import FailureLayer, FormulaMatchEvaluatorV2, classify_production_failure

CropOcrLayer = Literal["OK", "CROP_CLIPPED", "OCR_FAILURE", "POSTPROCESS_FAILURE"]
ShadowOutcome = Literal[
    "true_accept",
    "false_accept",
    "abstain_correct",
    "abstain_miss",
    "no_gold",
]

_CONTAM = re.compile(
    r"("
    r"\\begin\{array\}|"
    r"\\intertext|"
    r"identified|calculated using|the model|"
    r"\\text\{tests\}|"
    r"Eq\.\s*\(\d+\)|"
    r"\\quad(\{\})?\\quad"
    r")",
    re.I,
)


def pred_looks_contaminated(pred: str) -> bool:
    text = pred or ""
    if text.count("(") >= 3 and "frac" in text and "quad" in text:
        return True
    return bool(_CONTAM.search(text))


def classify_crop_vs_ocr(
    *,
    exact_prod: bool,
    exact_tight: bool,
    prod_pred: str = "",
    tight_pred: str = "",
) -> tuple[CropOcrLayer, CropOcrLayer]:
    """同一模型：生产 crop vs 紧 crop。紧过、产不过 → 裁图问题，不要训练。"""
    if exact_tight and exact_prod:
        return "OK", "OK"
    if exact_tight and not exact_prod:
        return "CROP_CLIPPED", "OK"
    if not exact_tight and exact_prod:
        return "OK", "POSTPROCESS_FAILURE"
    tight = "OCR_FAILURE"
    if not (tight_pred or "").strip():
        tight = "OCR_FAILURE"
    prod: CropOcrLayer = "CROP_CLIPPED" if pred_looks_contaminated(prod_pred) else "OCR_FAILURE"
    return prod, tight


@dataclass
class ShadowWriteback:
    decision: str
    consensus: str
    gold_exact: bool | None
    outcome: ShadowOutcome
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def simulate_shadow_writeback(
    pred_a: str,
    pred_b: str,
    gold: str,
    *,
    page: int | None = 1,
    bbox: list[float] | None = None,
) -> ShadowWriteback:
    """双模型共识才写回。对照 Gold 算 precision，不写生产 Markdown。"""
    box = bbox if bbox and len(bbox) >= 4 else [10.0, 10.0, 80.0, 40.0]
    risk = assess_formula_risk(
        latex=pred_a,
        page=page,
        bbox=box,
        peer_latex=pred_b,
        require_consensus=True,
    )
    gold_s = (gold or "").strip()
    exact: bool | None = None
    if gold_s and (pred_a or "").strip():
        exact = FormulaMatchEvaluatorV2(compute_cdm=False).compare(pred_a, gold_s).strict_canonical_exact
    elif gold_s:
        exact = False

    if risk.decision == "accept":
        if exact is None:
            outcome: ShadowOutcome = "no_gold"
        elif exact:
            outcome = "true_accept"
        else:
            outcome = "false_accept"
    else:
        if exact is None:
            outcome = "no_gold"
        elif exact:
            outcome = "abstain_miss"
        else:
            outcome = "abstain_correct"

    return ShadowWriteback(
        decision=risk.decision,
        consensus=risk.consensus,
        gold_exact=exact,
        outcome=outcome,
        reasons=list(risk.reasons),
    )


def summarize_shadow(rows: list[ShadowWriteback]) -> dict[str, Any]:
    scored = [r for r in rows if r.outcome != "no_gold"]
    accepts = [r for r in scored if r.decision == "accept"]
    true_n = sum(1 for r in accepts if r.outcome == "true_accept")
    false_n = sum(1 for r in accepts if r.outcome == "false_accept")
    gold_n = len(scored)
    accept_n = len(accepts)
    return {
        "n_gold": gold_n,
        "auto_accept": accept_n,
        "true_accept": true_n,
        "false_accept": false_n,
        "abstain": gold_n - accept_n,
        "precision": round(true_n / accept_n, 4) if accept_n else None,
        "coverage": round(true_n / gold_n, 4) if gold_n else None,
        "note": "shadow_only; precision=true_accept/auto_accept; coverage=true_accept/n_gold",
    }


def layer_or_ok(*, exact: bool, pred: str, gold: str) -> FailureLayer:
    if not (gold or "").strip():
        return "NO_GOLD"
    if exact:
        return "OK"
    if not (pred or "").strip():
        return "EMPTY_CANDIDATE"
    return classify_production_failure(ocr_ok=False, exact=False)
