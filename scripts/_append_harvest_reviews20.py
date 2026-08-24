# -*- coding: utf-8 -*-
"""Append harvest reviews for left-col batch-3 (20). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "05_梯级水光蓄协调优化控制技术研究_p3_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"\overline{P}_{i,t}\leqslant P_{t}\leqslant\underline{P}_{i+1,t}",
        "equation_number": "8",
        "notes": "human_from_harvest; complete cascade power bounds",
    },
    {
        "id": "05_梯级水光蓄协调优化控制技术研究_p4_eq10_h",
        "action": "verify",
        "gold_latex_raw": r"P_{\mathrm{PV}}=P_{\mathrm{HFP}}+P_{\mathrm{LFP}}",
        "equation_number": "10",
        "notes": "human_from_harvest; complete PV split",
    },
    {
        "id": "06_Graph_Convolutional_Networks_p13_eq14_h",
        "action": "verify",
        "gold_latex_raw": r"H^{(l+1)}=\sigma(\tilde{D}^{-\frac{1}{2}}\tilde{A}\tilde{D}^{-\frac{1}{2}}H^{(l)}W^{(l)})+H^{(l)}.",
        "equation_number": "14",
        "notes": "human_from_harvest; complete residual GCN layer",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p3_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"P_{ju}=U_{ju}\sum_{i=1}^{n}Y_{j,i}U_{iu}",
        "equation_number": "4",
        "notes": "human_from_harvest; complete nodal power",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p3_eq5_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "k-range stacked with extra radical identities",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p3_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"U_{d1}=U_{d0}-\frac{3X_{c}}{2\pi}I_{d}",
        "equation_number": "6",
        "notes": "human_from_harvest; complete rectifier Ud1",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p3_eq7_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "Ud2 stacked/garbled radicals",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p3_eq8_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "Ud3 stacked/garbled radicals",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p3_eq9_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "Ud5.1 stacked/garbled radicals",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p3_eq10_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "second Ud5.1 crop, same stacked radicals",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p4_eq12_h",
        "action": "verify",
        "gold_latex_raw": r"P_{i}=f(U,P_{u},P_{d},L_{u},L_{d})",
        "equation_number": "12",
        "notes": "human_from_harvest; complete power map",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p4_eq13_h",
        "action": "verify",
        "gold_latex_raw": r"I_{ju}=P_{ju}/U_{ju}",
        "equation_number": "13",
        "notes": "human_from_harvest; complete current from power",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p4_eq14_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "式(12)中 set defs around U=G^{-1}I",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p4_eq15_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{U}^{(k+1)}=\boldsymbol{G}^{-1}\boldsymbol{I}^{(k)}",
        "equation_number": "15",
        "notes": "human_from_harvest; complete voltage iteration",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p4_eq16_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "max residual stacked fragments",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p4_eq17_h",
        "action": "verify",
        "gold_latex_raw": r"U_{uj}\times I_{uj}\times\mu=F_{t}(v)\times v",
        "equation_number": "17",
        "notes": "human_from_harvest; complete traction power",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p5_eq18_h",
        "action": "verify",
        "gold_latex_raw": r"\mu I_{1200}=\frac{F_{t}(v)\times v}{U_{1200}}",
        "equation_number": "18",
        "notes": "human_from_harvest; complete 1200V current",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p5_eq19_h",
        "action": "verify",
        "gold_latex_raw": r"\mu I_{1500}=\frac{F_{t}(v)\times v}{U_{1500}}",
        "equation_number": "19",
        "notes": "human_from_harvest; complete 1500V current",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p5_eq20_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "left-clipped voltage-ratio fragment",
    },
    {
        "id": "06_考虑车网耦合的地铁供电系统潮流计算研究_p5_eq21_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "left-clipped 1200/1500 ratio fragment",
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
    spec["created_at"] = "2026-08-23T17:10:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
