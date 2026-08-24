"""Playwright 子进程 JSON 协议测试。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.vision_transcribe.browser.playwright_session_client import (
    _norm_wire_path,
    _wire_dumps,
)


def test_wire_dumps_windows_path_roundtrip():
    p = Path(r"D:\Docling\测试集\论文库\foo_高保真\bookfigures\page_0001.png")
    line = _wire_dumps({"cmd": "submit", "images": [p], "prompt": "ok"}) + "\n"
    obj = json.loads(line)
    assert obj["images"][0] == _norm_wire_path(p)
    assert "\\" not in obj["images"][0]


def test_wire_dumps_survives_subprocess_pipe():
    p = Path(r"D:\Docling\测试集\论文库\foo_高保真\bookfigures\page_0001.png")
    line = _wire_dumps({"cmd": "submit", "images": [p], "prompt": "test"}) + "\n"
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys,json; json.loads(sys.stdin.readline()); print('ok')",
        ],
        input=line,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=10,
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
