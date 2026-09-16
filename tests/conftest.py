"""Pytest：按能力拆分环境依赖；已知缺陷用 xfail，不要让主线变红。"""
from __future__ import annotations

import os

import pytest

# GitHub Actions 无本地 PDF、DeepSeek 模板、phase4 benchmark 产物等
_CI_SKIP_FILES = frozenset(
    {
        "test_formula_crop_cache.py",
        "test_phase4d_limited_production.py",
        "test_phase5a_canary.py",
        "test_experiment_report.py",
    }
)


def _is_ci() -> bool:
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def _has_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "requires_torch: needs PyTorch installed")
    config.addinivalue_line("markers", "requires_playwright: needs Playwright and Chromium")
    config.addinivalue_line("markers", "requires_cuda: needs an NVIDIA CUDA device")


def pytest_collection_modifyitems(config, items) -> None:
    has_torch = _has_module("torch")
    has_playwright = _has_module("playwright")
    skip_torch = pytest.mark.skip(reason="requires PyTorch (issue: r51-env-torch)")
    skip_playwright = pytest.mark.skip(reason="requires Playwright (issue: r51-env-playwright)")
    skip_ci = pytest.mark.skip(reason="needs local fixtures, GPU, or UI templates (skipped in CI)")
    for item in items:
        if item.get_closest_marker("requires_torch") and not has_torch:
            item.add_marker(skip_torch)
        if item.get_closest_marker("requires_playwright") and not has_playwright:
            item.add_marker(skip_playwright)
        if _is_ci() and item.path.name in _CI_SKIP_FILES:
            item.add_marker(skip_ci)
        if (
            _is_ci()
            and item.path.name == "test_o003_formula_contamination.py"
            and item.name == "test_o003_block_batch_no_intertext"
        ):
            item.add_marker(skip_ci)
