"""读写系统剪贴板（与 DeepSeek 网页 Ctrl+C / 本地 Ctrl+V 一致）。

自动化路径应优先用 clipboard_interceptor 隔离模式，避免污染用户剪贴板。
仅在隔离失败回退时读写 OS，并用 snapshot_restore 包一层。
"""
from __future__ import annotations

import subprocess
import sys
from contextlib import contextmanager
from typing import Iterator


def read_system_clipboard_rich() -> tuple[str, str]:
    """返回 (plain_text, html_fragment_raw)。"""
    from app.vision_transcribe.browser.clipboard_html import read_system_clipboard_html

    plain = read_system_clipboard_text()
    html = read_system_clipboard_html()
    return plain, html


def read_system_clipboard_text() -> str:
    """读 OS 剪贴板文本（优先 Win32 Unicode，与 Ctrl+V 一致）。"""
    if sys.platform == "win32":
        try:
            import ctypes

            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(None):
                try:
                    handle = user32.GetClipboardData(CF_UNICODETEXT)
                    if handle:
                        ptr = kernel32.GlobalLock(handle)
                        if ptr:
                            try:
                                text = ctypes.wstring_at(ptr) or ""
                                if text.strip():
                                    return text
                            finally:
                                kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
            )
            if r.returncode == 0 and (r.stdout or "").strip():
                return r.stdout
        except Exception:
            pass
    try:
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is not None:
            cb = QGuiApplication.clipboard()
            if cb is not None:
                text = cb.text() or ""
                if text.strip():
                    return text
    except Exception:
        pass
    return ""


def write_system_clipboard_text(text: str) -> bool:
    """写入系统剪贴板（半自动粘贴模式可用）。"""
    payload = str(text or "")
    if sys.platform == "win32":
        try:
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
                ],
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=8,
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass
    try:
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is not None:
            cb = QGuiApplication.clipboard()
            if cb is not None:
                cb.setText(payload)
                return True
    except Exception:
        pass
    return False


@contextmanager
def snapshot_restore_system_clipboard() -> Iterator[None]:
    """临时占用系统剪贴板后恢复用户原有内容（回退路径用）。"""
    saved_plain = ""
    try:
        saved_plain = read_system_clipboard_text()
    except Exception:
        saved_plain = ""
    try:
        yield
    finally:
        if not saved_plain:
            return
        try:
            write_system_clipboard_text(saved_plain)
        except Exception:
            pass
