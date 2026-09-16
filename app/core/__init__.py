"""pdf2md core：DocumentIR + JobRunner + Hybrid Router。不依赖 Qt。"""
from app.core.domain.document import DocumentIR, document_from_markdown
from app.core.domain.job import ConversionRequest, PipelinePlan
from app.core.domain.quality import QualityReport, QualityVerdict
from app.core.qa.engine import quality_from_markdown, run_unified_qa
from app.core.pipeline.planner import plan_for_request
from app.core.pipeline.runner import JobRunner

__all__ = [
    "ConversionRequest",
    "DocumentIR",
    "JobRunner",
    "PipelinePlan",
    "QualityReport",
    "QualityVerdict",
    "document_from_markdown",
    "plan_for_request",
    "quality_from_markdown",
    "run_unified_qa",
]
