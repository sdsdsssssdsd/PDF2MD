# -*- coding: utf-8 -*-
"""Append harvest reviews for batch-2 (21). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "28_Improved_DDPM_p1_eq7_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "(6) Lt-1 and (7) LT stacked in one crop",
    },
    {
        "id": "28_Improved_DDPM_p3_eq15_h",
        "action": "verify",
        "gold_latex_raw": r"\Sigma_{\theta}(x_t,t)=\exp\left(v\log\beta_t+(1-v)\log\tilde{\beta}_t\right)",
        "equation_number": "15",
        "notes": "human_from_harvest; complete learned variance interpolation",
    },
    {
        "id": "28_Improved_DDPM_p3_eq16_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Lsimple lead-in above and lambda sentence below (16)",
    },
    {
        "id": "28_Improved_DDPM_p4_eq18_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Since E[Lt^2] paragraph below (18)",
    },
    {
        "id": "28_Improved_DDPM_p5_eq19_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "betaSt pair plus Sigma_theta prose below (19)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p3_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "SHC variable-definition lines below (1)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p3_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "top-line fragment above NLFER (2)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "speech-signal lead-in plus NCCF and clipped e0 (3)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p3_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"e_0=\sum_{n=0}^{N-K_{\max}}s^2(n),\quad e_k=\sum_{n=k}^{k+N-K_{\max}}s^2(n)",
        "equation_number": "4",
        "notes": "human_from_harvest; complete e0 and ek energy sums",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p3_eq5_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "ek repeat of (4) stacked with K bounds (5)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"c_1(t)=\mathrm{IMF}_1(t)=p_1^{k}(t)",
        "equation_number": "8",
        "notes": "human_from_harvest; complete first IMF sift",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq9_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "residual-signal prose above and below (9)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq10_h",
        "action": "verify",
        "gold_latex_raw": r"x(t)=\sum_{i=1}^{n}c_i(t)+r_n(t)",
        "equation_number": "10",
        "notes": "human_from_harvest; complete IMF decomposition sum",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq11_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Hilbert-transform lead-in and analytic-signal text (11)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq12_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "real/imaginary-part setup above yi(t) (12)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq13_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "instantaneous amplitude lead-in above ai(t) (13)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq14_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "instantaneous frequency lead-in below phii(t) (14)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq15_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "prose above and below omegai(t) derivative (15)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq16_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "instantaneous-energy prose above and IMF text below (16)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p4_eq17_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "two-line IMF feature-setup prose above F (17)",
    },
    {
        "id": "28_希尔伯特黄变换音频篡改检测算法_p5_eq21_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{Precision}=\frac{TP}{TP+FP}",
        "equation_number": "21",
        "notes": "human_from_harvest; complete precision metric",
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
