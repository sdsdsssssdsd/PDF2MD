#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并 o018 + human_verified_v2 → verified_all.jsonl（去重，不改生产）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.paths import K5_GOLD_DIR, ensure_dirs  # noqa: E402


def main() -> int:
    ensure_dirs()
    parts: list[dict] = []
    seen: set[str] = set()
    for name in ("o018_verified.jsonl", "human_verified_v2.jsonl"):
        path = K5_GOLD_DIR / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rid = str(row.get("id") or "")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            parts.append(row)
    out = K5_GOLD_DIR / "verified_all.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in parts), encoding="utf-8")
    zh = sum(1 for r in parts if r.get("language") == "zh")
    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n": len(parts),
        "english": len(parts) - zh,
        "chinese": zh,
        "do_not_train": True,
    }
    (K5_GOLD_DIR / "verified_all_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(meta)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
