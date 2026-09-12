"""文件导入、编码快照与旁路原子写回。"""
from __future__ import annotations

import os
import json
from pathlib import Path

from app.format_repair.models import FileSnapshot

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}


def detect_snapshot(text: str) -> tuple[str, str, str]:
    if text.startswith("\ufeff"):
        bom = "utf-8-sig"
        text = text[1:]
    else:
        bom = ""
    newline = "\r\n" if "\r\n" in text else "\n"
    return bom, newline, text


def read_text_file(path: Path) -> tuple[str, FileSnapshot]:
    raw = Path(path).read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = ""
    encoding = "utf-8"
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    _bom, newline, text = detect_snapshot(text)
    bom = "utf-8-sig" if has_bom else _bom
    stat = Path(path).stat()
    snapshot = FileSnapshot(
        path=Path(path),
        encoding=encoding,
        newline=newline,
        bom=bom,
        mtime_ns=stat.st_mtime_ns,
    )
    return text, snapshot


def repaired_sibling_path(source: Path) -> Path:
    source = Path(source)
    candidate = source.with_name(f"{source.stem}_修复版{source.suffix}")
    index = 2
    while candidate.exists():
        candidate = source.with_name(f"{source.stem}_修复版_{index}{source.suffix}")
        index += 1
    return candidate


def atomic_write_text(path: Path, text: str, snapshot: FileSnapshot) -> Path:
    path = Path(path)
    newline_text = text.replace("\n", snapshot.newline)
    if snapshot.bom == "utf-8-sig":
        data = ("\ufeff" + newline_text).encode("utf-8")
    elif snapshot.encoding == "gb18030":
        data = newline_text.encode("gb18030", errors="replace")
    else:
        data = newline_text.encode("utf-8")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    with open(tmp, "r+b") as f:
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def save_repaired_sibling(source: Path, text: str, snapshot: FileSnapshot) -> Path:
    out = repaired_sibling_path(Path(source))
    return atomic_write_text(out, text, snapshot)


def save_report_sibling(source: Path, report: dict) -> Path:
    source = Path(source)
    candidate = source.with_name(f"{source.stem}_修复报告.json")
    index = 2
    while candidate.exists():
        candidate = source.with_name(f"{source.stem}_修复报告_{index}.json")
        index += 1
    candidate.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return candidate
