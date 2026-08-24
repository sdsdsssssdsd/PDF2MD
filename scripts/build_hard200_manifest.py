#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 verified Gold + L2 失败层构建 Hard-200 清单（只读评测，不训练）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_MANIFESTS_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402


def _load_l2_preds() -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for f in sorted(K5_RESULTS_DIR.glob("deepseek_l2_verified*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for d in data.get("details") or []:
            by_id[str(d["id"])] = d
    return by_id


def _tags_from_latex(tex: str) -> list[str]:
    tags: list[str] = []
    t = tex or ""
    if "\\frac" in t:
        tags.append("fraction")
    if "\\sum" in t or "\\prod" in t or "\\int" in t:
        tags.append("sum_prod_int")
    if "\\begin{cases}" in t or "\\begin{array}" in t:
        tags.append("cases_or_array")
    if "\\mathbb" in t or "\\mathcal" in t:
        tags.append("fonts")
    if "\\text{" in t or any("\u4e00" <= c <= "\u9fff" for c in t):
        tags.append("text_or_zh")
    if len(t) > 120:
        tags.append("long")
    return tags or ["other"]


def main() -> int:
    ensure_dirs()
    gold_path = K5_GOLD_DIR / "verified_all.jsonl"
    if not gold_path.is_file():
        print("run rebuild_verified_all.py first", file=sys.stderr)
        return 2
    l2 = _load_l2_preds()
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    scored: list[tuple[float, dict]] = []
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("id") or "")
        gold = str(row.get("gold_latex_raw") or "")
        if not gold.strip():
            continue
        d = l2.get(rid) or {}
        exact = bool(d.get("strict_canonical_exact"))
        ter = float(d.get("token_edit_ratio") or 0.0)
        # 优先：L2 错 + 长式 + 中文 + 复杂结构
        hard = 0.0
        if not exact:
            hard += 10.0 + ter * 5.0
        else:
            hard += ter
        if row.get("language") == "zh":
            hard += 1.5
        if len(gold) > 80:
            hard += 2.0
        for tag in _tags_from_latex(gold):
            if tag in ("cases_or_array", "sum_prod_int", "long"):
                hard += 1.0
        entry = {
            "id": rid,
            "pdf_id": row.get("pdf_id"),
            "language": row.get("language"),
            "equation_number": row.get("equation_number"),
            "difficulty": "hard",
            "tags": _tags_from_latex(gold),
            "l2_exact": exact,
            "l2_token_edit_ratio": ter,
            "split": "hard200",
            "do_not_train": True,
        }
        scored.append((hard, entry))
    scored.sort(key=lambda x: -x[0])
    picked = [e for _, e in scored[:200]]
    out = K5_MANIFESTS_DIR / "hard200_v1.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in picked), encoding="utf-8")
    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n": len(picked),
        "l2_miss_in_hard": sum(1 for r in picked if not r.get("l2_exact")),
        "english": sum(1 for r in picked if r.get("language") == "en"),
        "chinese": sum(1 for r in picked if r.get("language") == "zh"),
        "do_not_train": True,
    }
    (K5_MANIFESTS_DIR / "hard200_v1_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(meta)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
