# -*- coding: utf-8 -*-
"""发布前隐私扫描：在 github-submit 根目录运行，命中则 exit 1。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("windows_abs_path", re.compile(r"[A-Za-z]:\\(?:Users|作1|Ollama|Docling)")),
    ("hf_cache_hardcode", re.compile(r"E:\\\\Ollama")),
    ("personal_folder", re.compile(r"测试集|论文库|/浏览器页面|\\\\浏览器页面")),
    ("user_profile", re.compile(r"C:\\\\Users\\\\")),
    ("api_key", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}")),
    ("email", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
]

SCAN_SUFFIXES = {
    ".py",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".bat",
    ".ps1",
    ".mdc",
    ".log",
    ".html",
    ".txt",
}

SKIP_NAMES = {
    "_sanitize_github_submit.py",
    "check_github_submit_privacy.py",
}


def should_scan(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return False
    if path.suffix not in SCAN_SUFFIXES:
        return False
    parts = set(path.parts)
    if ".git" in parts or "__pycache__" in parts or ".pytest_cache" in parts:
        return False
    if path.is_relative_to(ROOT / "logs"):
        return path.name == ".gitkeep"
    return True


def main() -> int:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = path.relative_to(ROOT)
        for label, pat in PATTERNS:
            if pat.search(text):
                hits.append(f"{label}: {rel}")
                break
    if hits:
        print("PRIVACY HITS (fix before publish):", file=sys.stderr)
        for h in hits:
            print(f"  - {h}", file=sys.stderr)
        return 1
    print("privacy check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
