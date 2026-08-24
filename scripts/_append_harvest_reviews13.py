# -*- coding: utf-8 -*-
"""Append harvest reviews for harvest-560 batch (13). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq20_h",
        "action": "reject",
        "crop_quality": ["clipped_left", "neighbor_eq"],
        "notes": "left-clipped Lyapunov continuation, incomplete brace",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq30_h",
        "action": "reject",
        "crop_quality": ["clipped_left", "neighbor_eq"],
        "notes": "left-clipped Lyapunov continuation, truncated after +",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq01_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq21_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq31_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq02_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq22_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped sum fragment plus line above",
    },
    {
        "id": "45_RoFormer_p6_eq32_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "define lead-in and Equation (31) sentence around (32)",
    },
    {
        "id": "45_RoFormer_p6_eq33_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "set gamma=0 in Equation (31) lead-in above (33)",
    },
    {
        "id": "45_RoFormer_p6_eq34_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{R}_{\Theta,m}^{d}\boldsymbol{x}=\begin{pmatrix}x_{1}\\x_{2}\\x_{3}\\x_{4}\\\vdots\\x_{d-1}\\x_{d}\end{pmatrix}\otimes\begin{pmatrix}\cos m\theta_{1}\\\cos m\theta_{1}\\\cos m\theta_{2}\\\cos m\theta_{2}\\\vdots\\\cos m\theta_{d/2}\\\cos m\theta_{d/2}\end{pmatrix}+\begin{pmatrix}-x_{2}\\x_{1}\\-x_{4}\\x_{3}\\\vdots\\-x_{d}\\x_{d-1}\end{pmatrix}\otimes\begin{pmatrix}\sin m\theta_{1}\\\sin m\theta_{1}\\\sin m\theta_{2}\\\sin m\theta_{2}\\\vdots\\\sin m\theta_{d/2}\\\sin m\theta_{d/2}\end{pmatrix}",
        "equation_number": "34",
        "notes": "human_from_harvest; complete sparse rotary-times-x expansion",
    },
    {
        "id": "45_RoFormer_p7_eq35_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where-clause and Denote h_i below (35)",
    },
    {
        "id": "45_RoFormer_p7_eq36_h",
        "action": "verify",
        "gold_latex_raw": r"\sum_{i=0}^{d/2-1}\boldsymbol{q}_{[2i:2i+1]}\boldsymbol{k}_{[2i:2i+1]}^{*}e^{i(m-n)\theta_{i}}=\sum_{i=0}^{d/2-1}h_{i}(S_{i+1}-S_{i})=-\sum_{i=0}^{d/2-1}S_{i+1}(h_{i+1}-h_{i}).",
        "equation_number": "36",
        "notes": "human_from_harvest; complete Abel rewrite of RoPE sum",
    },
    {
        "id": "45_RoFormer_p7_eq37_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Note that decay sentence below the (37) bound",
    },
]


def main() -> int:
    spec = json.loads(PATH.read_text(encoding="utf-8"))
    old_ids = {str(r.get("id") or "") for r in spec.get("reviews") or []}
    added = 0
    for rev in NEW:
        if rev["id"] in old_ids:
            raise SystemExit(f"duplicate review id: {rev['id']}")
        spec["reviews"].append(rev)
        added += 1
    spec["created_at"] = "2026-08-23T16:55:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
