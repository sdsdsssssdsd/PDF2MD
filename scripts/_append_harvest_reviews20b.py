# -*- coding: utf-8 -*-
"""Append harvest reviews for left-col batch-5 (20). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "09_恒温式热线风速仪试制及试验验证_p1_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "量相等即 lead-in above (1)",
    },
    {
        "id": "09_恒温式热线风速仪试制及试验验证_p2_eq9_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "(9) stacked with (10)",
    },
    {
        "id": "09_恒温式热线风速仪试制及试验验证_p2_eq10_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "(10) stacked with leftover (9)",
    },
    {
        "id": "09_恒温式热线风速仪试制及试验验证_p2_eq11_h",
        "action": "verify",
        "gold_latex_raw": r"Q_{w}=I_{w}^{2}r_{w}=Q_{t}",
        "equation_number": "11",
        "notes": "human_from_harvest; complete Joule-heat balance",
    },
    {
        "id": "09_恒温式热线风速仪试制及试验验证_p2_eq12_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{I_{w}^{2}r_{w}}{r_{w}-r_{0}}=(X+Y\sqrt{v})",
        "equation_number": "12",
        "notes": "human_from_harvest; complete King's-law form",
    },
    {
        "id": "09_恒温式热线风速仪试制及试验验证_p3_eq13_h",
        "action": "verify",
        "gold_latex_raw": r"f_{c}=\frac{1}{1.3\Delta t}",
        "equation_number": "13",
        "notes": "human_from_harvest; complete cutoff frequency",
    },
    {
        "id": "09_恒温式热线风速仪试制及试验验证_p4_eq14_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "表述为 lead-in above (14)",
    },
    {
        "id": "09_恒温式热线风速仪试制及试验验证_p5_eq16_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "的函数式 lead-in above (16)",
    },
    {
        "id": "10_YOLO_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\phi(x)=\begin{cases}x,&x>0\\0.1x,&\text{otherwise}\end{cases}",
        "equation_number": "2",
        "notes": "human_from_harvest; complete leaky ReLU",
    },
    {
        "id": "10_YOLO_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where 1_obj denotes sentence below YOLO loss",
    },
    {
        "id": "12_基于模型的燃料电池物流车能量管理策略开发_p2_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "u_PID range and pedal 式中 below (2)",
    },
    {
        "id": "12_基于模型的燃料电池物流车能量管理策略开发_p2_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "4)燃料电池模型 and 输出电压表示为 above (3)",
    },
    {
        "id": "12_基于模型的燃料电池物流车能量管理策略开发_p2_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "定量关系 sentence above Shepherd (4)",
    },
    {
        "id": "12_基于模型的燃料电池物流车能量管理策略开发_p2_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "安时积分法 and 式中 below SOC (5)",
    },
    {
        "id": "13_Deep_Sets_p18_eq22_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Lambda/Gamma dims and maxpool sentence below (22)",
    },
    {
        "id": "13_基于提示方法与知识蒸馏方法的口语语音识别模型构建_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "hidden-state maps stacked with linear/softmax",
    },
    {
        "id": "13_基于提示方法与知识蒸馏方法的口语语音识别模型构建_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "same stacked hidden-state crop as (3)",
    },
    {
        "id": "13_基于提示方法与知识蒸馏方法的口语语音识别模型构建_p3_eq5_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "softmax stacked with neighbor maps",
    },
    {
        "id": "13_基于提示方法与知识蒸馏方法的口语语音识别模型构建_p3_eq6_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "tokenize/ctc_loss code-like stack",
    },
    {
        "id": "13_基于提示方法与知识蒸馏方法的口语语音识别模型构建_p3_eq7_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "same CTC_Loss stack as (6)",
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
