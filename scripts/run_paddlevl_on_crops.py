#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recognition-only：PaddleOCR-VL-1.6 吃冻结 crop（P3）。独立 paddle venv，不进 GUI。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

_BLOCK_CONTENT = re.compile(r'block_content"\s*:\s*"((?:\\.|[^"\\])*)"')

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _as_dict(item: object) -> dict:
    if item is None:
        return {}
    js = getattr(item, "json", None)
    if isinstance(js, dict):
        item = js
    if isinstance(item, str):
        try:
            item = json.loads(item)
        except json.JSONDecodeError:
            return {}
    if not isinstance(item, dict):
        return {}
    if isinstance(item.get("res"), dict):
        item = item["res"]
    return item


def _latex_from_text(text: str) -> str:
    from app.ocr.formula_crop_extract import salvage_formula_from_raw

    hit = salvage_formula_from_raw(text or "")
    if hit.block and (hit.block.latex_or_text or "").strip():
        return hit.block.latex_or_text.strip()
    return (text or "").strip()


def _content_from_truncated_json(text: str) -> str:
    m = _BLOCK_CONTENT.search(text or "")
    if not m:
        return ""
    try:
        return json.loads(f'"{m.group(1)}"')
    except json.JSONDecodeError:
        return m.group(1).replace("\\\\", "\\")


def _pred_from_vl(item: object) -> str:
    row = _as_dict(item)
    if not row.get("parsing_res_list") and isinstance(item, str):
        salvaged = _content_from_truncated_json(item)
        if salvaged:
            return _latex_from_text(salvaged)
    for block in row.get("parsing_res_list") or []:
        if not isinstance(block, dict):
            continue
        content = str(block.get("block_content") or "").strip()
        if content:
            return _latex_from_text(content)
    for key in ("rec_formula", "formula", "latex"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return _latex_from_text(v)
    md = row.get("markdown") or row.get("parsing_res_markdown") or ""
    if isinstance(md, dict):
        md = md.get("markdown") or md.get("text") or ""
    text = str(md or row.get("rec_text") or "")
    return _latex_from_text(text) if text else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--crop-root", default=str(ROOT / "benchmarks" / "crops"))
    ap.add_argument("--prefer-tight", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--include-unverified",
        action="store_true",
        help="Also score unverified harvest rows (no exact unless gold present).",
    )
    args = ap.parse_args()

    from paddleocr import PaddleOCRVL

    from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2, summarize_reports

    gold_path = Path(args.gold)
    crop_root = Path(args.crop_root)
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    # 紧 crop 已是公式图：关掉版面，避免再切一刀
    pipeline = PaddleOCRVL(
        pipeline_version="v1.6",
        use_layout_detection=False,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
    )
    reports = []
    details = []
    total = sum(
        1
        for line in gold_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        and (json.loads(line).get("verified") or args.include_unverified)
    )
    done = 0
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        verified = bool(row.get("verified"))
        if not verified and not args.include_unverified:
            continue
        rel = (row.get("crop_path_tight") if args.prefer_tight else row.get("crop_path")) or ""
        crop = crop_root / rel if rel else crop_root / "_missing.png"
        pred = ""
        raw = ""
        err = ""
        if not crop.is_file():
            err = "crop_missing"
        else:
            try:
                out = list(
                    pipeline.predict(
                        str(crop),
                        use_layout_detection=False,
                        prompt_label="formula",
                    )
                )
                item = out[0] if out else {}
                pred = _pred_from_vl(item)
                dump = item.json if hasattr(item, "json") and isinstance(item.json, dict) else item
                raw = json.dumps(dump, ensure_ascii=False, default=str)[:2000]
            except Exception as e:
                err = f"{type(e).__name__}:{e}"
        report = ev.compare(pred, row.get("gold_latex_raw") or "")
        if verified and str(row.get("gold_latex_raw") or "").strip():
            reports.append(report)
            scored = report.to_dict()
        else:
            scored = {"strict_canonical_exact": None, "reasons": ["no_gold"]}
        details.append(
            {
                "id": row.get("id"),
                "equation_number": row.get("equation_number"),
                "verified": verified,
                "pred": pred,
                "raw": raw,
                "gold": row.get("gold_latex_raw"),
                "error": err,
                **scored,
            }
        )
        done += 1
        if done % 10 == 0 or done == total:
            print(f"[PaddleVL] {done}/{total}", flush=True)

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": "PaddleOCR-VL-1.6",
        "gold": str(gold_path),
        "summary": summarize_reports(reports),
        "details": details,
        "shadow_only": True,
        "prefer_tight": bool(args.prefer_tight),
        "include_unverified": bool(args.include_unverified),
    }
    out = Path(args.out) if args.out else ROOT / "benchmarks" / "results" / "paddlevl16_o018_tight.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
