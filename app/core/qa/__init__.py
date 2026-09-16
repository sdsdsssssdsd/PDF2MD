"""统一 QA。"""
from app.core.domain.quality import QualityReport, QualityVerdict
from app.core.qa.engine import UNIFIED_CHECK_IDS, quality_from_markdown, run_unified_qa
from app.core.qa.gold import GoldExpectations, evaluate_gold, load_gold_dir

__all__ = [
    "GoldExpectations",
    "QualityReport",
    "QualityVerdict",
    "UNIFIED_CHECK_IDS",
    "evaluate_gold",
    "load_gold_dir",
    "quality_from_markdown",
    "run_unified_qa",
]
