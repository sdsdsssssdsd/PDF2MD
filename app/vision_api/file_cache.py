"""PDF Vision API：Files API 上传缓存（按 sha256 复用 file_id，支持断点续跑）。"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_path(output_dir: Path | None) -> Path | None:
    if output_dir is None:
        return None
    return Path(output_dir) / ".vision" / "api_files.json"


def load_entries(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_entries(path: Path | None, entries: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def lookup(path: Path, *, cache_file: Path | None) -> dict[str, Any] | None:
    digest = sha256_file(path)
    entries = load_entries(cache_file)
    row = entries.get(digest)
    if not isinstance(row, dict):
        return None
    expires = float(row.get("expires_at") or 0)
    if expires and expires < time.time():
        return None
    file_id = str(row.get("file_id") or "")
    if not file_id:
        return None
    return {"file_id": file_id, "sha256": digest, "expires_at": expires}


def invalidate_paths(paths: list[Path], *, cache_file: Path | None) -> None:
    if cache_file is None:
        return
    entries = load_entries(cache_file)
    changed = False
    for p in paths:
        try:
            digest = sha256_file(Path(p))
        except OSError:
            continue
        if digest in entries:
            del entries[digest]
            changed = True
    if changed:
        save_entries(cache_file, entries)


def store(
    path: Path,
    *,
    cache_file: Path | None,
    file_id: str,
    ttl_hours: int = 24,
) -> None:
    if cache_file is None:
        return
    digest = sha256_file(path)
    entries = load_entries(cache_file)
    entries[digest] = {
        "file_id": file_id,
        "path": str(path.name),
        "sha256": digest,
        "expires_at": time.time() + max(3600, ttl_hours * 3600),
        "uploaded_at": int(time.time()),
    }
    save_entries(cache_file, entries)
