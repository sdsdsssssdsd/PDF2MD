"""Pytest：CI 上跳过需本地 fixture / GPU / UI 模板的用例。"""
from __future__ import annotations

import os

import pytest

# GitHub Actions 无本地 PDF、DeepSeek 模板、phase4 benchmark 产物等
_CI_SKIP_FILES = frozenset(
    {
        "test_dom_locator.py",
        "test_deepseek_ocr_phase1.py",
        "test_deepseek_formula_prompt.py",
        "test_formula_crop_cache.py",
        "test_phase4d_limited_production.py",
        "test_phase5a_canary.py",
        "test_experiment_report.py",
    }
)


def _is_ci() -> bool:
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def pytest_collection_modifyitems(config, items) -> None:
    if not _is_ci():
        return
    reason = "needs local fixtures, GPU, or UI templates (skipped in CI)"
    mark = pytest.mark.skip(reason=reason)
    for item in items:
        if item.path.name in _CI_SKIP_FILES:
            item.add_marker(mark)
        if (
            item.path.name == "test_o003_formula_contamination.py"
            and item.name == "test_o003_block_batch_no_intertext"
        ):
            item.add_marker(mark)
