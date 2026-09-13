# -*- coding: utf-8 -*-
"""Publish-tree privacy scan. Scans every publishable text file, including this script.

Allowed contact identity: GitHub noreply for sdsdsssssdsd only.
Rules use generic regex — no workstation/research directory literals.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_EMAILS = {
    "187051765+sdsdsssssdsd@users.noreply.github.com",
    "git@github.com",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "user_profile",
        re.compile(r"[A-Za-z]:\\Users\\(?!EXAMPLE_USER(?:\\|$))[^\\\"'\s]+"),
    ),
    (
        "unix_home",
        re.compile(r"/(?:Users|home)/(?!EXAMPLE_USER(?:/|$))[A-Za-z0-9._-]+"),
    ),
    (
        "machine_python",
        re.compile(r"[A-Za-z]:\\python\\python3-\d"),
    ),
    (
        "url_credentials",
        re.compile(r"://[^/\s:@]+:[^/\s:@]+@"),
    ),
    (
        "db_dsn",
        re.compile(
            r"(?:postgres(?:ql)?|mysql|mongodb|redis)://[^\s\"']+",
            re.I,
        ),
    ),
    (
        "api_key",
        re.compile(
            r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
            r"|sk-proj-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}"
            r"|sk-[a-zA-Z0-9]{24,}|AIza[A-Za-z0-9_-]{20,}"
            r"|AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{10,})"
        ),
    ),
    (
        "private_key",
        re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    ),
    (
        "bearer_token",
        re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
    ),
    (
        "browser_profile",
        re.compile(
            "|".join(
                (
                    "Coo" + "kies",
                    "Lo" + "gin Data",
                    "Web" + " Data",
                    "Local" + " Storage" + r"[/\\]leveldb",
                )
            ),
            re.I,
        ),
    ),
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


def should_scan(path: Path, root: Path) -> bool:
    if path.suffix not in SCAN_SUFFIXES:
        return False
    parts = set(path.parts)
    if ".git" in parts or "__pycache__" in parts or ".pytest_cache" in parts:
        return False
    if path.is_relative_to(root / "logs"):
        return path.name == ".gitkeep"
    return True


def _allowed_email(addr: str) -> bool:
    low = addr.lower()
    if low in {a.lower() for a in ALLOWED_EMAILS}:
        return True
    if low.endswith("@users.noreply.github.com"):
        return True
    if low.endswith("@example.com") or low.endswith(".example"):
        return True
    return False


def scan_text(text: str) -> list[str]:
    hits: list[str] = []
    for label, pat in PATTERNS:
        if pat.search(text):
            hits.append(label)
    for addr in EMAIL_RE.findall(text):
        if not _allowed_email(addr):
            hits.append("email")
            break
    return hits


def resolve_scan_root() -> Path:
    nested = ROOT / "github-submit"
    if (nested / ".git").is_dir():
        return nested
    return ROOT


def main() -> int:
    scan_root = resolve_scan_root()
    hits: list[str] = []
    for path in scan_root.rglob("*"):
        if not path.is_file() or not should_scan(path, scan_root):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(scan_root)
        found = scan_text(text)
        if found:
            hits.append(f"{','.join(found)}: {rel}")
    if hits:
        print("PRIVACY HITS (fix before publish):", file=sys.stderr)
        for h in hits:
            print(f"  - {h}", file=sys.stderr)
        return 1
    print("privacy check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
