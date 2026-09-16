"""可重复构建锁：声明 extras + 当前环境已装版本。CUDA 不进 GUI extra。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LOCK_NAME = "pdf2md.lock.json"


def _declared() -> dict[str, Any]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    extras: dict[str, list[str]] = {}
    deps: list[str] = ["PySide6>=6.6"]
    section = ""
    for line in text.splitlines():
        raw = line.strip()
        if raw.startswith("[") and raw.endswith("]"):
            section = raw
            continue
        if section == "[project]" and raw.startswith("dependencies"):
            parsed = [
                part.strip().strip('"').strip("'")
                for part in raw.split("=", 1)[-1].strip().strip("[]").split(",")
                if part.strip().strip('"').strip("'")
            ]
            if parsed:
                deps = parsed
            continue
        if section != "[project.optional-dependencies]":
            continue
        if "=" not in raw or raw.startswith("#"):
            continue
        name, rest = raw.split("=", 1)
        extras[name.strip()] = [
            part.strip().strip('"').strip("'")
            for part in rest.strip().strip("[]").split(",")
            if part.strip().strip('"').strip("'")
        ]
    return {"dependencies": deps, "extras": extras}


def _pin(req: str) -> dict[str, str]:
    name = req.split(">")[0].split("=")[0].split("[")[0].strip()
    dist = name.replace("_", "-")
    version = ""
    try:
        version = metadata.version(name)
    except metadata.PackageNotFoundError:
        try:
            version = metadata.version(dist)
        except metadata.PackageNotFoundError:
            version = ""
    return {"requirement": req, "name": name, "version": version}


def collect_lock() -> dict[str, Any]:
    declared = _declared()
    extras_pinned = {
        extra: [_pin(req) for req in reqs]
        for extra, reqs in declared["extras"].items()
    }
    return {
        "schema_version": "1.0",
        "format": "pdf2md.lock.json",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "requires_python": ">=3.10",
        "dependencies": [_pin(req) for req in declared["dependencies"]],
        "extras": extras_pinned,
        "isolation": {
            "gui": "pdf2md[gui]",
            "cpu_providers": ["pdf2md[docling]", "pdf2md[web]"],
            "cuda_runtimes": ["pdf2md[deepseek-ocr]", "pdf2md[paddle]", "pdf2md[mineru]"],
            "note": "CUDA runtimes stay out of the GUI extra",
        },
    }


def lock_path() -> Path:
    return ROOT / LOCK_NAME


def write_lock(path: Path | None = None) -> Path:
    dest = Path(path) if path else lock_path()
    dest.write_text(json.dumps(collect_lock(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    del argv
    path = write_lock()
    print(json.dumps({"wrote": str(path), "lock": collect_lock()}, ensure_ascii=False, indent=2))
    return 0
