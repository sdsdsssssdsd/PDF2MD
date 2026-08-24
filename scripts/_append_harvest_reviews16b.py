# -*- coding: utf-8 -*-
"""Append harvest reviews for left-col batch-4 (16). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p5_eq22_h",
        "action": "verify",
        "gold_latex_raw": r"=\frac{1500}{1200}",
        "equation_number": "22",
        "notes": "human_from_harvest; complete numbered continuation ratio",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p5_eq23_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "same ratio line but denominator clipped at bottom",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{e}=\boldsymbol{r}-\boldsymbol{q}",
        "equation_number": "2",
        "notes": "human_from_harvest; complete tracking error",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"s=\dot{e}+\lambda e",
        "equation_number": "3",
        "notes": "human_from_harvest; complete sliding surface",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "对式(3)求导得 lead-in above (4)",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "将式(2)代入式(4) lead-in above (5)",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq6_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "由式(1)可得 lead-in above (6)",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq7_h",
        "action": "verify",
        "gold_latex_raw": r"\dot{s}=\ddot{r}-\boldsymbol{M}^{-1}(\tau-\tau_{d}-\boldsymbol{G}-\boldsymbol{C}\dot{\boldsymbol{q}})+\lambda\dot{e}",
        "equation_number": "7",
        "notes": "human_from_harvest; complete sliding dynamics",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{\tau}_{\mathrm{de}}=\boldsymbol{M}(\ddot{\boldsymbol{r}}+\lambda\dot{\boldsymbol{e}})+\boldsymbol{C}\dot{\boldsymbol{q}}+\boldsymbol{G}+\boldsymbol{\tau}_{\mathrm{d}}",
        "equation_number": "8",
        "notes": "human_from_harvest; complete equivalent torque",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq9_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{\tau}_{qi}=\boldsymbol{M}\cdot\boldsymbol{K}\cdot\mathrm{sgn}(s)",
        "equation_number": "9",
        "notes": "human_from_harvest; complete switching torque",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq10_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{\tau}=\boldsymbol{\tau}_{\mathrm{de}}+\boldsymbol{\tau}_{\mathrm{qi}}",
        "equation_number": "10",
        "notes": "human_from_harvest; complete total torque",
    },
    {
        "id": "07_基于切换增益调节的神经滑模控制的机器人位置跟踪_p2_eq11_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "神经元输出 lead-in and RBF 式中 below (11)",
    },
    {
        "id": "08_基于组合POA模型的硕曲河梯级水库短期优化调度_p2_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "FOA 求解目标 sentence above (3)",
    },
    {
        "id": "08_基于组合POA模型的硕曲河梯级水库短期优化调度_p2_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"Q'=\min(Q_{i,t}^{2},Q_{i,t+1}^{2})",
        "equation_number": "4",
        "notes": "human_from_harvest; complete POA discharge min",
    },
    {
        "id": "08_基于组合POA模型的硕曲河梯级水库短期优化调度_p2_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"n'=\max(N_{t}+N_{t+1})",
        "equation_number": "5",
        "notes": "human_from_harvest; complete POA power max",
    },
    {
        "id": "08_基于组合POA模型的硕曲河梯级水库短期优化调度_p2_eq6_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "原则即 and 式中 around (6)",
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
    spec["created_at"] = "2026-08-23T17:12:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
