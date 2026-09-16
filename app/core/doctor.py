"""pdf2md doctor：只读探测，不拉模型、不启动 Qt。"""
from __future__ import annotations

import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"


def collect_doctor() -> dict[str, Any]:
    from app.core.providers.registry import get_registry
    from app.core.runtime import get_runtime

    providers = []
    for item in get_registry().statuses():
        providers.append(
            {
                "id": item.id,
                "track": item.descriptor.track,
                "experimental": item.descriptor.experimental,
                "enabled": item.enabled,
                "available": item.available,
                "healthy": item.healthy,
                "license": item.descriptor.license_class,
                "source": item.descriptor.source,
                "reason": item.reason,
            }
        )
    python = {
        "version": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
    }
    gpu = _gpu_probe()
    disk = {}
    try:
        usage = shutil.disk_usage(str(Path.cwd()))
        disk = {
            "free_gb": round(usage.free / (1024**3), 2),
            "total_gb": round(usage.total / (1024**3), 2),
        }
    except OSError:
        disk = {}
    runtime = get_runtime().health()
    return {
        "schema_version": SCHEMA_VERSION,
        "python": python,
        "os": platform.system(),
        "gpu": gpu,
        "providers": providers,
        "runtime": runtime,
        "browser": _module_probe("playwright"),
        "api": _api_probe(),
        "disk": disk,
        "models": [
            {"id": p["id"], "available": p["available"], "healthy": p["healthy"]}
            for p in providers
        ],
        "license_notices": sorted(
            {
                f"{p['id']}:{p['license']}"
                for p in providers
                if p.get("license") and p.get("enabled")
            }
        ),
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    print(json.dumps(collect_doctor(), ensure_ascii=False, indent=2))
    return 0


def _gpu_probe() -> dict[str, Any]:
    info = {"cuda": "", "device": "", "available": False}
    try:
        import torch

        info["available"] = bool(torch.cuda.is_available())
        info["cuda"] = str(getattr(torch.version, "cuda", "") or "")
        if info["available"]:
            info["device"] = str(torch.cuda.get_device_name(0))
    except Exception:
        pass
    return info


def _module_probe(name: str) -> dict[str, Any]:
    try:
        import importlib.util

        found = importlib.util.find_spec(name) is not None
    except Exception:
        found = False
    return {"module": name, "available": found}


def _api_probe() -> dict[str, Any]:
    try:
        from app.deepseek_api.key_store import api_key_configured

        return {"deepseek_api_configured": bool(api_key_configured())}
    except Exception:
        return {"deepseek_api_configured": False}
