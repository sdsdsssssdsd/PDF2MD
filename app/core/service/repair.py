"""格式修正服务：Qt 无关。产物是 MarkdownArtifact，不是 DocumentIR。"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.core.domain.artifact import MarkdownArtifact
from app.core.runtime import ResourceKind, get_runtime
from app.format_repair.file_io import FileSnapshot
from app.format_repair.models import FormatRepairResult, RepairConfig
from app.format_repair.pipeline import repair_text


class RepairService:
    def run(
        self,
        text: str,
        config: RepairConfig,
        *,
        source_path: Path | None = None,
        snapshot: FileSnapshot | None = None,
        chat_fn=None,
    ) -> tuple[FormatRepairResult, MarkdownArtifact]:
        job_id = uuid4().hex[:12]
        with get_runtime().job_scope(job_id, kinds=(ResourceKind.CPU,)):
            result = repair_text(
                text,
                config=config,
                source_path=source_path,
                snapshot=snapshot,
                chat_fn=chat_fn,
            )
            artifact = MarkdownArtifact(
                workflow="格式修正",
                source=str(source_path or ""),
                path=str((result.report or {}).get("saved_path") or ""),
                text=result.output_text,
                extra={
                    "integrity_ok": result.integrity_ok,
                    "warnings": list(result.warnings),
                    "errors": list(result.errors),
                },
            )
            return result, artifact
