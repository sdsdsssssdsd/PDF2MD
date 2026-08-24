# -*- coding: utf-8 -*-
"""Append harvest reviews for batch-1 (21). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "25_综合能源系统优化调度策略_p7_eq19_h",
        "action": "verify",
        "gold_latex_raw": r"C_{e\_start}(t)=\sum_{1}^{n}C_{SS,n}[U_n(t-1)(1-U_n(t))+U_n(t)(1-U_n(t-1))]",
        "equation_number": "19",
        "notes": "human_from_harvest; complete electric startup cost sum",
    },
    {
        "id": "25_综合能源系统优化调度策略_p7_eq20_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "式中为 lead-in defining Ce_yun Ce_start below (20)",
    },
    {
        "id": "25_综合能源系统优化调度策略_p8_eq21_h",
        "action": "verify",
        "gold_latex_raw": r"C_G(t)=C_{g\_yun}(t)+C_{g\_start}(t)+C_{g\_bs}(t)",
        "equation_number": "21",
        "notes": "human_from_harvest; complete gas subsystem cost sum",
    },
    {
        "id": "25_综合能源系统优化调度策略_p8_eq22_h",
        "action": "verify",
        "gold_latex_raw": r"C_H(t)=C_{h\_yun}(t)+C_{h\_start}(t)+C_{h\_bs}(t)",
        "equation_number": "22",
        "notes": "human_from_harvest; complete heat subsystem cost sum",
    },
    {
        "id": "25_综合能源系统优化调度策略_p8_eq23_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Cc_yun Cc_start definition line below (23)",
    },
    {
        "id": "26_StyleGAN2_p2_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"w'_{ijk}=s_i\cdot w_{ijk}",
        "equation_number": "1",
        "notes": "human_from_harvest; complete modulated weight",
    },
    {
        "id": "26_StyleGAN2_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\sigma_j=\sqrt{\sum_{i,k}{w'_{ijk}}^{2}}",
        "equation_number": "2",
        "notes": "human_from_harvest; complete feature norm sigma_j",
    },
    {
        "id": "26_StyleGAN2_p16_eq6_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where y in R^M paragraph below path-length loss (6)",
    },
    {
        "id": "26_StyleGAN2_p17_eq7_h",
        "action": "verify",
        "gold_latex_raw": r"\mathcal{L}_{\mathbf{w}}\approx(2\pi e/L)^{-L/2}\int_{\mathbb{S}}\int_0^\infty(r\|\mathbf{\Sigma}\phi\|_2-a)^2\exp\left(-\frac{(r-\sqrt{L})^2}{2\sigma^2}\right)\mathrm{d}r\,\mathrm{d}\phi",
        "equation_number": "7",
        "notes": "human_from_harvest; complete path-length expectation integral",
    },
    {
        "id": "26_StyleGAN2_p18_eq10_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "consequently it leaves 2-norm prose above (10)",
    },
    {
        "id": "26_三相四桥臂逆变器控制策略_p2_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"\begin{cases}u_{AN}=u_{AO}-u_{NO}\\u_{BN}=u_{BO}-u_{NO}\\u_{CN}=u_{CO}-u_{NO}\end{cases}",
        "equation_number": "1",
        "notes": "human_from_harvest; complete phase-to-neutral voltages",
    },
    {
        "id": "26_三相四桥臂逆变器控制策略_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\begin{cases}u_{\mathrm{aref}}=U\cos\omega t\\u_{\mathrm{bref}}=U\cos\left(\omega t-\frac{2\pi}{3}\right)\\u_{\mathrm{cref}}=U\cos\left(\omega t+\frac{2\pi}{3}\right)\end{cases}",
        "equation_number": "2",
        "notes": "human_from_harvest; complete three-phase reference voltages",
    },
    {
        "id": "26_三相四桥臂逆变器控制策略_p3_eq9_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "时间可得 lead-in between stacked (9) and (10)",
    },
    {
        "id": "26_三相四桥臂逆变器控制策略_p3_eq10_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "clipped 时间可得 fragment above brace block (10)",
    },
    {
        "id": "26_三相四桥臂逆变器控制策略_p3_eq11_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "式(11)可得 urZ prose below zero-sequence block",
    },
    {
        "id": "28_Improved_DDPM_p1_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"q(x_1,\ldots,x_T|x_0):=\prod_{t=1}^{T}q(x_t|x_{t-1})",
        "equation_number": "1",
        "notes": "human_from_harvest; complete forward diffusion factorization",
    },
    {
        "id": "28_Improved_DDPM_p1_eq2_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "clipped_top"],
        "notes": "clipped product t=1 tail from eq (1) above (2)",
    },
    {
        "id": "28_Improved_DDPM_p1_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"p_{\theta}(x_{t-1}|x_t):=\mathcal{N}(x_{t-1};\mu_{\theta}(x_t,t),\Sigma_{\theta}(x_t,t))",
        "equation_number": "3",
        "notes": "human_from_harvest; complete reverse Gaussian parameterization",
    },
    {
        "id": "28_Improved_DDPM_p1_eq4_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "Kingma Welling lead-in plus stacked (4) and (5)",
    },
    {
        "id": "28_Improved_DDPM_p1_eq5_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "VLB block captures numbered (4)(5)(6) together",
    },
    {
        "id": "28_Improved_DDPM_p1_eq6_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "VLB block captures numbered (5)(6)(7) together",
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
