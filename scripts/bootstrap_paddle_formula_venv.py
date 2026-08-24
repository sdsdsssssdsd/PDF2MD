#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创建 .venv-paddle-formula（与 GUI Torch 环境隔离）。

默认装 CPU paddle 以便先打通 worker；GPU 用 --gpu。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv-paddle-formula"


def _py() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", action="store_true", help="paddlepaddle-gpu cu126")
    args = ap.parse_args()

    if not VENV.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    py = _py()
    subprocess.check_call([str(py), "-m", "pip", "install", "-U", "pip"])
    if args.gpu:
        paddle = [
            str(py),
            "-m",
            "pip",
            "install",
            "paddlepaddle-gpu==3.2.0",
            "-i",
            "https://www.paddlepaddle.org.cn/packages/stable/cu126/",
        ]
    else:
        paddle = [str(py), "-m", "pip", "install", "paddlepaddle==3.2.0"]
    print("install", paddle)
    subprocess.check_call(paddle)
    subprocess.check_call(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "paddleocr",
            "pillow",
            "tokenizers",
            "ftfy",
            "paddlex[ocr]==3.7.2",
        ]
    )
    )
    print({"ok": True, "python": str(py)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
