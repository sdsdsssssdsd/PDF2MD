# -*- coding: utf-8 -*-
"""Append harvest reviews for harvest-460 batch (12). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p4_eq12_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "left-clipped continuation ending in a trailing minus",
    },
    {
        "id": "42_DPO_p15_eq19_h",
        "action": "verify",
        "gold_latex_raw": r"p^{*}(\tau|y_{1},\dots,y_{K},x)=\prod_{k=1}^{K}\frac{\exp\left(\beta\log\frac{\pi^{*}(y_{\tau(k)}|x)}{\pi_{\mathrm{ref}}(y_{\tau(k)}|x)}\right)}{\sum_{j=k}^{K}\exp\left(\beta\log\frac{\pi^{*}(y_{\tau(j)}|x)}{\pi_{\mathrm{ref}}(y_{\tau(j)}|x)}\right)}",
        "equation_number": "19",
        "notes": "human_from_harvest; complete Plackett-Luce from optimal policy",
    },
    {
        "id": "42_DPO_p16_eq20_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "ranking-dataset paragraph above (20)",
    },
    {
        "id": "42_DPO_p16_eq21_h",
        "action": "verify",
        "gold_latex_raw": r"\nabla_{\theta}\mathcal{L}_{\mathrm{DPO}}(\pi_{\theta};\pi_{\mathrm{ref}})=-\nabla_{\theta}\mathbb{E}_{(x,y_{w},y_{l})\sim\mathcal{D}}\left[\log\sigma\left(\beta\log\frac{\pi_{\theta}(y_{l}|x)}{\pi_{\mathrm{ref}}(y_{l}|x)}-\beta\log\frac{\pi_{\theta}(y_{w}|x)}{\pi_{\mathrm{ref}}(y_{w}|x)}\right)\right]",
        "equation_number": "21",
        "notes": "human_from_harvest; complete DPO gradient",
    },
    {
        "id": "42_DPO_p16_eq22_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where defines u below (22)",
    },
    {
        "id": "45_RoFormer_p3_eq22_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "rotation-W product without x; leftover of (13)/(21)",
    },
    {
        "id": "45_RoFormer_p3_eq13_h",
        "action": "verify",
        "gold_latex_raw": r"f_{\{q,k\}}(\mathbf{x}_{m},m)=\begin{pmatrix}\cos m\theta&-\sin m\theta\\\sin m\theta&\cos m\theta\end{pmatrix}\begin{pmatrix}W_{\{q,k\}}^{(11)}&W_{\{q,k\}}^{(12)}\\W_{\{q,k\}}^{(21)}&W_{\{q,k\}}^{(22)}\end{pmatrix}\begin{pmatrix}x_{m}^{(1)}\\x_{m}^{(2)}\end{pmatrix}",
        "equation_number": "13",
        "notes": "human_from_harvest; complete 2D rotary with W and x",
    },
    {
        "id": "45_RoFormer_p4_eq14_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "complete (14) sitting above clipped (15)",
    },
    {
        "id": "45_RoFormer_p4_eq15_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{R}_{\Theta,m}^{d}=\begin{pmatrix}\cos m\theta_{1}&-\sin m\theta_{1}&0&0&\cdots&0&0\\\sin m\theta_{1}&\cos m\theta_{1}&0&0&\cdots&0&0\\0&0&\cos m\theta_{2}&-\sin m\theta_{2}&\cdots&0&0\\0&0&\sin m\theta_{2}&\cos m\theta_{2}&\cdots&0&0\\\vdots&\vdots&\vdots&\vdots&\ddots&\vdots&\vdots\\0&0&0&0&\cdots&\cos m\theta_{d/2}&-\sin m\theta_{d/2}\\0&0&0&0&\cdots&\sin m\theta_{d/2}&\cos m\theta_{d/2}\end{pmatrix}",
        "equation_number": "15",
        "notes": "human_from_harvest; complete block-diagonal rotary matrix",
    },
    {
        "id": "45_RoFormer_p4_eq16_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "orthogonality sentence below (16)",
    },
    {
        "id": "45_RoFormer_p5_eq17_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "self-attention complexity paragraph below (17)",
    },
    {
        "id": "45_RoFormer_p5_eq18_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "(17) and (18) with intervening prose",
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
    spec["created_at"] = "2026-08-23T18:00:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
