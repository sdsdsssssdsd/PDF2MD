# -*- coding: utf-8 -*-
"""双模型共识：不要用单模型自信度当 accept。"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.ocr.match_eval_v2 import canonicalize_latex, try_compute_cdm

Decision = Literal["ACCEPT", "ACCEPT_VISUAL", "DISAGREE", "INCOMPLETE"]

_OVER = re.compile(r"\{([^{}]+)\\over([^{}]+)\}")


def _frac_alias(text: str) -> str:
    s = (text or "").strip().replace("$$", "").replace("$", "")
    s = re.sub(r"\{([^{}]+)\\over\s*([^{}]+)\}", r"\\frac{\1}{\2}", s)
    s = canonicalize_latex(s)
    s = s.replace(r"\cdot", "*").replace(r"\times", "*")
    return s


@dataclass
class ConsensusResult:
    decision: Decision
    a_canonical: str
    b_canonical: str
    visual_equivalent: bool = False
    cdm: float | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def dual_model_consensus(
    latex_a: str,
    latex_b: str,
    *,
    visual_cdm_threshold: float = 0.98,
) -> ConsensusResult:
    a = (latex_a or "").strip()
    b = (latex_b or "").strip()
    if not a or not b:
        return ConsensusResult(
            decision="INCOMPLETE",
            a_canonical=canonicalize_latex(a),
            b_canonical=canonicalize_latex(b),
            reason="missing_prediction",
        )
    ca, cb = canonicalize_latex(a), canonicalize_latex(b)
    if ca and ca == cb:
        return ConsensusResult(
            decision="ACCEPT",
            a_canonical=ca,
            b_canonical=cb,
            visual_equivalent=True,
            reason="canonical_exact",
        )
    if _frac_alias(a) and _frac_alias(a) == _frac_alias(b):
        return ConsensusResult(
            decision="ACCEPT_VISUAL",
            a_canonical=ca,
            b_canonical=cb,
            visual_equivalent=True,
            reason="frac_over_or_cdot_alias",
        )
    cdm = try_compute_cdm(a, b)
    if cdm is not None and cdm >= visual_cdm_threshold:
        return ConsensusResult(
            decision="ACCEPT_VISUAL",
            a_canonical=ca,
            b_canonical=cb,
            visual_equivalent=True,
            cdm=cdm,
            reason="cdm_similar",
        )
    return ConsensusResult(
        decision="DISAGREE",
        a_canonical=ca,
        b_canonical=cb,
        cdm=cdm,
        reason="models_differ",
    )
