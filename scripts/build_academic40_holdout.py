#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冻结 Academic40-Holdout-v1（20 en + 20 zh）。RC 前禁止打开评测。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.paths import K5_GOLD_DIR, K5_MANIFESTS_DIR, ensure_dirs  # noqa: E402


def main() -> int:
    ensure_dirs()
    src = K5_MANIFESTS_DIR / "academic100_regression_v1.json"
    if not src.is_file():
        print("run inventory_academic100.py first", file=sys.stderr)
        return 2
    data = json.loads(src.read_text(encoding="utf-8"))
    papers = list(data.get("papers") or [])
    en = [p for p in papers if p.get("language") == "en"]
    zh = [p for p in papers if p.get("language") == "zh"]
    # 避开 O-018 canary；按 pdf_id 稳定排序取前 20+20
    en = [p for p in en if not str(p.get("pdf_id", "")).startswith("O-018")]
    zh = [p for p in zh if not str(p.get("pdf_id", "")).startswith("O-018")]
    en.sort(key=lambda p: str(p.get("pdf_id") or ""))
    zh.sort(key=lambda p: str(p.get("pdf_id") or ""))
    hold = en[:20] + zh[:20]
    for p in hold:
        p["split"] = "holdout"
        p["do_not_train"] = True
        p["opened"] = False
    payload = {
        "name": "Academic40-Holdout-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "do_not_train": True,
        "opened": False,
        "note": "Do not score until release candidate. No gold harvesting from these PDFs.",
        "n": len(hold),
        "english": sum(1 for p in hold if p.get("language") == "en"),
        "chinese": sum(1 for p in hold if p.get("language") == "zh"),
        "papers": hold,
    }
    out = K5_MANIFESTS_DIR / "academic40_holdout_v1.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # 标记 regression 清单中 holdout 论文
    hold_ids = {str(p.get("pdf_id")) for p in hold}
    for p in papers:
        if str(p.get("pdf_id")) in hold_ids:
            p["split"] = "holdout_reserved"
    data["holdout_manifest"] = str(out)
    src.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print({"ok": True, "path": str(out), "n": len(hold)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
