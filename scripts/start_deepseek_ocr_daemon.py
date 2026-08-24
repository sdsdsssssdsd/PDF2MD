# -*- coding: utf-8 -*-
"""Phase 5I：独立启动 DeepSeek OCR Daemon（可挂登录任务计划）。

用法：
  python scripts/start_deepseek_ocr_daemon.py
  python scripts/start_deepseek_ocr_daemon.py --warmup

默认：进程常驻当前 Windows 会话；60 分钟无活动后 unload 模型（进程不退）。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Start / reuse DeepSeek OCR daemon")
    ap.add_argument("--warmup", action="store_true", help="加载模型到 GPU")
    ap.add_argument(
        "--idle-unload-minutes",
        type=float,
        default=60.0,
        help="空闲多久 unload 模型（0=永不）",
    )
    args = ap.parse_args()
    unload_s = max(0.0, float(args.idle_unload_minutes) * 60.0)
    os.environ["DEEPSEEK_WORKER_IDLE_UNLOAD_SECONDS"] = str(unload_s)
    os.environ["DEEPSEEK_WORKER_IDLE_SHUTDOWN_SECONDS"] = "0"

    from app.ocr.deepseek_worker_client import ensure_deepseek_daemon, get_deepseek_worker_client

    info = ensure_deepseek_daemon(warmup=bool(args.warmup))
    print(info)
    if args.warmup:
        client = get_deepseek_worker_client()
        # 等待 load 完成（最多 240s）
        t0 = time.time()
        while time.time() - t0 < 240:
            h = client.health()
            if h.get("model_loaded"):
                print({"ready": True, "health": h})
                return 0
            time.sleep(2)
        print({"ready": False, "error": "warmup_timeout"})
        return 1
    return 0 if info.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
