"""Benchmark Platform 2.0：工程决策，不是生产 QA。"""
from app.core.benchmark.catalog import GOLD_SUITES, GOLD_TAGS, GoldCase, load_catalog
from app.core.benchmark.delta import BenchmarkDelta, compare_reports, default_change_allowed
from app.core.benchmark.report import BenchmarkReport
from app.core.benchmark.runner import run_gold_suite

__all__ = [
    "BenchmarkDelta",
    "BenchmarkReport",
    "GOLD_SUITES",
    "GOLD_TAGS",
    "GoldCase",
    "compare_reports",
    "default_change_allowed",
    "load_catalog",
    "run_gold_suite",
]
