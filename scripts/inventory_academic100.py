#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冻结 Academic100-Regression-v1 清单（禁止训练 / 禁止伪标签）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.crop_cache import language_from_stem  # noqa: E402
from app.utils.paths import K5_MANIFESTS_DIR, TESTSET_DIR, ensure_dirs  # noqa: E402


def main() -> int:
    ensure_dirs()
    papers = []
    if TESTSET_DIR.is_dir():
        for pdf in sorted(TESTSET_DIR.glob("*.pdf")):
            papers.append(
                {
                    "pdf_id": pdf.stem,
                    "language": language_from_stem(pdf.stem),
                    "filename": pdf.name,
                    "split": "regression",
                    "do_not_train": True,
                }
            )
    en = sum(1 for p in papers if p["language"] == "en")
    zh = sum(1 for p in papers if p["language"] == "zh")
    payload = {
        "name": "Academic100-Regression-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "do_not_train": True,
        "holdout_reserved": "Academic40-Holdout-v1 (not opened)",
        "n": len(papers),
        "english": en,
        "chinese": zh,
        "papers": papers,
    }
    out = K5_MANIFESTS_DIR / "academic100_regression_v1.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print({"ok": True, "path": str(out), "n": len(papers), "en": en, "zh": zh})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
