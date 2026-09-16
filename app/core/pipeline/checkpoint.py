""".pdf2md/run.json：只引用 IR 与 QA，不内嵌评价分数。schema_version=1.0。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.domain.document import DocumentIR
from app.core.domain.job import Job
from app.core.domain.quality import QualityReport
from app.core.pipeline.stage import StageResult

SCHEMA_VERSION = "1.0"
DOCUMENT_IR_NAME = "document.ir.json"
QUALITY_REPORT_NAME = "qa.json"
COMPAT_EXTRA_KEYS = (
    "vision_manifest",
    "backend",
    "model",
    "task_profile",
    "source_count",
    "markdown_artifact",
)


def pdf2md_dir(output_dir: Path) -> Path:
    return Path(output_dir) / ".pdf2md"


def run_path(output_dir: Path) -> Path:
    return pdf2md_dir(output_dir) / "run.json"


@dataclass
class RunManifest:
    schema_version: str = SCHEMA_VERSION
    job_id: str = ""
    workflow: str = ""
    profile: str = ""
    parser: str | None = None
    status: str = "pending"
    source: str = ""
    markdown_path: str = ""
    created_at: str = ""
    stages: list[dict[str, Any]] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)
    document_ir: str = ""
    quality_report: str = ""
    compat: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def for_job(cls, job: Job) -> RunManifest:
        return cls(
            job_id=job.id,
            workflow=job.request.workflow,
            profile=job.plan.profile,
            parser=job.plan.parser,
            status=job.status,
            source=str(job.request.source_path),
            created_at=datetime.now(timezone.utc).isoformat(),
            plan=job.plan.to_dict(),
        )

    def record_stage(self, result: StageResult) -> None:
        self.stages.append(
            {
                "name": result.name,
                "status": result.status,
                "retryable": result.retryable,
                "error": result.error,
                "warnings": list(result.warnings),
                "metrics": dict(result.metrics),
            }
        )
        if result.status == "failed":
            self.status = "failed"
        elif self.status == "pending":
            self.status = "running"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "workflow": self.workflow,
            "profile": self.profile,
            "parser": self.parser,
            "status": self.status,
            "source": self.source,
            "markdown_path": self.markdown_path,
            "created_at": self.created_at,
            "plan": dict(self.plan),
            "stages": list(self.stages),
            "document_ir": self.document_ir,
            "quality_report": self.quality_report,
        }
        if self.compat:
            payload["compat"] = dict(self.compat)
        return payload

    def save(self, output_dir: Path) -> Path:
        path = run_path(output_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, output_dir: Path) -> RunManifest | None:
        path = run_path(output_dir)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if "schema" in data and "schema_version" not in data:
            data["schema_version"] = str(data.pop("schema"))
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in known})


def write_run_sidecar(
    output_dir: Path,
    *,
    workflow: str,
    profile: str,
    parser: str | None = None,
    source: str = "",
    markdown_path: str = "",
    status: str = "done",
    plan: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    document: DocumentIR | None = None,
    quality: QualityReport | None = None,
    stages: list[dict[str, Any]] | None = None,
    job_id: str = "",
) -> Path:
    """写入 run.json（引用）、document.ir.json（事实）、qa.json（评价）。"""
    extra = dict(extra or {})
    compat = {
        k: extra[k]
        for k in COMPAT_EXTRA_KEYS
        if extra.get(k) not in (None, "")
    }
    root = pdf2md_dir(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    ir_name = ""
    qa_name = ""
    if document is not None:
        document.save(root / DOCUMENT_IR_NAME)
        ir_name = DOCUMENT_IR_NAME
    if quality is not None:
        quality.save(root / QUALITY_REPORT_NAME)
        qa_name = QUALITY_REPORT_NAME
        if status not in {"cancelled"}:
            status = quality.status
    payload = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "workflow": workflow,
        "profile": profile,
        "parser": parser,
        "status": status,
        "source": source,
        "markdown_path": markdown_path,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "plan": dict(plan or {}),
        "stages": list(stages or []),
        "document_ir": ir_name,
        "quality_report": qa_name,
    }
    if compat:
        payload["compat"] = compat
    path = run_path(output_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
