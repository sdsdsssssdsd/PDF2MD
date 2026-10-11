"""Pytest：按能力拆分环境依赖；已知缺陷用 xfail，不要让主线变红。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# 会话级兜底：整个 pytest 进程（含夹具收尾、GC、atexit 阶段）写设置都只落临时 INI。
# 必要性：夹具收尾时 monkeypatch 已经还原环境变量，若此时有遗留窗口被 close()，
# MainWindow.closeEvent 会通过 settings() 写「导出目录」——曾经就这样写进真实注册表。
SESSION_SETTINGS_FILE = os.environ.setdefault(
    "PDF2MD_SETTINGS_FILE",
    str(Path(tempfile.mkdtemp(prefix="pdf2md_pytest_settings_")) / "session.ini"),
)

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


_QT_APP = None  # 会话级 QApplication 强引用：绝不能中途被 GC 掉


@pytest.fixture(scope="session", autouse=True)
def qt_application_session():
    """整个测试会话共用一个 QApplication，并在退出前把 Qt 对象按序收干净。

    GitHub Windows runner 上实测：建过 Qt 窗口的进程在解释器退出时会被
    PySide6/Qt 的析构 abort（退出码 0xC0000409，pytest 明明全绿）——既有的
    test_ui_layout_smoke 用例单独跑也会崩，说明与具体用例无关，是收尾顺序问题：
    QApplication 的 Python 包装器没人持有引用，可能先于各窗口被回收。
    这里显式持有、先删窗口、processEvents 让 deleteLater 生效、再 gc，最后才放手。
    """
    global _QT_APP
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:  # 未装 PySide6 的纯逻辑测试
        yield None
        return
    _QT_APP = QApplication.instance() or QApplication([])
    yield _QT_APP

    import gc

    for widget in list(_QT_APP.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except Exception:
            pass
    _QT_APP.processEvents()
    _QT_APP.quit()
    _QT_APP.processEvents()
    gc.collect()


@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path, monkeypatch):
    """每个测试都用独立的 QSettings 存储（临时 INI），绝不碰用户真实配置。

    事故教训：UI 测试里 MainWindow.closeEvent() 会把当前界面选项写回真实
    QSettings，曾经把用户「导出目录」改成 pytest 的临时目录，下一次真实转换就把
    结果写进了临时目录。应用侧认 PDF2MD_SETTINGS_FILE 环境变量（见
    app/dialogs/settings_dialog.py:settings），比 monkeypatch 更彻底：
    已经 `from ... import settings` 绑定过去、或在函数内部延迟导入的调用点同样生效。
    （QSettings.setDefaultFormat(IniFormat) 对 QSettings(org, app) 无效，实测仍是注册表。）
    """
    monkeypatch.setenv("PDF2MD_SETTINGS_FILE", str(tmp_path / "_qsettings.ini"))
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
