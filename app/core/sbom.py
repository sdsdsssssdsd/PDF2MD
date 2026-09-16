"""CycloneDX-lite SBOM：声明依赖 + 已装版本。不扫描 CUDA venv。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.lockfile import LOCK_NAME, collect_lock, lock_path

ROOT = Path(__file__).resolve().parents[2]
SBOM_NAME = "sbom.cdx.json"


def collect_sbom() -> dict[str, Any]:
    lock = collect_lock()
    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in lock["dependencies"]:
        key = str(item["name"]).lower()
        if key in seen:
            continue
        seen.add(key)
        components.append(
            {
                "type": "library",
                "name": item["name"],
                "version": item["version"] or "unspecified",
                "scope": "required",
            }
        )
    for extra, reqs in lock["extras"].items():
        for item in reqs:
            key = f"{item['name']}:{extra}".lower()
            if key in seen:
                continue
            seen.add(key)
            components.append(
                {
                    "type": "library",
                    "name": item["name"],
                    "version": item["version"] or "unspecified",
                    "scope": "optional",
                    "properties": [{"name": "pdf2md:extra", "value": extra}],
                }
            )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": "pdf2md",
                "version": "0.1.0a0",
                "licenses": [{"license": {"id": "Apache-2.0"}}],
            },
            "properties": [
                {"name": "pdf2md:lock", "value": LOCK_NAME},
                {"name": "pdf2md:lock_present", "value": str(lock_path().is_file()).lower()},
            ],
        },
        "components": components,
    }


def sbom_path() -> Path:
    return ROOT / SBOM_NAME


def write_sbom(path: Path | None = None) -> Path:
    dest = Path(path) if path else sbom_path()
    dest.write_text(json.dumps(collect_sbom(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    del argv
    path = write_sbom()
    print(json.dumps({"wrote": str(path), "components": len(collect_sbom()["components"])}, indent=2))
    return 0
