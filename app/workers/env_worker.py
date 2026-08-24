"""环境探测（在 worker 线程跑，避免卡住启动）。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.utils.paths import PYTHON_EXE


class EnvProbeWorker(QThread):
    finished_info = Signal(dict)

    def run(self) -> None:
        info = {
            "python": "?",
            "docling": "不可用",
            "mineru": "不可用",
            "torch": "不可用",
            "cuda": "不可用",
            "gpu": "未知",
            "vram": "未知",
            "deepseek": "不可用",
            "deepseek_state": "Unavailable",
        }
        try:
            import sys

            info["python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        except Exception:
            pass

        try:
            import docling

            info["docling"] = getattr(docling, "__version__", "已安装")
        except Exception as e:
            info["docling"] = f"不可用 ({e})"

        try:
            import mineru

            ver = getattr(mineru, "__version__", None)
            if ver is None:
                try:
                    from mineru.version import __version__ as ver  # type: ignore
                except Exception:
                    ver = "已安装"
            info["mineru"] = str(ver)
        except Exception as e:
            info["mineru"] = f"不可用 ({e})"

        try:
            import torch

            info["torch"] = torch.__version__
            if torch.cuda.is_available():
                info["cuda"] = f"Available ({torch.version.cuda})"
                info["gpu"] = torch.cuda.get_device_name(0)
                try:
                    props = torch.cuda.get_device_properties(0)
                    info["vram"] = f"{props.total_memory / (1024**3):.0f} GB"
                except Exception:
                    info["vram"] = "?"
            else:
                info["cuda"] = "不可用 (CPU torch)"
                # 仍尝试 nvidia-smi 显示物理 GPU
                gpu, vram = _nvidia_smi()
                if gpu:
                    info["gpu"] = gpu
                if vram:
                    info["vram"] = vram
        except Exception as e:
            info["torch"] = f"不可用 ({e})"
            gpu, vram = _nvidia_smi()
            if gpu:
                info["gpu"] = gpu
            if vram:
                info["vram"] = vram

        _probe_deepseek(info)
        self.finished_info.emit(info)


def _probe_deepseek(info: dict) -> None:
    """只读 TCP health，不 import 客户端、不 spawn Worker。"""
    import json
    import socket

    from app.utils.paths import APP_ROOT

    host, port = "127.0.0.1", 18765
    meta_path = APP_ROOT / ".cache" / "deepseek_worker.json"
    try:
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            host = str(meta.get("host") or host)
            port = int(meta.get("port") or port)
        req = (json.dumps({"id": 1, "method": "health", "params": {}}) + "\n").encode("utf-8")
        with socket.create_connection((host, port), timeout=0.4) as sock:
            sock.settimeout(1.2)
            sock.sendall(req)
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
        if not buf:
            info["deepseek_state"] = "Cold"
            info["deepseek"] = "daemon 无响应（不自动拉起）"
            return
        h = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
        if h.get("ok") or h.get("model_loaded"):
            loaded = bool(h.get("model_loaded"))
            info["deepseek_state"] = "Warm" if loaded else "Ready"
            age = h.get("model_age_seconds")
            extra = f" · model {age:.0f}s" if loaded and isinstance(age, (int, float)) else ""
            info["deepseek"] = f"本地 worker{extra}"
            return
        info["deepseek_state"] = "Cold"
        info["deepseek"] = str(h.get("error") or h.get("state") or "未就绪")
    except OSError:
        info["deepseek_state"] = "Cold"
        info["deepseek"] = "daemon 未在监听（不自动拉起）"
    except Exception as e:  # noqa: BLE001
        info["deepseek_state"] = "Unavailable"
        info["deepseek"] = f"不可用 ({e})"


def _nvidia_smi() -> tuple[str, str]:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        ).strip()
        if not out:
            return "", ""
        parts = [p.strip() for p in out.split(",")]
        name = parts[0] if parts else ""
        mem = parts[1] if len(parts) > 1 else ""
        return name, mem
    except Exception:
        return "", ""


def probe_sync() -> dict:
    w = EnvProbeWorker()
    # 同步简版
    result: dict = {}

    def _set(d: dict) -> None:
        result.update(d)

    # 直接调用 run 逻辑
    w.finished_info.connect(_set)
    w.run()
    return result
