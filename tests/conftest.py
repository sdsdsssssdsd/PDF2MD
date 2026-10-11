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


@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path, monkeypatch):
    """每个测试都用独立的 QSettings 存储（临时 INI），绝不碰用户真实配置。

    事故教训：UI 测试里 MainWindow.closeEvent() 会把当前界面选项写回真实
    QSettings，曾经把用户「导出目录」改成 pytest 的临时目录，导致下一次真实转换
    把结果写进临时目录。QSettings.setDefaultFormat() 对 QSettings(org, app)
    无效（实测仍是 NativeFormat/注册表），所以这里直接替换 settings() 工厂。
    """
    try:
        from PySide6.QtCore import QSettings
    except Exception:  # 未装 PySide6 的纯逻辑测试
        yield
        return

    import sys

    import app.dialogs.settings_dialog as settings_dialog

    ini_path = tmp_path / "_qsettings.ini"

    def _isolated_settings() -> "QSettings":
        return QSettings(str(ini_path), QSettings.Format.IniFormat)

    monkeypatch.setattr(settings_dialog, "settings", _isolated_settings)
    main_window = sys.modules.get("app.main_window")
    if main_window is not None:  # 该模块用 from ... import settings 绑定了引用
        monkeypatch.setattr(main_window, "settings", _isolated_settings, raising=False)
    yield


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
