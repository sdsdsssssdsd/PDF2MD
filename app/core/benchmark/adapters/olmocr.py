"""olmOCR-Bench adapter：machine-checkable 外部集，不进普通 PR CI。"""
from __future__ import annotations

import os
from pathlib import Path

from app.core.benchmark.report import BenchmarkReport, skipped_report

ENV_ROOT = "PDF2MD_OLMOCR_ROOT"
ADAPTER_NAME = "olmocr_bench"


def dataset_root() -> Path | None:
    raw = os.environ.get(ENV_ROOT, "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def available() -> bool:
    return dataset_root() is not None


def run() -> BenchmarkReport:
    root = dataset_root()
    if root is None:
        return skipped_report(
            ADAPTER_NAME,
            f"dataset missing; set {ENV_ROOT} and run nightly/manual",
        )
    return BenchmarkReport(
        suite=ADAPTER_NAME,
        adapter=ADAPTER_NAME,
        cases=0,
        passed=0,
        skipped=True,
        skip_reason="eval_env_not_bundled",
        extras={"root": str(root), "ci_policy": "nightly_or_manual"},
    )
