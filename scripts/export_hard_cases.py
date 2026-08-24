#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 formula_qa 导出 Hard Case 候选（disagreement / abstain / writeback skip）。

未经人工确认不得作为训练标签。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.paths import EXPERIMENT_DIR, K5_HARD_CASES_DIR, ensure_dirs  # noqa: E402


def _collect(qa: dict, stem: str) -> list[dict]:
    out: list[dict] = []
    for fail in qa.get("formula_failures") or []:
        if not isinstance(fail, dict):
            continue
        out.append(
            {
                "pdf_id": stem,
                "source": "formula_failures",
                "status": fail.get("status"),
                "issues": fail.get("issues"),
                "preview": (fail.get("text") or fail.get("raw_text") or "")[:240],
                "verified": False,
                "notes": "hard_case_candidate; needs_human_gt",
            }
        )
    wb = qa.get("writeback") if isinstance(qa.get("writeback"), dict) else {}
    for entry in wb.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        skip = str(entry.get("skip_reason") or "")
        if skip or entry.get("accepted") is False:
            out.append(
                {
                    "pdf_id": stem,
                    "source": "writeback",
                    "skip_reason": skip,
                    "candidate_id": entry.get("candidate_id"),
                    "verified": False,
                    "notes": "writeback_skip_or_reject",
                }
            )
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Export hard-case candidates")
    p.add_argument("--experiment-dir", default=str(EXPERIMENT_DIR))
    p.add_argument("--out", default="")
    args = p.parse_args(argv)

    ensure_dirs()
    exp = Path(args.experiment_dir)
    rows: list[dict] = []
    if exp.is_dir():
        for qa_path in sorted(exp.glob("*/*.formula_qa.json")):
            try:
                qa = json.loads(qa_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rows.extend(_collect(qa, qa_path.parent.name))

    out = Path(args.out) if args.out else K5_HARD_CASES_DIR / "hard_candidates.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print({"ok": True, "path": str(out), "n": len(rows)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
