"""干净机器冒烟：不启 Qt、不拉模型。"""
from __future__ import annotations

import json
from typing import Any


def collect_smoke() -> dict[str, Any]:
    from app.core.doctor import collect_doctor
    from app.core.protocol import protocol_manifest
    from app.core.release import collect_release_check

    doctor = collect_doctor()
    release = collect_release_check()
    errors: list[str] = []
    if release.get("qsettings_in_core"):
        errors.append("qsettings_in_core")
    if not release.get("extras_ok"):
        errors.append("extras_missing")
    if doctor.get("schema_version") != "1.0":
        errors.append("doctor_schema")
    return {
        "schema_version": "1.0",
        "ok": not errors,
        "errors": errors,
        "protocol": protocol_manifest()["protocol_version"],
        "python": doctor.get("python"),
        "lockfile": release.get("lockfile"),
        "sbom": release.get("sbom"),
        "portable": release.get("installer"),
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    payload = collect_smoke()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1
