# -*- coding: utf-8 -*-
"""Split pending review queue crops into batch folders."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.utils.paths import K5_GOLD_DIR, K5_TIGHT_CROPS_DIR

need = []
for line in (K5_GOLD_DIR / "review_queue.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    if not r.get("verified"):
        need.append(r)

base = Path(r"d:\Docling\_tmp_review_batches")
if base.is_dir():
    shutil.rmtree(base)
base.mkdir()
per = 21
for i, r in enumerate(need):
    bi = i // per
    (base / f"batch{bi}").mkdir(exist_ok=True)
    hits = list(K5_TIGHT_CROPS_DIR.rglob(r["id"] + ".png"))
    if hits:
        dst = base / f"batch{bi}" / f"{i % per:02d}_{r['id']}.png"
        shutil.copy2(hits[0], dst)

for bi in range(10):
    d = base / f"batch{bi}"
    if d.is_dir():
        n = len(list(d.glob("*.png")))
        if n:
            print(f"batch{bi}", n)
print("total", len(need))
