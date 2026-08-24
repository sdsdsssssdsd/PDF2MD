# -*- coding: utf-8 -*-
"""Append harvest reviews for batch-3 (21). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p5_eq22_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{Recall}=\frac{TP}{TP+FN}",
        "equation_number": "22",
        "notes": "human_from_harvest; complete recall metric",
    },
    {
        "id": "29_Latent_Diffusion_Models_p3_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"L_{LDM}:=\mathbb{E}_{x,\epsilon\sim\mathcal{N}(0,1),t}\left[\|\epsilon-\epsilon_{\theta}(x_t,t)\|_{2}^{2}\right]",
        "equation_number": "1",
        "notes": "human_from_harvest; complete diffusion noise-prediction loss",
    },
    {
        "id": "29_考虑候车时间均衡性的灵活编组方案优化_p3_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"D_i=\frac{q_{i\max}}{\sum m\cdot f\cdot C}\times 100\%",
        "equation_number": "6",
        "notes": "human_from_harvest; complete demand share percentage",
    },
    {
        "id": "32_Swin_Transformer_p4_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Relative position bias paragraph above Attention (4)",
    },
    {
        "id": "33_低速湍流边界层DBD控制机制_p2_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"C_f=\left[\frac{2n\rho_{o,\mathrm{ave}}v_{o,\mathrm{ave}}}{q_{\infty}\lambda t}\frac{\cos\theta_r}{\cos\theta_i}\right]\Delta\xi",
        "equation_number": "1",
        "notes": "human_from_harvest; complete friction-coefficient increment",
    },
    {
        "id": "33_低速湍流边界层DBD控制机制_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "式中 variable-definition line below (4)",
    },
    {
        "id": "34_不同迎角下逆向喷流减阻降热特性研究_p2_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "的 Navier-Stokes 方程 lead-in above (1)",
    },
    {
        "id": "35_燃料理化特性与进气压力耦合对碳氢化合物排放的影响_p3_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "(v%) 按比例计算 lead-in above (1)",
    },
    {
        "id": "36_HC浓度对EGR冷却器沉积层表面微观结构的影响_p4_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"N_i=P_i-M_i+1",
        "equation_number": "2",
        "notes": "human_from_harvest; complete box-count index",
    },
    {
        "id": "36_HC浓度对EGR冷却器沉积层表面微观结构的影响_p4_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"N_r=\sum_{i=1}^{N}N_i",
        "equation_number": "3",
        "notes": "human_from_harvest; complete region box sum",
    },
    {
        "id": "36_HC浓度对EGR冷却器沉积层表面微观结构的影响_p4_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"r=\frac{s}{N}",
        "equation_number": "4",
        "notes": "human_from_harvest; complete box side length",
    },
    {
        "id": "36_HC浓度对EGR冷却器沉积层表面微观结构的影响_p4_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"D_s=\frac{\lg N_r}{\lg(1/r)}",
        "equation_number": "5",
        "notes": "human_from_harvest; complete fractal dimension",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq3_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (3) and (4)",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq4_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "same (3)+(4) stacked pair",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"M_i=D_i+C_i,\quad(i=1,2,3,\ldots,n)",
        "equation_number": "5",
        "notes": "human_from_harvest; complete DEMATEL prominence",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq6_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "中心度/原因度 Chinese explanation below (6)",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq7_h",
        "action": "verify",
        "gold_latex_raw": r"W_j^d=\frac{M_j}{\sum_{j=1}^{n}M_j}",
        "equation_number": "7",
        "notes": "human_from_harvest; complete normalized prominence weight",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbf{P}_{ij}=\frac{P_i-P_j}{2(n-1)}",
        "equation_number": "8",
        "notes": "human_from_harvest; complete AHP pairwise scale",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq9_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "entropy weight (9) plus a=(n-1)/2 definition",
    },
    {
        "id": "40_低铂纳米电催化材料设计合成及析氢研究进展_p2_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"E_{\eta}=1.23\mathrm{V}+E_{\text{阴}}+E_{\text{阳}}+E_{\text{其他}}",
        "equation_number": "1",
        "notes": "human_from_harvest; complete overpotential decomposition",
    },
    {
        "id": "40_低铂纳米电催化材料设计合成及析氢研究进展_p3_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Volmer-Tafel/Heyrovsky lead-in above Volmer step (2)",
    },
]


def main() -> int:
    spec = json.loads(PATH.read_text(encoding="utf-8"))
    old_ids = {str(r.get("id") or "") for r in spec.get("reviews") or []}
    added = 0
    for rev in NEW:
        if rev["id"] in old_ids:
            continue
        spec["reviews"].append(rev)
        old_ids.add(rev["id"])
        added += 1
    spec["created_at"] = "2026-08-23T17:45:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
