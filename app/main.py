"""GUI 入口。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 保证项目根目录在 sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 国内 HF 直连易卡住；转换子进程也会继承
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# MinerU/Docling 只用 PyTorch，禁止 transformers 去加载损坏的 TensorFlow
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

# Windows 100/125/150% DPI：按真实缩放，避免按钮跳位
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

from app.dialogs.settings_dialog import load_defaults
from app.main_window import MainWindow
from app.ui.theme import install_theme
from app.utils.paths import ICONS_DIR, ensure_dirs


def main() -> int:
    ensure_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName("PDF2MD")
    app.setOrganizationName("PDF2MD")
    cfg = load_defaults()
    install_theme(app, str(cfg.get("theme", "跟随系统")))
    # Phase 5I：退出 GUI 不杀 DeepSeek daemon
    app.setQuitOnLastWindowClosed(True)
    icon_path = ICONS_DIR / "pdf2md.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    # 启动时仅当用户开启 DeepSeek-OCR-2 时才拉起 Worker（不预加载模型权重）
    try:
        from app.dialogs.settings_dialog import deepseek_ocr2_load_enabled
        from app.ocr.deepseek_worker_client import ensure_deepseek_daemon

        if deepseek_ocr2_load_enabled():

            def _bg_daemon() -> None:
                try:
                    ensure_deepseek_daemon(warmup=False)
                except Exception:
                    pass

            import threading

            threading.Thread(target=_bg_daemon, daemon=True, name="ds-daemon-ping").start()
    except Exception:
        pass
    win = MainWindow()
    if icon_path.is_file():
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
