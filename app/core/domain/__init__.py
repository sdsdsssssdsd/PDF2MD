"""Core domain models."""
from app.core.domain.artifact import MarkdownArtifact
from app.core.domain.document import (
    ArtifactIR,
    BlockIR,
    DocumentIR,
    PageIR,
    Provenance,
    RelationIR,
    document_from_markdown,
)
from app.core.domain.job import (
    CancellationToken,
    ConversionRequest,
    Job,
    JobResult,
    JobStatus,
    PipelinePlan,
)
from app.core.domain.quality import QualityReport, QualityVerdict
from app.core.domain.recovery import RecoveryPatch, RecoveryRequest
from app.core.qa.engine import quality_from_markdown

__all__ = [
    "ArtifactIR",
    "BlockIR",
    "CancellationToken",
    "ConversionRequest",
    "DocumentIR",
    "Job",
    "JobResult",
    "JobStatus",
    "MarkdownArtifact",
    "PageIR",
    "PipelinePlan",
    "Provenance",
    "QualityReport",
    "QualityVerdict",
    "RecoveryPatch",
    "RecoveryRequest",
    "RelationIR",
    "document_from_markdown",
    "quality_from_markdown",
]
