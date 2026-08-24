# -*- coding: utf-8 -*-
"""诊断缓存管理：查看 / 清除 logs/experiment（实验结果 sidecar）。"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.ui.widgets.notice import Notice
from app.utils.paths import EXPERIMENT_DIR, ensure_dirs


def _dir_stats(root: Path) -> tuple[int, int, int]:
    """返回 (子目录数, 文件数, 字节数)。"""
    n_dirs = 0
    n_files = 0
    nbytes = 0
    if not root.exists():
        return 0, 0, 0
    for p in root.rglob("*"):
        if p.is_dir():
            n_dirs += 1
        elif p.is_file():
            n_files += 1
            try:
                nbytes += p.stat().st_size
            except OSError:
                pass
    return n_dirs, n_files, nbytes


def _mtime(p: Path) -> str:
    try:
        from datetime import datetime

        return datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M")
    except OSError:
        return ""


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


class ExperimentCacheDialog(QDialog):
    """查看并清除程序目录下的实验结果诊断缓存。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("诊断缓存")
        self.resize(640, 480)
        ensure_dirs()

        root = QVBoxLayout(self)
        root.addWidget(
            Notice(
                "Diagnostic mirror",
                "这是实验镜像，不是论文输出。转换成功时这里也可能持续增长；"
                "清理不会删除论文 Markdown。Failure Memory 不在此窗口。",
                tone="info",
            )
        )
        self.lbl_path = QLabel()
        self.lbl_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_path.setProperty("role", "muted")
        root.addWidget(self.lbl_path)

        self.lbl_stats = QLabel()
        self.lbl_stats.setProperty("role", "muted")
        root.addWidget(self.lbl_stats)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["名称", "大小", "类型", "修改时间"])
        self.tree.setColumnWidth(0, 280)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        root.addWidget(self.tree, 1)

        row = QHBoxLayout()
        btn_refresh = QPushButton("刷新")
        btn_open = QPushButton("打开文件夹")
        btn_clear_sel = QPushButton("清除所选")
        btn_clear_all = QPushButton("清除全部")
        btn_clear_all.setProperty("variant", "danger")
        btn_refresh.clicked.connect(self.refresh)
        btn_open.clicked.connect(self._open_folder)
        btn_clear_sel.clicked.connect(self._clear_selected)
        btn_clear_all.clicked.connect(self._clear_all)
        row.addWidget(btn_refresh)
        row.addWidget(btn_open)
        row.addStretch(1)
        row.addWidget(btn_clear_sel)
        row.addWidget(btn_clear_all)
        root.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        root.addWidget(buttons)

        self.refresh()

    def refresh(self) -> None:
        ensure_dirs()
        self.lbl_path.setText(f"路径：{EXPERIMENT_DIR.resolve()}")
        n_dirs, n_files, nbytes = _dir_stats(EXPERIMENT_DIR)
        self.lbl_stats.setText(
            f"共 {n_dirs} 个子目录 · {n_files} 个文件 · {_fmt_bytes(nbytes)}"
        )
        self.tree.clear()
        if not EXPERIMENT_DIR.exists():
            return
        for child in sorted(EXPERIMENT_DIR.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                item = QTreeWidgetItem(
                    [child.name, "", "文档缓存", _mtime(child)]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, str(child))
                for f in sorted(child.iterdir(), key=lambda p: p.name.lower()):
                    if not f.is_file():
                        continue
                    try:
                        sz = f.stat().st_size
                    except OSError:
                        sz = 0
                    kind = "计时" if f.name.startswith("timings_") else (
                        "公式 QA" if f.name.endswith(".formula_qa.json") else "文件"
                    )
                    sub = QTreeWidgetItem([f.name, _fmt_bytes(sz), kind, _mtime(f)])
                    sub.setData(0, Qt.ItemDataRole.UserRole, str(f))
                    item.addChild(sub)
                self.tree.addTopLevelItem(item)
            elif child.is_file():
                try:
                    sz = child.stat().st_size
                except OSError:
                    sz = 0
                item = QTreeWidgetItem([child.name, _fmt_bytes(sz), "文件", _mtime(child)])
                item.setData(0, Qt.ItemDataRole.UserRole, str(child))
                self.tree.addTopLevelItem(item)
        self.tree.expandToDepth(0)

    def _open_folder(self) -> None:
        ensure_dirs()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(EXPERIMENT_DIR.resolve())))

    def _paths_from_selection(self) -> list[Path]:
        paths: list[Path] = []
        seen: set[str] = set()
        for item in self.tree.selectedItems():
            raw = item.data(0, Qt.ItemDataRole.UserRole)
            if not raw:
                continue
            p = Path(str(raw))
            key = str(p.resolve()) if p.exists() else str(p)
            if key in seen:
                continue
            seen.add(key)
            paths.append(p)
        return paths

    def _clear_selected(self) -> None:
        paths = self._paths_from_selection()
        if not paths:
            QMessageBox.information(self, "诊断缓存", "请先选择要清除的项。")
            return
        n = len(paths)
        reply = QMessageBox.question(
            self,
            "清除所选",
            f"确定删除选中的 {n} 项？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        errors = 0
        for p in paths:
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                elif p.is_file():
                    p.unlink()
            except OSError:
                errors += 1
        self.refresh()
        if errors:
            QMessageBox.warning(self, "诊断缓存", f"有 {errors} 项删除失败。")

    def _clear_all(self) -> None:
        ensure_dirs()
        children = list(EXPERIMENT_DIR.iterdir()) if EXPERIMENT_DIR.exists() else []
        _, n_files, nbytes = _dir_stats(EXPERIMENT_DIR)
        if not children:
            QMessageBox.information(self, "诊断缓存", "缓存已为空。")
            return
        reply = QMessageBox.question(
            self,
            "清除全部",
            f"确定清空诊断缓存？\n"
            f"将删除 {EXPERIMENT_DIR.resolve()} 下全部内容"
            f"（约 {n_files} 个文件 · {_fmt_bytes(nbytes)}）。\n"
            f"「实验结果」将暂时无数据，需重新跑转换才会再生成。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            for child in children:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        except OSError as e:
            QMessageBox.warning(self, "诊断缓存", f"清除失败：{e}")
            self.refresh()
            return
        self.refresh()
        QMessageBox.information(self, "诊断缓存", "已清空。")
