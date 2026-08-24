# -*- coding: utf-8 -*-
"""dsocr2 子进程：对 pending 公式跑 DeepSeek Shadow，写出 would_replace JSON。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HF_ROOT = Path(r"E:\Ollama\hf-cache")
HF_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(HF_ROOT)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(HF_ROOT / "hub")
os.environ["TRANSFORMERS_CACHE"] = str(HF_ROOT / "transformers")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: deepseek_limited_pass_worker.py in.json out.json", file=sys.stderr)
        return 2
    inp = Path(sys.argv[1])
    outp = Path(sys.argv[2])
    data = json.loads(inp.read_text(encoding="utf-8"))

    from app.formula.config import formula_config_for_deepseek_limited_production
    from app.formula.deepseek_production_pass import _cand_from_payload, run_shadow_inprocess

    cfg_over = data.get("config") or {}
    cfg = formula_config_for_deepseek_limited_production(**cfg_over)
    pdf = Path(data["pdf"])
    cands = []
    for row in data.get("candidates") or []:
        cid = str(row.get("candidate_id") or "")
        cands.append((cid, _cand_from_payload(row)))

    model_name = str(data.get("model_name") or "") or None
    shadow = run_shadow_inprocess(pdf, cands, cfg, model_name=model_name)
    summary = shadow.get("summary") or {}
    rows = list(summary.get("would_replace") or [])
    outp.write_text(json.dumps(shadow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ok pending={len(cands)} would_replace={len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
