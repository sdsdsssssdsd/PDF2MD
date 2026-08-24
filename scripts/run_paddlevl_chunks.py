#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PaddleVL 分批评测（避免长任务中断后从零重来）。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PADDLE = ROOT / ".venv-paddle-formula" / "Scripts" / "python.exe"
GOLD = ROOT / "benchmarks" / "gold" / "verified_all.jsonl"
OUT = ROOT / "benchmarks" / "results" / "paddlevl_verified_all_tight.json"
PART_DIR = ROOT / "benchmarks" / "results" / "paddlevl_parts"


def _rows() -> list[dict]:
    return [json.loads(x) for x in GOLD.read_text(encoding="utf-8").splitlines() if x.strip()]


def _merge(parts: list[Path]) -> None:
    from app.ocr.match_eval_v2 import MatchReportV2, summarize_reports

    details: list[dict] = []
    for p in parts:
        data = json.loads(p.read_text(encoding="utf-8"))
        details.extend(data.get("details") or [])
    reports = []
    for d in details:
        if d.get("strict_canonical_exact") is not None:
            reports.append(
                MatchReportV2(
                    strict_canonical_exact=bool(d.get("strict_canonical_exact")),
                    token_edit_distance=int(d.get("token_edit_distance") or 0),
                    token_edit_ratio=float(d.get("token_edit_ratio") or 0.0),
                    compile_ok=bool(d.get("compile_ok")),
                    reasons=list(d.get("reasons") or []),
                )
            )
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": "PaddleOCR-VL-1.6",
        "gold": str(GOLD),
        "summary": summarize_reports(reports),
        "details": details,
        "shadow_only": True,
        "prefer_tight": True,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=20)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()
    PART_DIR.mkdir(parents=True, exist_ok=True)
    parts = sorted(PART_DIR.glob("part_*.json"))
    if args.merge_only:
        if not parts:
            print("no parts", file=sys.stderr)
            return 2
        _merge(parts)
        return 0
    rows = _rows()
    for i in range(0, len(rows), args.chunk):
        part_out = PART_DIR / f"part_{i // args.chunk:03d}.json"
        if part_out.is_file():
            print(f"skip existing {part_out.name}", flush=True)
            continue
        part_gold = PART_DIR / f"part_{i // args.chunk:03d}.jsonl"
        chunk = rows[i : i + args.chunk]
        part_gold.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in chunk), encoding="utf-8")
        cmd = [
            str(PADDLE),
            "scripts/run_paddlevl_on_crops.py",
            "--gold",
            str(part_gold),
            "--prefer-tight",
            "--out",
            str(part_out),
        ]
        print("$", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    _merge(sorted(PART_DIR.glob("part_*.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
