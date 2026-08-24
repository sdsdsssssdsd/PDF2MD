#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""k5 串行评测流水线（Python 版，避免 PowerShell stderr 误判）。"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PADDLE = ROOT / ".venv-paddle-formula" / "Scripts" / "python.exe"
PY = Path(r"C:\python\python3-12.3\python.exe")
GOLD = ROOT / "benchmarks" / "gold" / "verified_all.jsonl"
RES = ROOT / "benchmarks" / "results"
LOG = RES / f"k5_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOCK = RES / ".k5_pipeline.lock"


def _acquire_lock() -> None:
    if LOCK.is_file():
        raise SystemExit(f"lock exists ({LOCK.read_text(encoding='utf-8').strip()}); another pipeline running?")
    LOCK.write_text(f"pid={__import__('os').getpid()}\n", encoding="utf-8")


def _release_lock() -> None:
    LOCK.unlink(missing_ok=True)


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run(name: str, cmd: list[str], *, inherit_io: bool = False) -> None:
    log(f"=== {name} ===")
    log("$ " + " ".join(cmd))
    if inherit_io:
        code = subprocess.run(cmd, cwd=ROOT).returncode
    else:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        with LOG.open("a", encoding="utf-8") as f:
            if proc.stdout:
                f.write(proc.stdout)
                if not proc.stdout.endswith("\n"):
                    f.write("\n")
            if proc.stderr:
                f.write(proc.stderr)
                if not proc.stderr.endswith("\n"):
                    f.write("\n")
        code = proc.returncode
    if code != 0:
        raise SystemExit(f"{name} failed exit={code}")


def _l2_gap() -> int:
    v = sum(1 for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip())
    scored = set()
    for f in RES.glob("deepseek_l2_verified*.json"):
        for d in json.loads(f.read_text(encoding="utf-8")).get("details") or []:
            scored.add(d["id"])
    return v - len(scored)


def main() -> int:
    _acquire_lock()
    try:
        return _main_body()
    finally:
        _release_lock()


def _main_body() -> int:
    if not PADDLE.is_file():
        print("missing paddle venv", file=sys.stderr)
        return 2
    ppl = RES / "pp_l_verified_all_tight.json"
    pvl = RES / "paddlevl_verified_all_tight.json"
    steps: list[tuple[str, list[str]]] = []
    if not ppl.is_file():
        steps.append(
            (
                "PP-L 361",
                [
                    str(PADDLE),
                    "scripts/run_ppformula_on_crops.py",
                    "--gold",
                    str(GOLD),
                    "--model",
                    "PP-FormulaNet_plus-L",
                    "--prefer-tight",
                    "--out",
                    str(ppl),
                ],
            )
        )
    if not pvl.is_file():
        steps.append(
            (
                "PaddleVL 361",
                [
                    str(PY),
                    "scripts/run_paddlevl_chunks.py",
                    "--chunk",
                    "20",
                ],
            )
        )
    if _l2_gap() > 0:
        steps.append(("L2 chunks", [str(PY), "scripts/run_l2_unscored_chunks.py", "--chunk", "10"]))
    steps.extend(
        [
            ("compare", [str(PY), "scripts/run_k5_full_recognition_compare.py"]),
            ("shadow gate", [str(PY), "scripts/run_shadow_gate_calibration.py"]),
            ("hard200", [str(PY), "scripts/build_hard200_manifest.py"]),
            ("snapshot", [str(PY), "scripts/write_k5_progress_snapshot.py"]),
        ]
    )
    for name, cmd in steps:
        inherit = "paddlevl" in " ".join(cmd).lower() or "ppformula" in " ".join(cmd).lower() or "deepseek" in " ".join(cmd).lower()
        run(name, cmd, inherit_io=inherit)
    log("=== DONE ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
