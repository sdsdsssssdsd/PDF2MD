"""日常识图工作区：可一次性选一批，也可以「陆续加图」（QQ 一张一张复制的场景）。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.drop_widget import DropWidget
from app.ui.widgets.progress_row import ProgressRow

_IMAGE_EXTS = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.bmp")
# Ctrl+V 粘贴的临时图落在这里（归档目录名要能认出「这不是用户给的原始文件」）
PASTE_DIR = Path(__file__).resolve().parents[2] / "logs" / "daily_paste"


def is_pasted_image(path: Path) -> bool:
    try:
        return Path(path).resolve().parent == PASTE_DIR.resolve()
    except OSError:
        return False


def _key(path: Path) -> str:
    try:
        return str(Path(path).resolve())
    except OSError:
        return str(path)


class DailyVisionWorkspace(QWidget):
    images_added = Signal(list)
    request_recognize = Signal(list, bool)  # paths, archive
    request_finish = Signal()  # 结束会话：识别完队列里已有的就收工
    session_cleared = Signal()
    request_save_markdown = Signal(str)
    request_open_output = Signal()
    request_cancel = Signal()
    stream_mode_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image_paths: list[Path] = []  # 本次会话收到的全部图片（顺序）
        self._done: list[Path] = []  # 已识别
        self._failed: list[Path] = []  # 识别失败（等用户重试）
        self._busy = False
        self._paste_seq = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 8, 0)

        # 顶部进度行：确定进度条（0–100，按真实已处理张数/已接收字数推进）+ 阶段文本
        self.progress_row = ProgressRow()
        lay.addWidget(self.progress_row)

        self.drop = DropWidget()
        self.drop.set_mode("images")
        self.drop.files_dropped.connect(self._on_drop)
        lay.addWidget(self.drop)

        queue_row = QHBoxLayout()
        self.chk_stream = QCheckBox("连续收图")
        self.chk_stream.setToolTip(
            "陆续加图：拖入 / Ctrl+V 粘贴的图片会追加到队列，识别中也能继续加，"
            "识别完一批自动接着下一批，结果拼成同一篇 Markdown；\n"
            "关闭＝一次性模式：每次选择/粘贴的图片单独识别一次，结果整体替换。"
        )
        self.chk_stream.toggled.connect(self._on_stream_toggled)
        queue_row.addWidget(self.chk_stream)
        self.lbl_images = QLabel("尚未添加图片 · 支持 Ctrl+V 粘贴或拖入")
        self.lbl_images.setProperty("role", "muted")
        queue_row.addWidget(self.lbl_images, 1)
        queue_row.addStretch(0)
        lay.addLayout(queue_row)

        self.result = QPlainTextEdit()
        self.result.setPlaceholderText("识别结果将显示在这里，可直接编辑后复制…")
        self.result.setMinimumHeight(200)
        lay.addWidget(self.result, 1)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("添加图片")
        self.btn_add.setToolTip("选择一批图片追加到队列（已添加过的不会重复）")
        self.btn_add.clicked.connect(self._pick_files)
        self.btn_copy = QPushButton("复制 Markdown")
        self.btn_copy.clicked.connect(self._copy_md)
        self.btn_save_md = QPushButton("保存 Markdown")
        self.btn_save_md.clicked.connect(self._save_md)
        self.btn_save = QPushButton("图文归档")
        self.btn_save.setToolTip("保存 Markdown + 裁图到输出目录（连续收图时归档整个会话）")
        self.btn_save.clicked.connect(self._archive)
        self.btn_open_out = QPushButton("打开输出目录")
        self.btn_open_out.clicked.connect(self.request_open_output.emit)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setToolTip("清空队列与结果，开始新的一次会话（识别中不可用）")
        self.btn_clear.clicked.connect(self.clear)
        self.btn_retry = QPushButton("重新识别")
        self.btn_retry.setToolTip("重新识别队列里未完成（含失败）的图片")
        self.btn_retry.clicked.connect(self._retry)
        self.btn_finish = QPushButton("结束会话")
        self.btn_finish.setToolTip("识别完队列里已有的图片就收工（不再等待新图片）")
        self.btn_finish.clicked.connect(self.request_finish.emit)
        self.btn_finish.setVisible(False)
        self.btn_cancel = QPushButton("取消识别")
        self.btn_cancel.setProperty("variant", "danger")
        self.btn_cancel.setToolTip("立即停止（Esc 同效），已识别的部分保留")
        self.btn_cancel.clicked.connect(self.request_cancel.emit)
        self.btn_cancel.setVisible(False)
        for b in (
            self.btn_add,
            self.btn_copy,
            self.btn_save_md,
            self.btn_save,
            self.btn_open_out,
            self.btn_retry,
            self.btn_finish,
            self.btn_cancel,
            self.btn_clear,
        ):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("role", "subtle")
        lay.addWidget(self.lbl_status)

        self._refresh_queue_label()

    # —— 队列 ——
    def _on_drop(self, paths: list[str]) -> None:
        if not paths:
            self._pick_files()
            return
        self.add_image_paths([Path(p) for p in paths if p])

    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片（可多选，也可以一张一张陆续添加）",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)",
        )
        if files:
            self.add_image_paths([Path(p) for p in files])

    def add_image_paths(self, paths: list[Path]) -> list[Path]:
        """追加图片（按绝对路径去重）并请求识别；返回本次新增的图片。

        一次性模式下本次选择就是要识别的全部内容，所以先清空队列；
        连续收图模式下只追加，识别中也能继续加。
        """
        if not self.stream_mode():
            self._reset_queue()
        existing = {_key(p) for p in self._image_paths}
        added: list[Path] = []
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                for ext in _IMAGE_EXTS:
                    for sub in (path.glob(ext), path.glob(ext.upper())):
                        for item in sub:
                            if item.is_file() and _key(item) not in existing:
                                existing.add(_key(item))
                                self._image_paths.append(item)
                                added.append(item)
                continue
            if not path.is_file():
                continue
            key = _key(path)
            if key in existing:
                continue
            existing.add(key)
            self._image_paths.append(path)
            added.append(path)
        if not added:
            self._refresh_queue_label()
            return []
        self._refresh_queue_label()
        self.images_added.emit([str(p) for p in added])
        if not self.stream_mode():
            # 一次性模式：本次选择立刻识别；连续收图交给 MainWindow 防抖后统一派发，
            # 否则「粘贴一张」和「防抖批量」会各派发一次，同一张图被识别两遍。
            self.request_recognize.emit(list(self._image_paths), False)
        return added

    def paste_from_clipboard(self) -> bool:
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None or not mime.hasImage():
            return False
        from PySide6.QtGui import QImage

        image = mime.imageData()
        if not isinstance(image, QImage) or image.isNull():
            img = QGuiApplication.clipboard().image()
            if img.isNull():
                return False
            image = img
        temp_dir = PASTE_DIR
        temp_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 同一秒连点两次 Ctrl+V 也必须落成两个文件，否则第二张会覆盖第一张
        self._paste_seq += 1
        path = temp_dir / f"paste_{stamp}_{self._paste_seq:03d}.png"
        while path.exists():
            self._paste_seq += 1
            path = temp_dir / f"paste_{stamp}_{self._paste_seq:03d}.png"
        if not image.save(str(path), "PNG"):
            return False
        self.add_image_paths([path])
        return True

    # —— 状态 ——
    def mark_done(self, paths: list[Path]) -> None:
        keys = {_key(p) for p in self._done}
        for path in paths:
            key = _key(path)
            if key in keys:
                continue
            keys.add(key)
            self._done.append(Path(path))
        self._failed = [p for p in self._failed if _key(p) not in keys]
        self._refresh_queue_label()

    def mark_failed(self, paths: list[Path]) -> None:
        keys = {_key(p) for p in self._failed}
        for path in paths:
            if _key(path) not in keys:
                keys.add(_key(path))
                self._failed.append(Path(path))
        self._refresh_queue_label()

    def clear_failed(self) -> None:
        self._failed.clear()
        self._refresh_queue_label()

    def pending_paths(self) -> list[Path]:
        done = {_key(p) for p in self._done}
        return [p for p in self._image_paths if _key(p) not in done]

    def failed_paths(self) -> list[Path]:
        return list(self._failed)

    def queue_counts(self) -> tuple[int, int, int]:
        """(已识别, 待识别, 失败)。"""
        done = {_key(p) for p in self._done}
        pending = [p for p in self._image_paths if _key(p) not in done]
        return len(self._done), len(pending), len(self._failed)

    def _refresh_queue_label(self) -> None:
        total = len(self._image_paths)
        if not total:
            self.lbl_images.setText("尚未添加图片 · 支持 Ctrl+V 粘贴或拖入")
            return
        done, pending, failed = self.queue_counts()
        parts = [f"已收 {total} 张", f"已识别 {done} 张", f"队列 {pending} 张"]
        if failed:
            parts.append(f"失败 {failed} 张")
        self.lbl_images.setText(" · ".join(parts))

    def stream_mode(self) -> bool:
        return self.chk_stream.isChecked()

    def set_stream_mode(self, enabled: bool) -> None:
        if self.chk_stream.isChecked() != bool(enabled):
            self.chk_stream.setChecked(bool(enabled))
        else:
            self._sync_stream_ui()

    def _on_stream_toggled(self, enabled: bool) -> None:
        self._sync_stream_ui()
        self.stream_mode_changed.emit(bool(enabled))

    def _sync_stream_ui(self) -> None:
        streaming = self.chk_stream.isChecked()
        if self._busy:
            self.drop.setEnabled(streaming)
        self.btn_finish.setVisible(bool(self._busy) and streaming)

    def set_progress(self, percent: int | None, text: str = "") -> None:
        """percent 为真实完成度 0–100（None = 数值不变，只更新阶段文本）。"""
        self.progress_row.set_progress(percent, text)

    def set_status(self, text: str) -> None:
        """运行中显示在进度行；空闲时显示在底部状态栏。"""
        if self.progress_row.is_busy():
            self.progress_row.set_status(text)
        else:
            self.lbl_status.setText(text or "")

    def set_busy(self, busy: bool) -> None:
        """busy：识别中。连续收图时拖入/粘贴/添加仍然可用（这正是「陆续加图」）。"""
        self._busy = bool(busy)
        streaming = self.chk_stream.isChecked()
        allow_more = (not busy) or streaming
        self.drop.setEnabled(allow_more)
        self.btn_add.setEnabled(allow_more)
        self.btn_retry.setEnabled(not busy)
        self.btn_save.setEnabled(not busy)
        self.btn_clear.setEnabled(not busy)
        self.btn_cancel.setVisible(bool(busy))
        self.btn_finish.setVisible(bool(busy) and streaming)
        self.progress_row.set_busy(busy)

    def is_busy(self) -> bool:
        return self._busy

    def clear(self) -> None:
        self._reset_queue()
        self.result.clear()
        self.lbl_status.clear()
        self.session_cleared.emit()

    def _reset_queue(self) -> None:
        self._image_paths.clear()
        self._done.clear()
        self._failed.clear()
        self._refresh_queue_label()

    def image_paths(self) -> list[Path]:
        return list(self._image_paths)

    # —— 按钮 ——
    def _retry(self) -> None:
        self.clear_failed()
        pending = self.pending_paths()
        if pending:
            self.request_recognize.emit(pending, False)

    def _archive(self) -> None:
        self.clear_failed()
        pending = self.pending_paths()
        self.request_recognize.emit(pending or list(self._image_paths), True)

    def _save_md(self) -> None:
        text = self.result.toPlainText().strip()
        if not text:
            self.set_status("没有可保存的内容")
            return
        self.request_save_markdown.emit(text)

    def _copy_md(self) -> None:
        text = self.result.toPlainText().strip()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.set_status("已复制到剪贴板")

    def set_result(self, markdown: str) -> None:
        self.result.setPlainText(markdown or "")
