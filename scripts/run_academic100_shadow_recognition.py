#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Academic100 regression（60 篇）收割池 shadow 识别：PP-M + PaddleVL，不写生产。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.consensus import dual_model_consensus  # noqa: E402
from app.ocr.k5_taxonomy import summarize_shadow, simulate_shadow_writeback  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_MANIFESTS_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402

PADDLE = ROOT / ".venv-paddle-formula" / "Scripts" / "python.exe"
PY = Path(r"C:\python\python3-12.3\python.exe")
SUBSET = K5_GOLD_DIR / "harvest_display_regression.jsonl"
PP_OUT = K5_RESULTS_DIR / "pp_m_academic100_regression_tight.json"
VL_OUT = K5_RESULTS_DIR / "paddlevl_academic100_regression_tight.json"
SUMMARY_OUT = K5_RESULTS_DIR / "academic100_shadow_recognition_summary.json"


def _regression_rows() -> list[dict]:
    man = json.loads((K5_MANIFESTS_DIR / "academic100_regression_v1.json").read_text(encoding="utf-8"))
    reg = {p["pdf_id"] for p in man.get("papers") or [] if p.get("split") == "regression"}
    rows = []
    for line in (K5_GOLD_DIR / "harvest_display.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("pdf_id") in reg and row.get("crop_path_tight"):
            rows.append(row)
    return rows


def _load_preds(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(d["id"]): str(d.get("pred") or "") for d in data.get("details") or []}


def _run_pp() -> None:
    cmd = [
        str(PADDLE),
        "scripts/run_ppformula_on_crops.py",
        "--gold",
        str(SUBSET),
        "--model",
        "PP-FormulaNet_plus-M",
        "--prefer-tight",
        "--include-unverified",
        "--out",
        str(PP_OUT),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)


def _run_vl_single() -> None:
    cmd = [
        str(PADDLE),
        "scripts/run_paddlevl_on_crops.py",
        "--gold",
        str(SUBSET),
        "--prefer-tight",
        "--include-unverified",
        "--out",
        str(VL_OUT),
    ]
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def _run_vl_chunks(chunk: int) -> None:
    part_dir = K5_RESULTS_DIR / "paddlevl_academic100_parts"
    part_dir.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in SUBSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    for i in range(0, len(rows), chunk):
        part_out = part_dir / f"part_{i // chunk:03d}.json"
        if part_out.is_file():
            print(f"skip {part_out.name}", flush=True)
            continue
        part_gold = part_dir / f"part_{i // chunk:03d}.jsonl"
        part_gold.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[i : i + chunk]),
            encoding="utf-8",
        )
        cmd = [
            str(PADDLE),
            "scripts/run_paddlevl_on_crops.py",
            "--gold",
            str(part_gold),
            "--prefer-tight",
            "--include-unverified",
            "--out",
            str(part_out),
        ]
        print("$", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    from app.ocr.match_eval_v2 import MatchReportV2, summarize_reports

    details: list[dict] = []
    for p in sorted(part_dir.glob("part_*.json")):
        details.extend(json.loads(p.read_text(encoding="utf-8")).get("details") or [])
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
        "gold": str(SUBSET),
        "summary": summarize_reports(reports),
        "details": details,
        "shadow_only": True,
        "prefer_tight": True,
    }
    VL_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _summarize(pp: dict[str, str], vl: dict[str, str], rows: list[dict]) -> dict:
    verified_ids = {
        str(json.loads(l).get("id"))
        for l in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    }
    shadows_all = []
    shadows_verified = []
    consensus_stats = {"ACCEPT": 0, "ACCEPT_VISUAL": 0, "DISAGREE": 0, "INCOMPLETE": 0}
    for row in rows:
        rid = str(row.get("id") or "")
        pred_pp = pp.get(rid, "")
        pred_vl = vl.get(rid, "")
        cons = dual_model_consensus(pred_pp, pred_vl)
        consensus_stats[cons.decision] = consensus_stats.get(cons.decision, 0) + 1
        gold = str(row.get("gold_latex_raw") or "") if row.get("verified") else ""
        if not gold.strip() and rid in verified_ids:
            for vline in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines():
                if not vline.strip():
                    continue
                vrow = json.loads(vline)
                if str(vrow.get("id")) == rid:
                    gold = str(vrow.get("gold_latex_raw") or "")
                    break
        sh = simulate_shadow_writeback(
            pred_pp,
            pred_vl if pred_vl.strip() else pred_pp,
            gold,
            page=int(row.get("page") or 1),
            bbox=list(row.get("bbox_pdf_tight") or row.get("bbox_pdf") or []),
        )
        shadows_all.append(sh)
        if gold.strip():
            shadows_verified.append(sh)
    return {
        "n_regression_harvest": len(rows),
        "n_with_gold": len(shadows_verified),
        "consensus": consensus_stats,
        "shadow_all_no_gold_scored": {
            "accept": sum(1 for s in shadows_all if s.decision == "accept"),
            "abstain": sum(1 for s in shadows_all if s.decision == "abstain"),
        },
        "shadow_verified_subset": summarize_shadow(shadows_verified) if shadows_verified else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=0, help="0=单次加载模型跑全量；>0 分批评测（断点续跑）")
    ap.add_argument("--skip-pp", action="store_true")
    ap.add_argument("--skip-vl", action="store_true")
    ap.add_argument("--summarize-only", action="store_true")
    args = ap.parse_args()
    ensure_dirs()
    rows = _regression_rows()
    SUBSET.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print({"subset": str(SUBSET), "n": len(rows)}, flush=True)
    if args.summarize_only:
        summary = _summarize(_load_preds(PP_OUT), _load_preds(VL_OUT), rows)
    else:
        if not args.skip_pp and not PP_OUT.is_file():
            _run_pp()
        if not args.skip_vl and not VL_OUT.is_file():
            if args.chunk <= 0:
                _run_vl_single()
            else:
                _run_vl_chunks(args.chunk)
        summary = _summarize(_load_preds(PP_OUT), _load_preds(VL_OUT), rows)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "subset": str(SUBSET),
        "pp_file": str(PP_OUT),
        "vl_file": str(VL_OUT),
        "shadow_only": True,
        "production_unchanged": True,
        "do_not_train": True,
        **summary,
    }
    SUMMARY_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(SUMMARY_OUT)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
