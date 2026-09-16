"""日常识图服务：Qt 无关。算法仍在 DailyVisionPipeline。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.core.domain.artifact import MarkdownArtifact
from app.core.runtime import ResourceKind, get_runtime
from app.daily_vision.exporter import export_archive
from app.daily_vision.pipeline import DailyVisionPipeline


@dataclass
class DailyVisionOutcome:
    ok: bool
    markdown: str = ""
    archive_path: str = ""
    error: str = ""
    artifact: MarkdownArtifact | None = None


class DailyVisionService:
    def run(
        self,
        image_paths: list[Path],
        *,
        archive: bool = False,
        archive_dir: Path | None = None,
        log: Callable[[str], None] | None = None,
    ) -> DailyVisionOutcome:
        log_fn = log or (lambda _m: None)
        paths = [Path(p) for p in image_paths]
        job_id = uuid4().hex[:12]
        try:
            with get_runtime().job_scope(job_id, kinds=(ResourceKind.API,)):
                pipe = DailyVisionPipeline(log=log_fn)
                result = pipe.transcribe(paths)
            md = result.markdown
            artifact = MarkdownArtifact(
                workflow="日常识图",
                source=str(paths[0]) if paths else "",
                text=md,
            )
            if archive and archive_dir:
                md_path = export_archive(paths, result, archive_dir)
                artifact.path = str(md_path)
                return DailyVisionOutcome(
                    ok=True,
                    markdown=md,
                    archive_path=str(md_path),
                    artifact=artifact,
                )
            return DailyVisionOutcome(ok=True, markdown=md, artifact=artifact)
        except Exception as exc:
            return DailyVisionOutcome(ok=False, error=str(exc))
