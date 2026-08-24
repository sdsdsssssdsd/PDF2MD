# -*- coding: utf-8 -*-
import json
from pathlib import Path

q = [
    json.loads(l)
    for l in Path("benchmarks/gold/review_queue.jsonl").read_text(encoding="utf-8").splitlines()
    if l.strip()
]
need = [r for r in q if not r.get("verified")]
print("N", len(need))
for i, r in enumerate(need):
    notes = r.get("notes") or ""
    prev = notes.split("preview=")[-1] if "preview=" in notes else ""
    print(f"{i:02d}|{r['id']}|{r.get('language')}|eq={r.get('equation_number')}|cq={r.get('crop_quality')}|{prev[:100]}")
