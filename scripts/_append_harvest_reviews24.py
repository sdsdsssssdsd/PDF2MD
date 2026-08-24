# -*- coding: utf-8 -*-
"""Append harvest reviews for left-col batch-1 (24). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "01_车辆悬架鲁棒控制_p2_eq1_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "(1) stacked with clipped start of (2)",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p2_eq2_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "RHS tail of unsprung-mass line, no LHS",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p2_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"\dot{x}(t)=Ax(t)+B_{1}u(t)+B_{2}w(t)",
        "equation_number": "3",
        "notes": "human_from_harvest; complete state equation",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p3_eq7_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "LMI with line-above residue and bottom clip",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p3_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"V(x)=x(t)^{\mathrm{T}}Px(t)+\int_{t-d}^{t}x(\tau)^{\mathrm{T}}Sx(\tau)\mathrm{d}\tau",
        "equation_number": "8",
        "notes": "human_from_harvest; complete Lyapunov functional",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p3_eq9_h",
        "action": "verify",
        "gold_latex_raw": r"J=\|z\|_{2}^{2}-\gamma^{2}\|w\|_{2}^{2}",
        "equation_number": "9",
        "notes": "human_from_harvest; complete H-inf index",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p3_eq10_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "(10) plus 等价于 matrix block",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p3_eq11_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "quadratic form stacked with neighbor expansion",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p3_eq12_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated", "neighbor_eq"],
        "notes": "式(11)等价于 lead-in into (12)",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p4_eq15_h",
        "action": "verify",
        "gold_latex_raw": r"f=c_{1}\dot{y}+k_{1}(x-x_{0})",
        "equation_number": "15",
        "notes": "human_from_harvest; complete Bouc-Wen force",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p4_eq16_h",
        "action": "verify",
        "gold_latex_raw": r"\dot{y}=[\alpha z+k_{0}(x-y)+c_{0}\dot{x}]/(c_{0}+c_{1})",
        "equation_number": "16",
        "notes": "human_from_harvest; complete Bouc-Wen y-dot",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p4_eq17_h",
        "action": "verify",
        "gold_latex_raw": r"\dot{z}=-\delta|\dot{x}-\dot{y}||z|^{n-1}z-\mu(\dot{x}-\dot{y})|z|^{n}+N(\dot{x}-\dot{y})",
        "equation_number": "17",
        "notes": "human_from_harvest; complete Bouc-Wen z-dot",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p4_eq18_h",
        "action": "verify",
        "gold_latex_raw": r"\alpha=\alpha(u)=\alpha_{a}+\alpha_{b}u",
        "equation_number": "18",
        "notes": "human_from_harvest; complete alpha(u)",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p4_eq19_h",
        "action": "verify",
        "gold_latex_raw": r"c_{1}=c_{1}(u)=c_{1a}+c_{1b}u",
        "equation_number": "19",
        "notes": "human_from_harvest; complete c1(u)",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p4_eq20_h",
        "action": "verify",
        "gold_latex_raw": r"c_{0}=c_{0}(u)=c_{0a}+c_{0b}u",
        "equation_number": "20",
        "notes": "human_from_harvest; complete c0(u)",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p4_eq21_h",
        "action": "verify",
        "gold_latex_raw": r"\dot{u}=-\eta(u-v)",
        "equation_number": "21",
        "notes": "human_from_harvest; complete voltage lag",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p4_eq22_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "似为 lead-in above (22)",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p4_eq23_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "逆模型即 lead-in above (23)",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p5_eq29_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "输入信号表示为 lead-in above (29)",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p5_eq30_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "表示 and 式中 definitions around (30)",
    },
    {
        "id": "01_车辆悬架鲁棒控制_p5_eq31_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "式中 definitions below (31)",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p3_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "差异度 sentence above Dis(i,j)",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "TS/KL stacked with neighbor identities",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "same stacked KL/TopicSim crop as (3)",
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
    spec["created_at"] = "2026-08-23T17:06:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
