# -*- coding: utf-8 -*-
"""启动 / 复用独立 Paddle 公式 Worker（不占用 GUI venv）。

  python scripts/start_paddle_formula_daemon.py
  python scripts/start_paddle_formula_daemon.py --warmup --model PP-FormulaNet_plus-M
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Start Paddle formula worker daemon")
    ap.add_argument("--warmup", action="store_true")
    ap.add_argument("--model", default="PP-FormulaNet_plus-M")
    args = ap.parse_args()

    from app.formula.ppformula_paths import resolve_paddle_python
    from app.formula.ppformula_worker_client import get_ppformula_worker_client

    if resolve_paddle_python() is None:
        print(
            {
                "ok": False,
                "error": "PDF2MD_PADDLE_PYTHON missing; create .venv-paddle-formula first",
            }
        )
        return 2

    client = get_ppformula_worker_client()
    if not client.ping():
        spawned = client.spawn()
        if not spawned.get("ok"):
            print(spawned)
            return 1
        t0 = time.time()
        while time.time() - t0 < 20:
            if client.ping():
                break
            time.sleep(0.4)
    if not client.ping():
        print({"ok": False, "error": "worker_not_reachable"})
        return 1
    if args.warmup:
        print(client.load(args.model))
    else:
        print(client.health())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
