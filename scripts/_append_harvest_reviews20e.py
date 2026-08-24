# -*- coding: utf-8 -*-
"""Append harvest reviews for batch-7 (20). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "20_TRPO_p2_eq7_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Define D_TV^max lead-in and Theorem 1 below (7)",
    },
    {
        "id": "20_TRPO_p2_eq8_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where epsilon definition stacked in (8)",
    },
    {
        "id": "20_TRPO_p2_eq9_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where C= fraction line below bound (9)",
    },
    {
        "id": "20_TRPO_p2_eq10_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "three-line stack with by Equation (9) text",
    },
    {
        "id": "20_TRPO_p3_eq14_h",
        "action": "verify",
        "gold_latex_raw": r"\max_{\theta}\mathbb{E}_{s\sim\rho_{\theta_{\mathrm{old}}},a\sim q}\left[\frac{\pi_{\theta}(a|s)}{q(a|s)}Q_{\theta_{\mathrm{old}}}(s,a)\right]\text{ subject to }\mathbb{E}_{s\sim\rho_{\theta_{\mathrm{old}}}}[D_{\mathrm{KL}}(\pi_{\theta_{\mathrm{old}}}(\cdot|s)\|\pi_{\theta}(\cdot|s))]\leq\delta",
        "equation_number": "14",
        "notes": "human_from_harvest; complete TRPO constrained objective",
    },
    {
        "id": "20_TRPO_p4_eq15_h",
        "action": "verify",
        "gold_latex_raw": r"L_n(\theta)=\sum_{k=1}^{K}\pi_{\theta}(a_k|s_n)\hat{Q}(s_n,a_k)",
        "equation_number": "15",
        "notes": "human_from_harvest; complete surrogate sum",
    },
    {
        "id": "20_TRPO_p4_eq16_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "self-normalized estimator sentence above (16)",
    },
    {
        "id": "20_TRPO_p5_eq17_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "subject-to plus where A_ij and update below (17)",
    },
    {
        "id": "20_TRPO_p5_eq18_h",
        "action": "verify",
        "gold_latex_raw": r"\underset{\theta}{\mathrm{maximize}}\left[\nabla_{\theta}L_{\theta_{\mathrm{old}}}(\theta)|_{\theta=\theta_{\mathrm{old}}}\cdot(\theta-\theta_{\mathrm{old}})\right]",
        "equation_number": "18",
        "notes": "human_from_harvest; complete linearized TRPO step",
    },
    {
        "id": "21_Double_Q_Learning_p1_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "SGD explanation sentence below (2)",
    },
    {
        "id": "21_Double_Q_Learning_p1_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "target-network prose above and below (3)",
    },
    {
        "id": "21_Double_Q_Learning_p5_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "random/human score citation below (5)",
    },
    {
        "id": "22_Dueling_Networks_p2_eq1_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "Q^pi and V^pi definitions stacked as (1)",
    },
    {
        "id": "22_Dueling_Networks_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"Q^*(s,a)=\mathbb{E}_{s'}\left[r+\gamma\max_{a'}Q^*(s',a')\mid s,a\right].",
        "equation_number": "2",
        "notes": "human_from_harvest; complete Bellman optimality",
    },
    {
        "id": "22_Dueling_Networks_p2_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"A^{\pi}(s,a)=Q^{\pi}(s,a)-V^{\pi}(s).",
        "equation_number": "3",
        "notes": "human_from_harvest; complete advantage identity",
    },
    {
        "id": "22_Dueling_Networks_p3_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"y_i^{\mathrm{DDQN}}=r+\gamma Q(s',\arg\max_{a'}Q(s',a';\theta_i);\theta^-).",
        "equation_number": "6",
        "notes": "human_from_harvest; complete DDQN target",
    },
    {
        "id": "22_Dueling_Networks_p4_eq9_h",
        "action": "verify",
        "gold_latex_raw": r"Q(s,a;\theta,\alpha,\beta)=V(s;\theta,\beta)+\left(A(s,a;\theta,\alpha)-\frac{1}{|\mathcal{A}|}\sum_{a'}A(s,a';\theta,\alpha)\right).",
        "equation_number": "9",
        "notes": "human_from_harvest; complete dueling aggregation",
    },
    {
        "id": "22_多级液压天线举升机构运动平稳性检测系统_p3_eq2_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "(2) and (3) stacked in one crop",
    },
    {
        "id": "22_多级液压天线举升机构运动平稳性检测系统_p3_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"\theta_1=\arcsin\left(\frac{L_6}{L_4}\right)+\operatorname{arcos}\left(\frac{L_1^2+L_4^2-L_5^2}{2L_1L_4}\right)",
        "equation_number": "3",
        "notes": "human_from_harvest; complete angle theta1",
    },
    {
        "id": "22_多级液压天线举升机构运动平稳性检测系统_p3_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"R=1-\sqrt{\frac{\sum_{i=1}^{n}(S_i-S'_i)^2}{\sum_{i=1}^{n}S_i^2}}",
        "equation_number": "4",
        "notes": "human_from_harvest; complete fit metric R",
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
    spec["created_at"] = "2026-08-23T17:25:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
