#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理重复的 DeepSeek / Paddle 公式 Worker（保留 meta 指向的 PID）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _meta_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("pid") or 0) or None
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None


def main() -> int:
    keep: set[int] = set()
    for rel in (".cache/deepseek_worker.json", ".cache/paddle_formula_worker.json"):
        pid = _meta_pid(ROOT / rel)
        if pid:
            keep.add(pid)

    # PowerShell process list
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)
        return 1

    killed = []
    for line in out.splitlines():
        if "|" not in line:
            continue
        pid_s, cmd = line.split("|", 1)
        try:
            pid = int(pid_s.strip())
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        if "deepseek_ocr_worker_server" not in cmd and "paddle_formula_worker_server" not in cmd:
            continue
        if pid in keep:
            print(f"keep pid={pid}")
            continue
        print(f"kill duplicate pid={pid} cmd={cmd[:80]}")
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            check=False,
        )
        killed.append(pid)
    print({"kept": sorted(keep), "killed": killed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
