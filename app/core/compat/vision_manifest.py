"""`.vision/manifest.json` → `.pdf2md/run.json` 兼容适配。

旧文件只读/迁移，至少一个兼容周期内不得删除。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.pipeline.checkpoint import RunManifest, run_path, write_run_sidecar
from app.core.pipeline.planner import profile_name_for_workflow
from app.task_model import WorkflowChoice

VISION_MANIFEST_REL = ".vision/manifest.json"


def vision_manifest_path(output_dir: Path) -> Path:
    return Path(output_dir) / ".vision" / "manifest.json"


def load_legacy_vision_manifest(output_dir: Path) -> dict[str, Any] | None:
    path = vision_manifest_path(output_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _workflow_from_legacy(legacy: dict[str, Any], workflow: str = "") -> str:
    if workflow:
        return workflow
    backend = str(legacy.get("backend") or legacy.get("browser_mode") or "").lower()
    if backend in {"api", "vision_api", "deepseek_api"}:
        return WorkflowChoice.VISION_API.value
    return WorkflowChoice.VISION_WEB.value


def ensure_vision_run_compat(
    output_dir: Path,
    *,
    source: str = "",
    markdown_path: str = "",
    workflow: str = "",
) -> Path | None:
    """把旧 vision manifest 指针写入 run.json.compat。不删除 `.vision/manifest.json`。"""
    output_dir = Path(output_dir)
    legacy = load_legacy_vision_manifest(output_dir)
    if legacy is None:
        return None
    wf = _workflow_from_legacy(legacy, workflow)
    compat = {
        "vision_manifest": VISION_MANIFEST_REL,
        "backend": str(legacy.get("backend") or legacy.get("browser_mode") or ""),
        "model": str(legacy.get("model") or ""),
        "task_profile": str(legacy.get("task_profile") or ""),
    }
    existing = RunManifest.load(output_dir)
    if existing is None:
        write_run_sidecar(
            output_dir,
            workflow=wf,
            profile=profile_name_for_workflow(wf),
            source=source or str(legacy.get("pdf") or ""),
            markdown_path=markdown_path,
            status=str(legacy.get("state") or "done"),
            extra=compat,
        )
        return run_path(output_dir)
    merged = dict(existing.compat or {})
    merged.update({k: v for k, v in compat.items() if v not in (None, "")})
    existing.compat = merged
    if source and not existing.source:
        existing.source = source
    if markdown_path and not existing.markdown_path:
        existing.markdown_path = markdown_path
    if not existing.workflow:
        existing.workflow = wf
    if not existing.profile:
        existing.profile = profile_name_for_workflow(wf)
    existing.save(output_dir)
    return run_path(output_dir)
