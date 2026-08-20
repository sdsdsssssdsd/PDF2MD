"""GUI 入口。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 保证项目根目录在 sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 不强制 HF 镜像；需要时由用户自行设置 HF_ENDPOINT
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# MinerU/Docling 只用 PyTorch，禁止 transformers 去加载损坏的 TensorFlow
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.utils.paths import ICONS_DIR, ensure_dirs


def main() -> int:
    ensure_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName("PDF2MD")
    app.setOrganizationName("PDF2MD")
    icon_path = ICONS_DIR / "pdf2md.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    win = MainWindow()
    if icon_path.is_file():
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
