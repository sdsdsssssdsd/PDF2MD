"""应用日志：写文件 + 可选 Qt 信号转发。"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from .paths import LOGS_DIR, ensure_dirs

_listeners: list[Callable[[str], None]] = []


def add_listener(cb: Callable[[str], None]) -> None:
    if cb not in _listeners:
        _listeners.append(cb)


def remove_listener(cb: Callable[[str], None]) -> None:
    if cb in _listeners:
        _listeners.remove(cb)


def _notify(line: str) -> None:
    for cb in list(_listeners):
        try:
            cb(line)
        except Exception:
            pass


def setup_logging() -> logging.Logger:
    ensure_dirs()
    logger = logging.getLogger("pdf2md")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")

    day = datetime.now().strftime("%Y%m%d")
    fh = logging.FileHandler(LOGS_DIR / f"app_{day}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    class _QtHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            _notify(self.format(record))

    qh = _QtHandler()
    qh.setFormatter(fmt)
    logger.addHandler(qh)
    return logger


def get_logger() -> logging.Logger:
    return setup_logging()


def write_task_log(folder: Path, text: str, *, run_id: str | None = None) -> Path:
    """写入转换日志。默认追加到 conversion.log；若给 run_id 则写独立文件避免覆盖。"""
    folder.mkdir(parents=True, exist_ok=True)
    if run_id:
        path = folder / f"conversion_{run_id}.log"
    else:
        path = folder / "conversion.log"
    with path.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")
    return path


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

