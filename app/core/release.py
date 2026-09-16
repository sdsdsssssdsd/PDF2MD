"""发行检查：extras / doctor / lock / SBOM / portable。不做 MSI installer。"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _pyproject_extras() -> list[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    names: list[str] = []
    in_extras = False
    for line in text.splitlines():
        raw = line.strip()
        if raw.startswith("[project.optional-dependencies]"):
            in_extras = True
            continue
        if in_extras and raw.startswith("["):
            break
        if in_extras and "=" in raw and not raw.startswith("#"):
            names.append(raw.split("=", 1)[0].strip())
    return names


def _core_uses_qsettings() -> bool:
    core = ROOT / "app" / "core"
    for path in core.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "QSettings" in alias.name:
                        return True
            elif isinstance(node, ast.ImportFrom):
                names = [a.name for a in node.names]
                if "QSettings" in names:
                    return True
                if (node.module or "").endswith("QtCore") and "QSettings" in names:
                    return True
    return False


def collect_release_check() -> dict[str, Any]:
    from app.core.doctor import collect_doctor
    from app.core.protocol import protocol_manifest

    extras = _pyproject_extras()
    required = {"gui", "docling", "mineru", "paddle", "web", "deepseek-ocr", "bench", "dev"}
    doctor = collect_doctor()
    from app.core.lockfile import LOCK_NAME, lock_path
    from app.core.sbom import SBOM_NAME, sbom_path

    return {
        "schema_version": "1.0",
        "protocol": protocol_manifest(),
        "extras": extras,
        "extras_ok": required.issubset(set(extras)),
        "qsettings_in_core": _core_uses_qsettings(),
        "lockfile": {
            "uv.lock": (ROOT / "uv.lock").is_file(),
            "pdf2md.lock.json": lock_path().is_file(),
            "name": LOCK_NAME,
            "note": "CUDA runtimes stay out of the GUI extra",
        },
        "sbom": {
            "path": SBOM_NAME,
            "present": sbom_path().is_file(),
            "format": "CycloneDX-1.5",
        },
        "doctor": {
            "schema_version": doctor.get("schema_version"),
            "os": doctor.get("os"),
        },
        "isolation": "subprocess + ResourceRuntime",
        "installer": "portable-script",
        "portable_script": "scripts/run-portable.ps1",
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    print(json.dumps(collect_release_check(), ensure_ascii=False, indent=2))
    return 0
