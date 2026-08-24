# -*- coding: utf-8 -*-
"""Append harvest reviews for pending-review batch4. Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "40_低铂纳米电催化材料设计合成及析氢研究进展_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Heyrovsky步骤 Chinese label before (4)",
    },
    {
        "id": "40_低铂纳米电催化材料设计合成及析氢研究进展_p4_eq6_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Fig. 5 HER polarization caption above Tafel (6)",
    },
    {
        "id": "40_低铂纳米电催化材料设计合成及析氢研究进展_p5_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"MA=\frac{I}{m}",
        "equation_number": "8",
        "notes": "human_from_harvest; complete mass-activity ratio",
    },
    {
        "id": "44_氢气传感器的研究及应用进展_p4_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"E=E_{0}-\frac{RT}{nF}\ln Q",
        "equation_number": "3",
        "notes": "human_from_harvest; complete Nernst equation",
    },
    {
        "id": "45_氧化亚铜光阴极稳定性提升策略研究进展_p8_eq111_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "XRD figure Cu2O(111) peak annotation, not display eq",
    },
    {
        "id": "47_副产氢金属氢化物分离法净化氢技术经济性分析_p2_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"M+\frac{x}{2}\mathrm{H}_{2}\leftrightarrow\mathrm{MH}_{x}+\Delta H",
        "equation_number": "1",
        "notes": "human_from_harvest; complete hydride formation",
    },
    {
        "id": "47_副产氢金属氢化物分离法净化氢技术经济性分析_p4_eq7_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Chinese heading fragments clipped at top of (7)",
    },
    {
        "id": "47_副产氢金属氢化物分离法净化氢技术经济性分析_p4_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"D_{t}=\frac{I_{0}(1-V_{r})}{T_{\mathrm{op}}}",
        "equation_number": "8",
        "notes": "human_from_harvest; complete depreciation",
    },
    {
        "id": "47_副产氢金属氢化物分离法净化氢技术经济性分析_p4_eq9_h",
        "action": "verify",
        "gold_latex_raw": r"H_{\mathrm{total}}=\sum_{t=0}^{T_{\mathrm{op}}}\frac{H_{t}}{(1+i)^{t}}",
        "equation_number": "9",
        "notes": "human_from_harvest; complete discounted hydrogen sum",
    },
    {
        "id": "48_Ni-CeO2纳米复合材料催化肼硼烷产氢性能分析_p1_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{N}_{2}\mathrm{H}_{4}\mathrm{BH}_{3}+3\mathrm{H}_{2}\mathrm{O}\rightarrow\mathrm{N}_{2}\mathrm{H}_{4}+\mathrm{B}(\mathrm{OH})_{3}+3\mathrm{H}_{2}",
        "equation_number": "1",
        "notes": "human_from_harvest; complete hydrolysis step 1",
    },
    {
        "id": "48_Ni-CeO2纳米复合材料催化肼硼烷产氢性能分析_p1_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{N}_{2}\mathrm{H}_{4}\rightarrow\mathrm{N}_{2}+2\mathrm{H}_{2}",
        "equation_number": "2",
        "notes": "human_from_harvest; complete hydrazine decomposition",
    },
    {
        "id": "48_Ni-CeO2纳米复合材料催化肼硼烷产氢性能分析_p1_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"3\mathrm{N}_{2}\mathrm{H}_{4}\rightarrow\mathrm{N}_{2}+4\mathrm{NH}_{3}",
        "equation_number": "3",
        "notes": "human_from_harvest; complete hydrazine disproportionation",
    },
    {
        "id": "48_Ni-CeO2纳米复合材料催化肼硼烷产氢性能分析_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures (4) alpha fraction plus lambda definition below",
    },
    {
        "id": "48_Ni-CeO2纳米复合材料催化肼硼烷产氢性能分析_p3_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"TOF=\frac{n(\mathrm{H}_{2})}{n(\mathrm{metal})\cdot t}",
        "equation_number": "5",
        "notes": "human_from_harvest; complete TOF definition",
    },
    {
        "id": "48_Ni-CeO2纳米复合材料催化肼硼烷产氢性能分析_p3_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{N}_{2}\mathrm{H}_{4}\mathrm{BH}_{3}+3\mathrm{H}_{2}\mathrm{O}\rightarrow\mathrm{B}(\mathrm{OH})_{3}+(3+2\alpha)\mathrm{H}_{2}+\frac{2\alpha+1}{3}\mathrm{N}_{2}+\frac{4(1-\alpha)}{3}\mathrm{NH}_{3}",
        "equation_number": "6",
        "notes": "human_from_harvest; complete alpha-weighted hydrolysis",
    },
    {
        "id": "49_生命周期视角下氢的制取及其在化工领域的应用_p6_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"2\mathrm{Cu}(\mathrm{s})+2\mathrm{HCl}(\mathrm{g})\rightarrow2\mathrm{CuCl}(\mathrm{s})+\mathrm{H}_{2}(\mathrm{g})",
        "equation_number": "5",
        "notes": "human_from_harvest; complete CuCl hydrogen route",
    },
    {
        "id": "50_Deep_Learning_with_Differential_Privacy_p3_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"c(o;\mathcal{M},\mathrm{aux},d,d')\triangleq\log\frac{\Pr[\mathcal{M}(\mathrm{aux},d)=o]}{\Pr[\mathcal{M}(\mathrm{aux},d')=o]}",
        "equation_number": "1",
        "notes": "human_from_harvest; complete privacy cost definition",
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
    spec["created_at"] = "2026-08-23T17:40:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
