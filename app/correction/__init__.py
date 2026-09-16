"""Correction Core（legacy）：R14 起不再作为默认路径，算法保留。"""
from app.correction.models import CorrectionConfig, CorrectionContext, CorrectionResult
from app.correction.pipeline import CorrectionPipeline
from app.correction.report import correction_report_path, write_correction_report

LEGACY = True
PHASE = "legacy_correction"

__all__ = [
    "LEGACY",
    "PHASE",
    "CorrectionConfig",
    "CorrectionContext",
    "CorrectionPipeline",
    "CorrectionResult",
    "correction_report_path",
    "write_correction_report",
]
