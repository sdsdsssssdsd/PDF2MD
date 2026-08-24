"""半自动 Clipboard Bridge（默认 / Playwright 失败回退）。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.vision_transcribe.browser.base import AdapterResult, VisionWebAdapter


class ManualClipboardAdapter(VisionWebAdapter):
    """不驱动浏览器：把 Prompt 放入剪贴板并打开 bookfigures，由用户粘贴结果。"""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def prepare_manual_batch(
        self,
        images: list[Path],
        prompt: str,
        *,
        bookfigures_dir: Path | None = None,
    ) -> str:
        self._copy_text(prompt)
        folder = bookfigures_dir
        if folder is None and images:
            folder = images[0].parent
        if folder and folder.exists():
            self._open_folder(folder)
        names = ", ".join(p.name for p in images[:3])
        if len(images) > 3:
            names += f" … 共 {len(images)} 张"
        return (
            f"已复制 Prompt 到剪贴板，并打开图片目录。\n"
            f"1. 在 DeepSeek 首页点最右侧的「识图模式」\n"
            f"   （快速模式 | 专家模式 | 识图模式 ← 点这个）\n"
            f"2. 将以下页面拖入或上传：{names}\n"
            f"3. 粘贴 Prompt → 发送 → 复制完整回答\n"
            f"4. 回到本程序点「从剪贴板导入」"
        )

    def submit_batch(self, images: list[Path], prompt: str) -> AdapterResult:
        hint = self.prepare_manual_batch(images, prompt)
        return AdapterResult(markdown="", needs_user=True, message=hint)

    @staticmethod
    def read_clipboard() -> str:
        from app.vision_transcribe.browser.system_clipboard import read_system_clipboard_text

        return read_system_clipboard_text()

    @staticmethod
    def _copy_text(text: str) -> None:
        try:
            from PySide6.QtGui import QGuiApplication

            cb = QGuiApplication.clipboard()
            if cb is not None:
                cb.setText(text)
                return
        except Exception:
            pass
        if sys.platform == "win32":
            # PowerShell Set-Clipboard
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value @'\n" + text.replace("'", "''") + "\n'@"],
                    check=False,
                    capture_output=True,
                )
            except Exception:
                pass

    @staticmethod
    def _open_folder(folder: Path) -> None:
        folder = Path(folder)
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(folder)], check=False)
            else:
                subprocess.run(["xdg-open", str(folder)], check=False)
        except Exception:
            pass
