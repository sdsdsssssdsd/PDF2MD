#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""k5 发布前一键跑齐 Recognition A/B + Gate 校准（shadow only，不改生产）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
PADDLE = ROOT / ".venv-paddle-formula" / "Scripts" / "python.exe"
GOLD = ROOT / "benchmarks" / "gold" / "verified_all.jsonl"


def _run(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    if not GOLD.is_file():
        _run([PY, "scripts/rebuild_verified_all.py"])
    _run([PY, "scripts/rebuild_verified_all.py"])
    _run([PY, "scripts/build_hard200_manifest.py"])
    if not PADDLE.is_file():
        print("missing .venv-paddle-formula", file=sys.stderr)
        return 2
    for model, out in (
        ("PP-FormulaNet_plus-M", "pp_m_verified_all_tight.json"),
        ("PP-FormulaNet_plus-L", "pp_l_verified_all_tight.json"),
    ):
        _run(
            [
                str(PADDLE),
                "scripts/run_ppformula_on_crops.py",
                "--gold",
                str(GOLD),
                "--model",
                model,
                "--prefer-tight",
                "--out",
                f"benchmarks/results/{out}",
            ]
        )
    _run(
        [
            str(PADDLE),
            "scripts/run_paddlevl_on_crops.py",
            "--gold",
            str(GOLD),
            "--prefer-tight",
            "--out",
            "benchmarks/results/paddlevl_verified_all_tight.json",
        ]
    )
    _run([PY, "scripts/run_k5_full_recognition_compare.py"])
    _run([PY, "scripts/run_shadow_gate_calibration.py"])
    print("k5 release pipeline done (shadow only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
