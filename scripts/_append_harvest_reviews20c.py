# -*- coding: utf-8 -*-
"""Append harvest reviews for batch-6 (20). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "13_基于提示方法与知识蒸馏方法的口语语音识别模型构建_p4_eq8_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "的序列级隐藏状态 fragment above (8)",
    },
    {
        "id": "13_基于提示方法与知识蒸馏方法的口语语音识别模型构建_p4_eq9_h",
        "action": "verify",
        "gold_latex_raw": r"H_{\text{text}}=f_{\text{enc}}^{\text{lm}}(T)(D_t\times D_t^{\text{lm}})",
        "equation_number": "9",
        "notes": "human_from_harvest; complete text hidden-state map",
    },
    {
        "id": "13_基于提示方法与知识蒸馏方法的口语语音识别模型构建_p4_eq10_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "dashv_sm leftover above shrink (10)",
    },
    {
        "id": "14_Neural_ODEs_p17_eq53_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where clause and algorithm steps 2-4 below (53)",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p7_eq24_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "piecewise when-k lines missing leading abs bar",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p7_eq25_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "right fragment of summation missing LHS",
    },
    {
        "id": "17_发电机组流场数值模拟及优化分析_p2_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{\partial\rho\varphi}{\partial t}+\mathrm{div}(\rho\varphi\vec{u})=\mathrm{div}(\Gamma_{\varphi}\cdot\mathrm{grad}\varphi+S_{\varphi})",
        "equation_number": "1",
        "notes": "human_from_harvest; complete scalar transport",
    },
    {
        "id": "18_封闭高压开关设备发热监测与评估方法综述_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "y-momentum missing rho( time derivative at left",
    },
    {
        "id": "18_封闭高压开关设备发热监测与评估方法综述_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "energy equation missing rho u dT/dx at left",
    },
    {
        "id": "19_基于多孔介质模型的过滤器分析_p2_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "式，为 lead-in above (3)",
    },
    {
        "id": "19_基于多孔介质模型的过滤器分析_p2_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"C_1=\frac{150(1-\varepsilon)^2}{d^2\varepsilon^2}",
        "equation_number": "4",
        "notes": "human_from_harvest; complete Ergun C1",
    },
    {
        "id": "19_基于多孔介质模型的过滤器分析_p2_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"q=\frac{1}{C_1}",
        "equation_number": "5",
        "notes": "human_from_harvest; complete permeability factor",
    },
    {
        "id": "19_基于多孔介质模型的过滤器分析_p2_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"C_2=\frac{3.5(1-\varepsilon)}{d\varepsilon^3}",
        "equation_number": "6",
        "notes": "human_from_harvest; complete Ergun C2",
    },
    {
        "id": "19_基于多孔介质模型的过滤器分析_p2_eq7_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "|u| definition and C1 式中 below (7)",
    },
    {
        "id": "19_基于多孔介质模型的过滤器分析_p2_eq8_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "prior |u| line and 单位体积迎流面的面积 above (8)",
    },
    {
        "id": "19_基于多孔介质模型的过滤器分析_p2_eq9_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated", "neighbor_eq"],
        "notes": "湍动能 lead-in and epsilon eq stacked below (9)",
    },
    {
        "id": "19_基于多孔介质模型的过滤器分析_p2_eq10_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "耗散率 lead-in above two-line epsilon (10)",
    },
    {
        "id": "19_基于多孔介质模型的过滤器分析_p2_eq11_h",
        "action": "verify",
        "gold_latex_raw": r"\varepsilon=\frac{\mu}{\rho}\left(\frac{\partial u_i'}{\partial x_k}\right)\left(\frac{\partial u_i'}{\partial x_k}\right)",
        "equation_number": "11",
        "notes": "human_from_harvest; complete dissipation rate",
    },
    {
        "id": "20_TRPO_p1_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where E[...] sampling sentence below (1)",
    },
    {
        "id": "20_TRPO_p1_eq2_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "clipped_left"],
        "notes": "continuation lines starting with = missing LHS",
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
    spec["created_at"] = "2026-08-23T17:20:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
