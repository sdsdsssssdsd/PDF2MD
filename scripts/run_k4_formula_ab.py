#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""k4 公式级 A/B：在 gold corpus 上跑实验 A–E（不改生产 Markdown）。

示例：
  python scripts/run_k4_formula_ab.py --pdf "path/to/O-018.pdf" --fake
  python scripts/run_k4_formula_ab.py --pdf "path/to/O-018.pdf" --experiments A,B,C
  python scripts/run_k4_formula_ab.py --pdf "path/to/O-018.pdf" --allow-cpu
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ocr.deepseek_benchmark import (  # noqa: E402
    FakeDeepSeekOCR2Recognizer,
    build_o018_cases,
    run_deepseek_benchmark,
)
from app.ocr.k4_experiments import K4_EXPERIMENTS, benchmark_config_for_experiment  # noqa: E402
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs  # noqa: E402


def _fake_recognizer() -> FakeDeepSeekOCR2Recognizer:
    md_formula = "$$Recall=\\frac{TP}{TP+FN}$$"
    return FakeDeepSeekOCR2Recognizer(
        {
            "formula": md_formula,
            "region": f"Recall:\n{md_formula}",
            "page": md_formula,
            "*": md_formula,
        }
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="k4 formula A/B benchmark (experiment only)")
    p.add_argument("--pdf", required=True, help="PDF with gold cases (default O-018 corpus)")
    p.add_argument(
        "--experiments",
        default="A,B,C,D,E",
        help="Comma-separated experiment ids (A–E)",
    )
    p.add_argument("--fake", action="store_true", help="Fake DeepSeek (no GPU)")
    p.add_argument("--allow-cpu", action="store_true")
    p.add_argument("--out-dir", default="", help="Output directory (default logs/benchmark_runs)")
    args = p.parse_args(argv)

    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"PDF not found: {pdf}", file=sys.stderr)
        return 2

    ensure_dirs()
    out_root = Path(args.out_dir) if args.out_dir else BENCHMARK_RUNS
    out_root.mkdir(parents=True, exist_ok=True)
    cases = build_o018_cases(pdf)
    ids = [x.strip().upper() for x in args.experiments.split(",") if x.strip()]
    unknown = [i for i in ids if i not in K4_EXPERIMENTS]
    if unknown:
        print(f"Unknown experiments: {unknown}", file=sys.stderr)
        return 2

    fake = _fake_recognizer() if args.fake else None
    batch: dict = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "pdf_path": str(pdf),
        "k4": True,
        "experiments": {},
    }

    for eid in ids:
        spec = K4_EXPERIMENTS[eid]
        cfg = benchmark_config_for_experiment(spec, allow_cpu=args.allow_cpu)
        cfg.experiment_id = eid
        cfg.run_deepseek_region = False
        cfg.run_deepseek_page = False
        if eid != "E":
            cfg.run_baseline = False

        print(f"\n=== Experiment {eid}: {spec.label} ===", flush=True)

        payload = run_deepseek_benchmark(
            pdf,
            cfg=cfg,
            cases=cases,
            doc_recognizer=fake,
            progress=lambda m: print(f"  {m}", flush=True),
            out_path=out_root / f"k4_{eid}_{pdf.stem}.json",
        )
        batch["experiments"][eid] = {
            "label": spec.label,
            "output_path": payload.get("output_path"),
            "summary": payload.get("summary"),
            "total_seconds": payload.get("total_seconds"),
        }
        print(json.dumps(payload.get("summary"), ensure_ascii=False, indent=2))

    batch_path = out_root / f"k4_batch_{pdf.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote batch summary → {batch_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
