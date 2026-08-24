#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从骨架 + 已有预测生成人工核验队列。禁止自动标 verified / 禁止当伪标签训练。"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.gold_schema import FormulaGoldRecord  # noqa: E402
from app.utils.paths import K5_CROPS_DIR, K5_GOLD_DIR, K5_RESULTS_DIR  # noqa: E402

PRED_FILES = (
    ("L0", "l0_o018_machine_pred.json"),
    ("P1_tight", "pp_m_o018_tight_v1.json"),
    ("P3_tight", "paddlevl16_o018_tight.json"),
    ("P1_skel", "pp_m_skeleton23_tight.json"),
)


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _preds_by_id() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for label, name in PRED_FILES:
        path = K5_RESULTS_DIR / name
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for d in data.get("details") or []:
            key = str(d.get("id") or "")
            if not key:
                continue
            out.setdefault(key, {})[label] = str(d.get("pred") or "")
    return out


def main() -> int:
    skeleton = K5_GOLD_DIR / "core_skeleton.jsonl"
    harvest = K5_GOLD_DIR / "harvest_display.jsonl"
    verified_files = (
        K5_GOLD_DIR / "o018_verified.jsonl",
        K5_GOLD_DIR / "human_verified_v2.jsonl",
        K5_GOLD_DIR / "harvest_display.jsonl",
    )
    rows = [_normalize(r) for r in _load_jsonl(skeleton)]
    seen_ids = {str(r.get("id") or "") for r in rows}
    if harvest.is_file():
        for r in _load_jsonl(harvest):
            gid = str(r.get("id") or "")
            if gid and gid not in seen_ids:
                rows.append(_normalize(r))
                seen_ids.add(gid)
    gold_by_id: dict[str, dict] = {}
    verified_ids: set[str] = set()
    for vf in verified_files:
        for r in _load_jsonl(vf):
            if r.get("verified") and r.get("id"):
                verified_ids.add(str(r["id"]))
                gold_by_id[str(r["id"])] = r
    preds = _preds_by_id()

    queue = []
    zh = en = verified_n = 0
    for rec in rows:
        gid = rec.get("id") or ""
        lang = rec.get("language") or "en"
        tags = list(rec.get("tags") or [])
        if "crop_rejected" in tags and gid not in verified_ids:
            continue
        if lang == "zh":
            zh += 1
        else:
            en += 1
        is_v = gid in verified_ids or bool(rec.get("verified"))
        if is_v:
            verified_n += 1
        item = {
            "id": gid,
            "pdf_id": rec.get("pdf_id"),
            "language": lang,
            "page": rec.get("page"),
            "equation_number": rec.get("equation_number"),
            "verified": is_v,
            "gold_latex_raw": (
                rec.get("gold_latex_raw")
                or (gold_by_id.get(gid) or {}).get("gold_latex_raw")
                or ""
            )
            if is_v
            else "",
            "crop_path_tight": rec.get("crop_path_tight") or "",
            "crop_quality": rec.get("crop_quality") or [],
            "machine_pred": rec.get("machine_pred") or "",
            "model_preds": preds.get(gid) or {},
            "needs_human_gt": not is_v,
            "do_not_train": True,
            "notes": rec.get("notes") or "",
        }
        queue.append(item)

    out_jsonl = K5_GOLD_DIR / "review_queue.jsonl"
    out_jsonl.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in queue) + "\n",
        encoding="utf-8",
    )
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n": len(queue),
        "verified": verified_n,
        "needs_human": len(queue) - verified_n,
        "english": en,
        "chinese": zh,
        "do_not_train": True,
        "note": "Fill gold_latex_raw by hand. Never copy machine_pred as verified GT.",
    }
    (K5_GOLD_DIR / "review_queue_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    html_path = K5_GOLD_DIR / "review_queue.html"
    html_path.write_text(_render_html(queue, summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(out_jsonl)
    print(html_path)
    return 0


def _normalize(row: dict) -> dict:
    return FormulaGoldRecord.from_dict(row).to_dict()


def _render_html(queue: list[dict], summary: dict) -> str:
    cards = []
    for item in queue:
        rel = item.get("crop_path_tight") or ""
        img = ""
        if rel:
            src = Path("..") / "crops" / rel
            img = f'<img src="{html.escape(src.as_posix())}" alt="{html.escape(item["id"])}" />'
        preds = item.get("model_preds") or {}
        pred_blocks = "".join(
            f"<p><b>{html.escape(k)}</b><code>{html.escape(v[:400])}</code></p>"
            for k, v in preds.items()
            if v
        )
        if item.get("machine_pred") and "L0" not in preds:
            pred_blocks += (
                f"<p><b>machine_pred</b><code>{html.escape(str(item['machine_pred'])[:400])}</code></p>"
            )
        status = "已核验" if item.get("verified") else "待人工写 Gold"
        cards.append(
            f"""
<section>
  <h2>{html.escape(item['id'])} <small>{status}</small></h2>
  <p>page={item.get('page')} eq={html.escape(str(item.get('equation_number') or ''))}
     quality={html.escape(','.join(item.get('crop_quality') or []))}</p>
  {img}
  {pred_blocks}
  <p>gold_latex_raw（人工填写，禁止把预测直接当 GT）：
     <code>{html.escape(item.get('gold_latex_raw') or '')}</code></p>
</section>
"""
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>k5 Gold 核验队列</title>
<style>
body{{font-family:sans-serif;max-width:960px;margin:24px auto;padding:0 16px}}
img{{max-width:100%;border:1px solid #ccc;background:#fff}}
code{{display:block;white-space:pre-wrap;background:#f6f6f6;padding:8px;margin:6px 0}}
section{{margin:28px 0;padding-bottom:16px;border-bottom:1px solid #ddd}}
small{{color:#666;font-weight:normal}}
</style></head>
<body>
<h1>k5 Gold 人工核验队列</h1>
<p>n={summary['n']} · 已核验={summary['verified']} · 待写={summary['needs_human']} ·
中文={summary['chinese']} · 英文={summary['english']}</p>
<p><b>禁止训练 / 禁止伪标签。</b>核对紧裁图后手写 LaTeX；编号单独放 equation_number。</p>
{''.join(cards)}
</body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
