"""Page / Region OCR 结果缓存（Benchmark 调 Validator 时禁止重跑模型）。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.ocr import DocumentOCRResult, OCRMode


def file_sha1(path: str | Path, *, max_bytes: int = 8_000_000) -> str:
    p = Path(path)
    h = hashlib.sha1()
    with p.open("rb") as f:
        remaining = max_bytes
        while remaining > 0:
            chunk = f.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    h.update(str(p.stat().st_size).encode())
    return h.hexdigest()[:16]


def config_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def normalize_bbox(bbox: tuple[float, float, float, float], *, ndigits: int = 1) -> tuple[float, float, float, float]:
    return tuple(round(float(x), ndigits) for x in bbox)  # type: ignore[return-value]


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class PageOCRCache:
    """key = (pdf_hash, page, recognizer, config_hash)。"""

    def __init__(self) -> None:
        self._store: dict[tuple[Any, ...], DocumentOCRResult] = {}
        self.stats = CacheStats()

    def make_key(
        self,
        *,
        pdf_hash: str,
        page: int,
        recognizer: str,
        config: dict[str, Any],
    ) -> tuple[Any, ...]:
        return (pdf_hash, int(page), recognizer, config_hash(config))

    def get(self, key: tuple[Any, ...]) -> DocumentOCRResult | None:
        hit = self._store.get(key)
        if hit is None:
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return hit

    def put(self, key: tuple[Any, ...], value: DocumentOCRResult) -> None:
        self._store[key] = value


class RegionOCRCache:
    """key = pdf_hash + page + normalized_bbox + recognizer + scale + prompt。"""

    def __init__(self) -> None:
        self._store: dict[tuple[Any, ...], DocumentOCRResult] = {}
        self.stats = CacheStats()

    def make_key(
        self,
        *,
        pdf_hash: str,
        page: int,
        bbox: tuple[float, float, float, float],
        recognizer: str,
        render_scale: float,
        prompt: str,
        mode: OCRMode | str = OCRMode.REGION,
    ) -> tuple[Any, ...]:
        mode_s = mode.value if isinstance(mode, OCRMode) else str(mode)
        return (
            pdf_hash,
            int(page),
            normalize_bbox(bbox),
            recognizer,
            round(float(render_scale), 2),
            hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10],
            mode_s,
        )

    def get(self, key: tuple[Any, ...]) -> DocumentOCRResult | None:
        hit = self._store.get(key)
        if hit is None:
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return hit

    def put(self, key: tuple[Any, ...], value: DocumentOCRResult) -> None:
        self._store[key] = value
