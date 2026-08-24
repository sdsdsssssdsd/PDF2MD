# -*- coding: utf-8 -*-
"""k5 四层 Gate：Geometry / Syntax / Render / Consensus。宁可不写回。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.formula.consensus import ConsensusResult, dual_model_consensus
from app.ocr.match_eval_v2 import compile_rate_ok

RiskLevel = Literal["low", "medium", "high"]
WriteDecision = Literal["accept", "abstain"]


@dataclass
class RiskAssessment:
    geometry_ok: bool = True
    syntax_ok: bool = True
    render_ok: bool = True
    consensus: str = "INCOMPLETE"
    risk: RiskLevel = "high"
    decision: WriteDecision = "abstain"
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_geometry(
    *,
    page: int | None,
    bbox: tuple[float, float, float, float] | list[float] | None,
    crop_class: str = "",
    page_width: float | None = None,
    page_height: float | None = None,
    edge_margin: float = 4.0,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if page is None:
        reasons.append("missing_page")
    if bbox is None or len(bbox) < 4:
        reasons.append("missing_bbox")
        return False, reasons
    x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    if x1 <= x0 or y1 <= y0:
        reasons.append("degenerate_bbox")
    if crop_class in {"likely_prose", "likely_table"}:
        reasons.append(f"suspicious_crop:{crop_class}")
    if page_width and (x0 < edge_margin or x1 > page_width - edge_margin):
        reasons.append("bbox_near_x_edge")
    if page_height and (y0 < edge_margin or y1 > page_height - edge_margin):
        reasons.append("bbox_near_y_edge")
    return len(reasons) == 0, reasons


def assess_formula_risk(
    *,
    latex: str,
    page: int | None = None,
    bbox: tuple[float, float, float, float] | list[float] | None = None,
    crop_class: str = "",
    peer_latex: str | None = None,
    consensus: ConsensusResult | None = None,
    page_width: float | None = None,
    page_height: float | None = None,
    require_consensus: bool = False,
) -> RiskAssessment:
    reasons: list[str] = []
    geo_ok, geo_rs = assess_geometry(
        page=page,
        bbox=bbox,
        crop_class=crop_class,
        page_width=page_width,
        page_height=page_height,
    )
    reasons.extend(geo_rs)

    syntax_ok = bool((latex or "").strip()) and compile_rate_ok(latex)
    if not syntax_ok:
        reasons.append("syntax_or_compile_fail")

    render_ok = syntax_ok
    if not render_ok:
        reasons.append("render_untrusted")

    cons = consensus
    if cons is None and peer_latex is not None:
        cons = dual_model_consensus(latex, peer_latex)
    cons_dec = cons.decision if cons is not None else "INCOMPLETE"
    if require_consensus and cons_dec not in {"ACCEPT", "ACCEPT_VISUAL"}:
        reasons.append("no_dual_consensus")

    if geo_ok and syntax_ok and render_ok:
        if cons_dec in {"ACCEPT", "ACCEPT_VISUAL"} or (
            not require_consensus and cons is None
        ):
            return RiskAssessment(
                geometry_ok=True,
                syntax_ok=True,
                render_ok=True,
                consensus=cons_dec,
                risk="low",
                decision="accept",
                reasons=reasons or ["all_layers_ok"],
            )
        if cons_dec == "DISAGREE":
            return RiskAssessment(
                geometry_ok=True,
                syntax_ok=True,
                render_ok=True,
                consensus=cons_dec,
                risk="high",
                decision="abstain",
                reasons=reasons + ["consensus_disagree"],
            )
        return RiskAssessment(
            geometry_ok=True,
            syntax_ok=True,
            render_ok=True,
            consensus=cons_dec,
            risk="medium",
            decision="abstain" if require_consensus else "accept",
            reasons=reasons or ["single_model_no_peer"],
        )

    return RiskAssessment(
        geometry_ok=geo_ok,
        syntax_ok=syntax_ok,
        render_ok=render_ok,
        consensus=cons_dec,
        risk="high",
        decision="abstain",
        reasons=reasons or ["high_risk"],
    )
