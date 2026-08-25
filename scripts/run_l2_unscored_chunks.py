#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 verified_unscored 拆成小批跑 L2，避免 GPU OOM（shadow only）。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ocr.deepseek_paths import resolve_dsocr2_python

PY_DS = resolve_dsocr2_python() or Path(sys.executable)
GOLD = ROOT / "benchmarks" / "gold" / "verified_unscored.jsonl"
OUT_DIR = ROOT / "benchmarks" / "results"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=10)
    args = ap.parse_args()
    if not PY_DS.is_file():
        print("deepseek venv missing", file=sys.stderr)
        return 2
    rows = [json.loads(x) for x in GOLD.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        print({"ok": True, "n": 0, "note": "nothing_unscored"})
        return 0
    n = 0
    for i in range(0, len(rows), args.chunk):
        chunk = rows[i : i + args.chunk]
        part = OUT_DIR / f"verified_unscored_part{i // args.chunk}.jsonl"
        out = OUT_DIR / f"deepseek_l2_verified_part{i // args.chunk}.json"
        part.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in chunk), encoding="utf-8")
        cmd = [
            str(PY_DS),
            "scripts/run_deepseek_on_crops.py",
            "--gold",
            str(part),
            "--prefer-tight",
            "--image-size",
            "640",
            "--prompt",
            "document",
            "--experiment-id",
            "L2",
            "--out",
            str(out),
        ]
        print("$", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
        n += len(chunk)
    print({"ok": True, "scored": n})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
