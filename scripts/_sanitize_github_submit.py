# -*- coding: utf-8 -*-
"""Sanitize personal absolute paths inside github-submit after sync."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Drop local-only sync helper from public tree
sync = ROOT / "scripts" / "_sync_to_github_submit.py"
if sync.is_file():
    sync.unlink()
    print("removed scripts/_sync_to_github_submit.py")

for _local_only in (
    "_copy_review_crops.py",
    "_split_pending_batches.py",
):
    p = ROOT / "scripts" / _local_only
    if p.is_file():
        p.unlink()
        print(f"removed scripts/{_local_only}")

_HF_ROOT_BLOCK = re.compile(
    r"HF_ROOT\s*=\s*Path\(r?[\"']E:\\\\Ollama\\\\hf-cache[\"']\)\s*\n"
    r"HF_ROOT\.mkdir\(parents=True, exist_ok=True\)\s*\n"
    r"os\.environ\[\"HF_HOME\"\]\s*=\s*str\(HF_ROOT\)\s*\n"
    r"os\.environ\[\"HUGGINGFACE_HUB_CACHE\"\]\s*=\s*str\(HF_ROOT / \"hub\"\)\s*\n"
    r"os\.environ\[\"TRANSFORMERS_CACHE\"\]\s*=\s*str\(HF_ROOT / \"transformers\"\)\s*\n"
    r"(?:os\.environ\.setdefault\([^\n]+\)\s*\n)*",
    re.MULTILINE,
)

_ENSURE_HF_BLOCK = (
    "from app.ocr.deepseek_paths import ensure_deepseek_hf_env\n\n"
    "ensure_deepseek_hf_env()\n"
)


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
    if "resolve_dsocr2_python" in text and "from app.ocr.deepseek_paths import" not in text:
        needle = "sys.path.insert(0, str(ROOT))\n"
        if needle in text:
            return text.replace(
                needle,
                needle
                + "\nfrom app.ocr.deepseek_paths import resolve_dsocr2_python\n",
                1,
            )
    return text


def ensure_ensure_hf_import(text: str) -> str:
    if "ensure_deepseek_hf_env()" in text and "ensure_deepseek_hf_env" not in text.split("import", 1)[0]:
        needle = "sys.path.insert(0, str(ROOT))\n"
        if needle in text and "from app.ocr.deepseek_paths import ensure_deepseek_hf_env" not in text:
            return text.replace(
                needle,
                needle + "\nfrom app.ocr.deepseek_paths import ensure_deepseek_hf_env\n",
                1,
            )
    return text


def fix_text(text: str) -> str:
    t = text
    t = _HF_ROOT_BLOCK.sub(_ENSURE_HF_BLOCK, t)
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
        r'PY_DS\s*=\s*Path\(r"E:\\Ollama\\venvs\\dsocr2\\Scripts\\python\.exe"\)',
        "PY_DS = resolve_dsocr2_python() or Path(sys.executable)",
        t,
    )
    t = re.sub(
        r"\$Ds\s*=\s*'E:\\Ollama\\venvs\\dsocr2\\Scripts\\python\.exe'",
        "$Ds = if ($env:PDF2MD_DSOCR2_PYTHON) { $env:PDF2MD_DSOCR2_PYTHON } else { 'python' }",
        t,
    )
    t = re.sub(
        r"Set-Location\s+'d:\\Docling'",
        "Set-Location $PSScriptRoot\\..",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"Set-Location\s+'D:\\Docling'",
        "Set-Location $PSScriptRoot\\..",
        t,
    )
    t = re.sub(
        r'\$Paddle\s*=\s*\'d:\\Docling\\.venv-paddle-formula\\Scripts\\python\.exe\'',
        "$Paddle = if ($env:PDF2MD_PADDLE_PYTHON) { $env:PDF2MD_PADDLE_PYTHON } else { 'python' }",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r'\$Py\s*=\s*\'C:\\python\\python3-12\.3\\python\.exe\'',
        "$Py = if ($env:PDF2MD_PYTHON) { $env:PDF2MD_PYTHON } else { 'python' }",
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
        r'Path\(\s*r?"E:\\作1[^"]*"\s*\)',
        'Path(os.environ.get("PDF2MD_BENCH_ROOT") or (ROOT / "input"))',
        t,
    )
    t = re.sub(
        r'r?"E:\\[^"]*OULAD[^"]*"',
        'os.environ.get("PDF2MD_BENCH_ROOT") or str(ROOT / "input")',
        t,
    )
    t = re.sub(
        r'r?"E:\\作1[^"]*"',
        'os.environ.get("PDF2MD_BENCH_ROOT") or str(ROOT / "input")',
        t,
    )
    t = re.sub(
        r'r?"E:\\[^"]*O-003[^"]*"',
        'os.environ.get("PDF2MD_BENCH_O003_MD") or str(ROOT / "input" / "O-003_Peach2019_DataDrivenClustering.md")',
        t,
    )
    t = re.sub(
        r'Path\(r"D:\\Docling\\测试集\\论文库[^"]*"\)',
        'Path("/tmp/pdf2md/sample_高保真/bookfigures/page_0001.png")',
        t,
    )
    t = re.sub(
        r'ROOT / "docs" / "images"',
        'ROOT / "docs" / "images"',
        t,
    )
    t = re.sub(
        r'D:\\\\Docling\\\\浏览器页面',
        "docs/images/demo-01-pdf-source.png",
        t,
    )
    t = re.sub(
        r'pdf\.parent / "论文库"',
        'Path(os.environ.get("PDF2MD_BENCH_ROOT") or (ROOT / "input"))',
        t,
    )
    t = re.sub(
        r'HF_ROOT = Path\(r"\$\{PDF2MD_HF_HOME\}"\)',
        "HF_ROOT = Path(os.environ.get('PDF2MD_HF_HOME') or (ROOT / '.cache' / 'hf'))",
        t,
    )
    if "APP_ROOT" in t and "from app.utils.paths import APP_ROOT" not in t:
        if "from app.utils.paths import (" in t:
            t = t.replace(
                "from app.utils.paths import (",
                "from app.utils.paths import APP_ROOT, ",
                1,
            )
        elif "import pytest" in t:
            t = t.replace(
                "import pytest\n",
                "import pytest\n\nfrom app.utils.paths import APP_ROOT\n",
                1,
            )
    if "resolve_deepseek_model_name()" in t:
        t = ensure_resolve_import(t)
    if "resolve_dsocr2_python()" in t:
        t = ensure_resolve_import(t)
    if "ensure_deepseek_hf_env()" in t:
        t = ensure_ensure_hf_import(t)
    if "os.environ" in t:
        t = ensure_os_import(t)
    return t


SCAN_SUFFIXES = {".py", ".md", ".bat", ".ps1", ".yml", ".yaml", ".toml", ".json", ".mdc"}

changed = 0
for sub in ("app", "scripts", "tests", "data"):
    root = ROOT / sub
    if not root.exists():
        continue
    for f in root.rglob("*"):
        if not f.is_file() or f.suffix not in SCAN_SUFFIXES:
            continue
        if ".git" in f.parts or "__pycache__" in f.parts:
            continue
        orig = f.read_text(encoding="utf-8", errors="ignore")
        new = fix_text(orig)
        if new != orig:
            f.write_text(new, encoding="utf-8")
            changed += 1
            print("fixed", f.relative_to(ROOT))

print("changed", changed)

hits = []
for p in ROOT.rglob("*"):
    if not p.is_file() or p.suffix not in SCAN_SUFFIXES | {".log"}:
        continue
    if ".git" in p.parts or "__pycache__" in p.parts:
        continue
    if p.name in {"_sanitize_github_submit.py", "check_github_submit_privacy.py"}:
        continue
    tt = p.read_text(encoding="utf-8", errors="ignore")
    bad = (
        "E:\\Ollama" in tt
        or "E:\\作1" in tt
        or "D:\\Docling" in tt
        or "C:\\Users\\" in tt
        or "测试集" in tt
        or "论文库" in tt
        or "/浏览器页面" in tt
        or "\\\\浏览器页面" in tt
        or ("sk-" in tt and "sk-proj" in tt)
    )
    if bad:
        hits.append(str(p.relative_to(ROOT)))
print("remaining_hits", hits)
if hits:
    raise SystemExit(1)
