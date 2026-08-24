# -*- coding: utf-8 -*-
"""Append harvest reviews for batch-0 (21). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "24_Soft_Actor_Critic_p3_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "modified Bellman backup lead-in above (2)",
    },
    {
        "id": "24_Soft_Actor_Critic_p3_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"V(\mathbf{s}_{t})=\mathbb{E}_{\mathbf{a}_{t}\sim\pi}[Q(\mathbf{s}_{t},\mathbf{a}_{t})-\log\pi(\mathbf{a}_{t}|\mathbf{s}_{t})]",
        "equation_number": "3",
        "notes": "human_from_harvest; complete soft value definition",
    },
    {
        "id": "24_Soft_Actor_Critic_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "D_KL projection LHS clipped in (4)",
    },
    {
        "id": "24_Soft_Actor_Critic_p4_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"J_{V}(\psi)=\mathbb{E}_{\mathbf{s}_{t}\sim\mathcal{D}}\left[\frac{1}{2}\left(V_{\psi}(\mathbf{s}_{t})-\mathbb{E}_{\mathbf{a}_{t}\sim\pi_{\phi}}[Q_{\theta}(\mathbf{s}_{t},\mathbf{a}_{t})-\log\pi_{\phi}(\mathbf{a}_{t}|\mathbf{s}_{t})]\right)^{2}\right]",
        "equation_number": "5",
        "notes": "human_from_harvest; complete value critic loss",
    },
    {
        "id": "24_Soft_Actor_Critic_p4_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"\hat{\nabla}_{\psi}J_{V}(\psi)=\nabla_{\psi}V_{\psi}(\mathbf{s}_{t})(V_{\psi}(\mathbf{s}_{t})-Q_{\theta}(\mathbf{s}_{t},\mathbf{a}_{t})+\log\pi_{\phi}(\mathbf{a}_{t}|\mathbf{s}_{t})),",
        "equation_number": "6",
        "notes": "human_from_harvest; complete value critic gradient",
    },
    {
        "id": "24_Soft_Actor_Critic_p4_eq7_h",
        "action": "verify",
        "gold_latex_raw": r"J_{Q}(\theta)=\mathbb{E}_{(\mathbf{s}_{t},\mathbf{a}_{t})\sim\mathcal{D}}\left[\frac{1}{2}(Q_{\theta}(\mathbf{s}_{t},\mathbf{a}_{t})-\hat{Q}(\mathbf{s}_{t},\mathbf{a}_{t}))^{2}\right],",
        "equation_number": "7",
        "notes": "human_from_harvest; complete Q critic loss",
    },
    {
        "id": "24_Soft_Actor_Critic_p4_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"\hat{Q}(\mathbf{s}_{t},\mathbf{a}_{t})=r(\mathbf{s}_{t},\mathbf{a}_{t})+\gamma\mathbb{E}_{\mathbf{s}_{t+1}\sim p}[V_{\bar{\psi}}(\mathbf{s}_{t+1})],",
        "equation_number": "8",
        "notes": "human_from_harvest; complete soft Q target",
    },
    {
        "id": "24_Soft_Actor_Critic_p4_eq9_h",
        "action": "verify",
        "gold_latex_raw": r"\hat{\nabla}_{\theta}J_{Q}(\theta)=\nabla_{\theta}Q_{\theta}(\mathbf{a}_{t},\mathbf{s}_{t})(Q_{\theta}(\mathbf{s}_{t},\mathbf{a}_{t})-r(\mathbf{s}_{t},\mathbf{a}_{t})-\gamma V_{\bar{\psi}}(\mathbf{s}_{t+1})).",
        "equation_number": "9",
        "notes": "human_from_harvest; complete Q critic gradient",
    },
    {
        "id": "24_Soft_Actor_Critic_p4_eq10_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "KL-divergence lead-in paragraph above (10)",
    },
    {
        "id": "24_Soft_Actor_Critic_p4_eq11_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbf{a}_{t}=f_{\phi}(\epsilon_{t};\mathbf{s}_{t}),",
        "equation_number": "11",
        "notes": "human_from_harvest; complete reparameterized action",
    },
    {
        "id": "25_StyleGAN_p1_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"\text{AdaIN}(\mathbf{x}_{i},\mathbf{y})=\mathbf{y}_{s,i}\frac{\mathbf{x}_{i}-\mu(\mathbf{x}_{i})}{\sigma(\mathbf{x}_{i})}+\mathbf{y}_{b,i},",
        "equation_number": "1",
        "notes": "human_from_harvest; complete AdaIN normalization",
    },
    {
        "id": "25_StyleGAN_p6_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"l_{\mathcal{W}}=\mathbb{E}\left[\frac{1}{\epsilon^{2}}d(g(\text{lerp}(f(\mathbf{z}_{1}),f(\mathbf{z}_{2});t)),g(\text{lerp}(f(\mathbf{z}_{1}),f(\mathbf{z}_{2});t+\epsilon)))\right],",
        "equation_number": "3",
        "notes": "human_from_harvest; complete W-space path length loss",
    },
    {
        "id": "25_综合能源系统优化调度策略_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "two-line gas balance plus variable definitions below (4)",
    },
    {
        "id": "25_综合能源系统优化调度策略_p3_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "率表达式为 lead-in above (5)",
    },
    {
        "id": "25_综合能源系统优化调度策略_p3_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"P_{\text{GB}}^{h}(t)=\eta_{\text{GB}}\lambda_{\text{gas}}P_{\text{GB}}^{g}(t)",
        "equation_number": "6",
        "notes": "human_from_harvest; complete gas boiler heat output",
    },
    {
        "id": "25_综合能源系统优化调度策略_p3_eq7_h",
        "action": "verify",
        "gold_latex_raw": r"P_{\text{WHB}}^{h}(t)=(1-\eta_{\text{GT}}-\eta_{\text{loss}})P_{\text{GT}}^{e}/\eta_{\text{GT}}",
        "equation_number": "7",
        "notes": "human_from_harvest; complete waste-heat boiler output",
    },
    {
        "id": "25_综合能源系统优化调度策略_p3_eq8_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "达式为 lead-in above (8)",
    },
    {
        "id": "25_综合能源系统优化调度策略_p3_eq9_h",
        "action": "verify",
        "gold_latex_raw": r"P_{\text{EB}}^{h}(t)=\eta_{\text{EB}}P_{\text{EB}}^{e}(t)",
        "equation_number": "9",
        "notes": "human_from_harvest; complete electric boiler heat output",
    },
    {
        "id": "25_综合能源系统优化调度策略_p4_eq14_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "FCSNPS definition lead-in above (14)",
    },
    {
        "id": "25_综合能源系统优化调度策略_p7_eq17_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "summation of eq (18) stacked below (17)",
    },
    {
        "id": "25_综合能源系统优化调度策略_p7_eq18_h",
        "action": "verify",
        "gold_latex_raw": r"C_{e\_yun}(t)=\sum_{1}^{n}C_{n}P_{n}(t)",
        "equation_number": "18",
        "notes": "human_from_harvest; complete startup cost sum",
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
    spec["created_at"] = "2026-08-23T17:40:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
