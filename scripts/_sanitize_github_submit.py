# -*- coding: utf-8 -*-
"""Sanitize personal absolute paths inside github-submit after sync."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(r"d:\Docling\github-submit")

# Drop local-only sync helper from public tree
sync = ROOT / "scripts" / "_sync_to_github_submit.py"
if sync.is_file():
    sync.unlink()
    print("removed scripts/_sync_to_github_submit.py")


def ensure_os_import(text: str) -> str:
    if "import os" in text or "os.environ" not in text:
        return text
    if "from __future__ import annotations" in text:
        return text.replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\n\nimport os\n",
            1,
        )
    return "import os\n" + text


def ensure_resolve_import(text: str) -> str:
    if "resolve_deepseek_model_name" in text and "from app.ocr.deepseek_paths import" not in text:
        needle = "sys.path.insert(0, str(ROOT))\n"
        if needle in text:
            return text.replace(
                needle,
                needle
                + "\nfrom app.ocr.deepseek_paths import resolve_deepseek_model_name\n",
                1,
            )
    return text


def fix_text(text: str) -> str:
    t = text
    t = re.sub(
        r'model_name\s*=\s*r?"E:\\Ollama\\modelscope\\[^"]+"',
        "model_name=resolve_deepseek_model_name()",
        t,
    )
    t = re.sub(
        r"model_name\s*=\s*r?'E:\\Ollama\\modelscope\\[^']+'",
        "model_name=resolve_deepseek_model_name()",
        t,
    )
    t = re.sub(
        r'local\s*=\s*r?"E:\\Ollama\\modelscope\\[^"]+"',
        "local = resolve_deepseek_model_name()",
        t,
    )
    t = re.sub(
        r'PDF\s*=\s*Path\(\s*r?"E:\\[^"]+O-018[^"]*"\s*\)',
        'PDF = Path(os.environ["PDF2MD_BENCH_PDF"]) if os.environ.get("PDF2MD_BENCH_PDF") '
        'else (ROOT / "input" / "O-018_Abdo2025_Stacking_SHAP.pdf")',
        t,
    )
    t = re.sub(
        r'Path\(\s*r?"E:\\[^"]*OULAD[^"]*"\s*\)',
        'Path(os.environ.get("PDF2MD_BENCH_ROOT") or (ROOT / "input"))',
        t,
    )
    t = re.sub(
        r'r?"E:\\[^"]*OULAD[^"]*"',
        'os.environ.get("PDF2MD_BENCH_ROOT") or str(ROOT / "input")',
        t,
    )
    t = re.sub(
        r'r?"E:\\[^"]*O-003[^"]*"',
        'os.environ.get("PDF2MD_BENCH_O003_MD") or str(ROOT / "input" / "O-003.md")',
        t,
    )
    if "resolve_deepseek_model_name()" in t:
        t = ensure_resolve_import(t)
    if "os.environ" in t:
        t = ensure_os_import(t)
    return t


changed = 0
for p in list((ROOT / "scripts").glob("*.py")) + list((ROOT / "tests").glob("*.py")):
    orig = p.read_text(encoding="utf-8")
    new = fix_text(orig)
    if new != orig:
        p.write_text(new, encoding="utf-8")
        changed += 1
        print("fixed", p.relative_to(ROOT))

print("changed", changed)

hits = []
for p in ROOT.rglob("*.py"):
    if ".git" in p.parts or "__pycache__" in p.parts:
        continue
    tt = p.read_text(encoding="utf-8", errors="ignore")
    if "E:\\Ollama" in tt or "E:\\作1" in tt or ("E:\\" in tt and "OULAD" in tt):
        hits.append(str(p.relative_to(ROOT)))
print("remaining_hits", hits)
