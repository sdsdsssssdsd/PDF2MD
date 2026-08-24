# -*- coding: utf-8 -*-
"""Append harvest reviews for harvest-640 batch (8). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq32_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped Lyapunov sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq03_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped Lyapunov sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq23_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped Lyapunov sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p5_eq33_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped Lyapunov sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p6_eq32_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped Lyapunov sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p6_eq33_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped Lyapunov sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p6_eq23_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped Lyapunov sum fragment plus line above",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p6_eq03_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "right-clipped Lyapunov sum fragment plus line above",
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
    spec["created_at"] = "2026-08-23T16:58:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
