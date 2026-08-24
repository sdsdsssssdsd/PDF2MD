# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def walk_attempts(shadow: dict):
    for pg in shadow.get("pages") or []:
        if not isinstance(pg, dict):
            continue
        exe = pg.get("execution") or {}
        for att in exe.get("candidates") or []:
            yield att
    for att in shadow.get("attempts") or []:
        yield att


def classify(gate: str, fc: str) -> str:
    if gate == "skip_non_equation_number":
        return "0_skip_bad_eq_number"
    if gate == "no_equation_blocks" or fc == "extraction_failure":
        return "2_ocr_prose_not_formula"
    if gate == "ocr_context_conflict" or fc == "context_strong_conflict":
        return "3_ocr_gate_context_conflict"
    if gate == "gain_accept" or fc == "accepted":
        return "4_ok_accepted"
    if gate:
        return f"5_gate_{gate[:24]}"
    return "Z_other"


def analyze(qa_path: Path) -> list[dict]:
    d = json.loads(qa_path.read_text(encoding="utf-8"))
    name = qa_path.parent.name
    shadow = d.get("deepseek_shadow") or {}
    wb = d.get("writeback") or {}
    wb_map = {
        e.get("candidate_id"): e for e in (wb.get("entries") or []) if e.get("candidate_id")
    }
    fails = d.get("formula_failures") or []
    rows: list[dict] = []

    for att in walk_attempts(shadow):
        cid = att.get("candidate_id") or ""
        eq = att.get("eq_number") or ""
        page = att.get("page")
        gate = att.get("gate_reason") or ""
        fc = att.get("failure_class") or ""
        raw = (att.get("raw_output") or "").replace("\n", " ")[:100]
        rec = (att.get("recovered") or att.get("selected_latex") or "").replace("\n", " ")[:80]
        t = att.get("timing") or {}
        cw, ch = t.get("crop_px_width"), t.get("crop_px_height")
        wb_e = wb_map.get(cid) or {}
        bbox = None
        for f in fails:
            if f.get("page") == page and cid and cid in str(f.get("context_before", "")):
                bbox = f.get("bbox")
        if bbox is None and cid:
            for f in fails:
                key = f"page{page}_eq"
                if cid.startswith(f"page{page}_"):
                    bbox = f.get("bbox")
                    break
        stage = classify(gate, fc)
        rows.append(
            {
                "doc": name,
                "eq": eq,
                "page": page,
                "cid": cid,
                "stage": stage,
                "gate": gate,
                "fc": fc,
                "crop": f"{cw}x{ch}",
                "wb": wb_e.get("writeback_applied"),
                "raw": raw,
                "rec": rec,
                "bbox_h": round((bbox[3] - bbox[1]) if bbox else 0, 1),
            }
        )

    nd = [x for x in (d.get("details") or []) if x.get("status") == "no_bbox_or_deepseek_off"]
    ctr = Counter(r["stage"] for r in rows)
    print(f"\n{'=' * 80}")
    print(name)
    print(
        f"corrupted={d.get('corrupted_formula_count')} ocr_calls={((shadow.get('summary') or {}).get('ocr_calls'))} "
        f"wb_applied={wb.get('applied_count')} no_bbox_slots={len(nd)}"
    )
    print("stage:", dict(ctr))
    for r in rows:
        print(
            f"  p{r['page']:>2} eq({str(r['eq']):>4}) {r['stage']:32} "
            f"crop={r['crop']:>10} bbox_h={r['bbox_h']:>5} wb={r['wb']} "
            f"| {r['raw'][:70]}"
        )
    for i, slot in enumerate(nd[:8]):
        print(f"  [no_bbox #{i+1}] ctx={str(slot.get('context_before',''))[-60:]}")
    return rows


def main() -> None:
    names = sys.argv[1:] or [
        "O-003_Peach2019_DataDrivenClustering",
        "O-024_Le2026_LEAP_arXiv",
        "en_O-028_Almazroei2026_SHAP_LIME",
        "3785022.3785030",
        "O-025_daSilva2026_Survival_arXiv",
        "O-018_Abdo2025_Stacking_SHAP",
    ]
    all_rows: list[dict] = []
    for n in names:
        p = ROOT / "logs" / "experiment" / n / f"{n}.formula_qa.json"
        if p.is_file():
            all_rows.extend(analyze(p))

    print(f"\n{'=' * 80}")
    print("GLOBAL stage counts:")
    for k, v in Counter(r["stage"] for r in all_rows).most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
