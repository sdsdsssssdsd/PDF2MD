"""读取剪贴板 HTML Format（DeepSeek 复制按钮常写入 Markdown 源或渲染 HTML）。"""
from __future__ import annotations

import subprocess
import sys


def read_system_clipboard_html() -> str:
    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            fmt = user32.RegisterClipboardFormatW("HTML Format")
            if user32.OpenClipboard(None):
                try:
                    handle = user32.GetClipboardData(fmt)
                    if handle:
                        ptr = kernel32.GlobalLock(handle)
                        if ptr:
                            try:
                                size = kernel32.GlobalSize(handle)
                                raw = ctypes.string_at(ptr, size)
                                for enc in ("utf-8", "mbcs", "latin-1"):
                                    try:
                                        text = raw.decode(enc)
                                        if "StartHTML" in text or "<" in text:
                                            return text
                                    except Exception:
                                        continue
                            finally:
                                kernel32.GlobalUnlock(handle)
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass
        try:
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.Clipboard]::GetData('HTML Format')"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
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
    return ""
