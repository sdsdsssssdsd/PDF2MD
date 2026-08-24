# -*- coding: utf-8 -*-
"""Append harvest reviews for harvest-520 batch (16). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p4_eq13_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "left-clipped delay-term continuation",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p4_eq14_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "left-clipped delay-term continuation",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p4_eq15_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "left-clipped delay-term continuation",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq00_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Lyapunov fragment, not a numbered display equation",
    },
    {
        "id": "45_RoFormer_p5_eq19_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "non-negative functions sentence above (19)",
    },
    {
        "id": "45_RoFormer_p5_eq20_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{q}_{m}=f_{q}(\boldsymbol{x}_{q},m),\quad\boldsymbol{k}_{n}=f_{k}(\boldsymbol{x}_{k},n),",
        "equation_number": "20",
        "notes": "human_from_harvest; complete polar q/k maps",
    },
    {
        "id": "45_RoFormer_p5_eq23_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "decompose Equations (20)(21) lead-in and where below",
    },
    {
        "id": "45_RoFormer_p5_eq24_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "we get the relation lead-in above (24)",
    },
    {
        "id": "45_RoFormer_p6_eq25_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{q}=\|\boldsymbol{q}\|e^{i\theta_{q}}=R_{q}(\boldsymbol{x}_{q},0)e^{i\Theta_{q}(\boldsymbol{x}_{q},0)},\quad\boldsymbol{k}=\|\boldsymbol{k}\|e^{i\theta_{k}}=R_{k}(\boldsymbol{x}_{k},0)e^{i\Theta_{k}(\boldsymbol{x}_{k},0)},",
        "equation_number": "25",
        "notes": "human_from_harvest; complete polar q/k at origin",
    },
    {
        "id": "45_RoFormer_p6_eq26a_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "(26a) stacked with (26b)",
    },
    {
        "id": "45_RoFormer_p6_eq26b_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "(26b) stacked with leftover R identities",
    },
    {
        "id": "45_RoFormer_p6_eq27_h",
        "action": "verify",
        "gold_latex_raw": r"R_{q}(\mathbf{x}_{q},m)=R_{q}(\mathbf{x}_{q},0)=\|\mathbf{q}\|,\quad R_{k}(\mathbf{x}_{k},n)=R_{k}(\mathbf{x}_{k},0)=\|\mathbf{k}\|,\quad R_{g}(\mathbf{x}_{q},\mathbf{x}_{k},n-m)=R_{g}(\mathbf{x}_{q},\mathbf{x}_{k},0)=\|\mathbf{q}\|\|\mathbf{k}\|,",
        "equation_number": "27",
        "notes": "human_from_harvest; complete radial invariance",
    },
    {
        "id": "45_RoFormer_p6_eq28_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "independent of word embedding sentence above (28)",
    },
    {
        "id": "45_RoFormer_p6_eq29_h",
        "action": "verify",
        "gold_latex_raw": r"\phi(m+1)-\phi(m)=\Theta_{g}(\boldsymbol{x}_{q},\boldsymbol{x}_{k},1)+\theta_{q}-\theta_{k},",
        "equation_number": "29",
        "notes": "human_from_harvest; complete phase increment",
    },
    {
        "id": "45_RoFormer_p6_eq30_h",
        "action": "verify",
        "gold_latex_raw": r"\phi(m)=m\theta+\gamma,",
        "equation_number": "30",
        "notes": "human_from_harvest; complete linear phase",
    },
    {
        "id": "45_RoFormer_p6_eq31_h",
        "action": "verify",
        "gold_latex_raw": r"f_{q}(\boldsymbol{x}_{q},m)=\|\boldsymbol{q}\|e^{i\theta_{q}+m\theta+\gamma}=\boldsymbol{q}e^{i(m\theta+\gamma)},\quad f_{k}(\boldsymbol{x}_{k},n)=\|\boldsymbol{k}\|e^{i\theta_{k}+n\theta+\gamma}=\boldsymbol{k}e^{i(n\theta+\gamma)}.",
        "equation_number": "31",
        "notes": "human_from_harvest; complete rotary closed form",
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
    spec["created_at"] = "2026-08-23T18:10:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
