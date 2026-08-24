# -*- coding: utf-8 -*-
"""Append harvest reviews for left-col batch-2 (24). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p3_eq5_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "stacked DKL identities, not a single display",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p3_eq6_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "previous-sentence residue above topic_ij",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p4_eq12_h",
        "action": "verify",
        "gold_latex_raw": r"Q^{*}=\{P_{Q}^{*}(u,v)\forall u,v\in V\}",
        "equation_number": "12",
        "notes": "human_from_harvest; complete Q-star set",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p4_eq13_h",
        "action": "verify",
        "gold_latex_raw": r"p_{u}=\sum_{v}p_{v}\cdot\boldsymbol{Q}_{vu}",
        "equation_number": "13",
        "notes": "human_from_harvest; complete stationary balance",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p4_eq14_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "stacked gradient identities",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p4_eq15_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "stacked partial-Q identities",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p4_eq16_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated", "neighbor_eq"],
        "notes": "如果(u,v)存在 piecewise with extra sums",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p6_eq17_h",
        "action": "verify",
        "gold_latex_raw": r"P=\frac{W_{\mathrm{Corrected}}}{W_{\mathrm{Allspam}}}\times 100\%",
        "equation_number": "17",
        "notes": "human_from_harvest; complete precision",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p6_eq18_h",
        "action": "verify",
        "gold_latex_raw": r"R=\frac{W_{\mathrm{Corrected}}}{W_{\mathrm{All}}}\times 100\%",
        "equation_number": "18",
        "notes": "human_from_harvest; complete recall",
    },
    {
        "id": "02_基于监督随机游走的有影响力用户发现算法_p6_eq19_h",
        "action": "verify",
        "gold_latex_raw": r"F=\frac{2\times P\times R}{P+R}\times 100\%",
        "equation_number": "19",
        "notes": "human_from_harvest; complete F-measure",
    },
    {
        "id": "03_基于反向学习与混合位置中心的樽海鞘算法_p2_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "式(4)求解 and 定义2 below",
    },
    {
        "id": "03_基于反向学习与混合位置中心的樽海鞘算法_p2_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated", "neighbor_eq"],
        "notes": "opposite-learn line plus k/ub/lb defs",
    },
    {
        "id": "03_基于反向学习与混合位置中心的樽海鞘算法_p2_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"W=\frac{\sum_{i=1}^{N}X_{i}(N-i+1)}{\sum_{i=1}^{N}i}",
        "equation_number": "6",
        "notes": "human_from_harvest; complete rank weight",
    },
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p13_eq24_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "mu/sigma denote sentence below (24)",
    },
    {
        "id": "04_基于分圆理论和中国剩余定理的跳频序列集构造_p2_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "自相关满足 lead-in above (1)",
    },
    {
        "id": "04_基于分圆理论和中国剩余定理的跳频序列集构造_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"H(S)\geqslant\left\lceil\frac{(NM-l)N}{(NM-1)l}\right\rceil",
        "equation_number": "2",
        "notes": "human_from_harvest; complete Peng-Fan set bound",
    },
    {
        "id": "04_基于分圆理论和中国剩余定理的跳频序列集构造_p5_eq4_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "Aa(S) stacked with extra count identities",
    },
    {
        "id": "04_基于分圆理论和中国剩余定理的跳频序列集构造_p5_eq5_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "Ac(S) stacked with extra count identities",
    },
    {
        "id": "05_Deep_Residual_Learning_p2_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "F represents the residual mapping paragraph below (1)",
    },
    {
        "id": "05_梯级水光蓄协调优化控制技术研究_p3_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"P_{\mathrm{SET}}=P_{\mathrm{PV}}+P_{\mathrm{EDC}}+P_{\mathrm{FSC}}",
        "equation_number": "2",
        "notes": "human_from_harvest; complete power balance",
    },
    {
        "id": "05_梯级水光蓄协调优化控制技术研究_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "(3) stacked with leftover (2)",
    },
    {
        "id": "05_梯级水光蓄协调优化控制技术研究_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "式中 reservoir-volume defs below (4)",
    },
    {
        "id": "05_梯级水光蓄协调优化控制技术研究_p3_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"Q_{i,t}=Q_{i,t}^{\mathrm{fd}}+S_{i,t}",
        "equation_number": "5",
        "notes": "human_from_harvest; complete outflow split",
    },
    {
        "id": "05_梯级水光蓄协调优化控制技术研究_p3_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"q_{i,t}=Q_{i-1,t-\tau}+q_{i,t}^{qu}",
        "equation_number": "6",
        "notes": "human_from_harvest; complete cascade inflow",
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
    spec["created_at"] = "2026-08-23T17:08:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
