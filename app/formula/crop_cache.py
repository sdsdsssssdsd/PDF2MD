# -*- coding: utf-8 -*-
"""k5：固化 formula crop。所有模型必须吃同一张图。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.utils.paths import (
    EXPERIMENT_DIR,
    K5_CROPS_DIR,
    OULAD_PDF_DIR,
    TESTSET_DIR,
    ensure_dirs,
)

CROP_SCALE = 2.0
CROP_PAD_X = 0.10
CROP_PAD_Y = 0.12


@dataclass
class CropSlot:
    id: str
    pdf_id: str
    pdf_path: str
    page: int
    page_index: int
    bbox_pdf: list[float]
    crop_path: str = ""
    equation_number: str = ""
    scale: float = CROP_SCALE
    width: int = 0
    height: int = 0
    sha256: str = ""
    crop_ok: bool = False
    language: str = ""
    source: str = "formula_qa"
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def language_from_stem(stem: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", stem or ""):
        return "zh"
    s = (stem or "").lower()
    if s.startswith("en_") or s.startswith("o-") or s.startswith("zh_"):
        return "en" if not s.startswith("zh_") else "zh"
    return "en"


def latest_timings_pdf(exp_dir: Path) -> str | None:
    files = sorted(exp_dir.glob("timings_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pdf = data.get("pdf")
        if pdf:
            return str(pdf)
    return None


def resolve_pdf(stem: str, *, hinted: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if hinted:
        candidates.append(Path(hinted))
    candidates.append(TESTSET_DIR / f"{stem}.pdf")
    candidates.append(OULAD_PDF_DIR / f"{stem}.pdf")
    for path in candidates:
        if path.is_file():
            return path
    return None


def page_index_candidates(page: int, n_pages: int) -> list[int]:
    out: list[int] = []
    for idx in (int(page), int(page) - 1):
        if 0 <= idx < n_pages and idx not in out:
            out.append(idx)
    return out


def _slots_from_qa(stem: str, qa: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(raw: dict[str, Any], source: str) -> None:
        bbox = raw.get("bbox") or raw.get("bbox_pdf")
        if not isinstance(bbox, list) or len(bbox) < 4:
            return
        page = int(raw.get("page") or 0)
        eq = str(raw.get("equation_number") or raw.get("eq_number") or "")
        cid = str(raw.get("candidate_id") or "") or f"p{page}_{eq or 'slot'}{len(rows)}"
        key = cid if cid not in seen else f"{cid}_{len(rows)}"
        seen.add(key)
        rows.append(
            {
                "id": f"{stem}_{key}",
                "page": page,
                "bbox": [float(x) for x in bbox[:4]],
                "equation_number": eq,
                "candidate_id": cid,
                "source": source,
                "parser_latex": str(raw.get("raw") or raw.get("text") or raw.get("original") or ""),
            }
        )

    for fail in qa.get("formula_failures") or []:
        if isinstance(fail, dict):
            add(fail, "formula_failures")
    for detail in qa.get("details") or []:
        if isinstance(detail, dict) and detail.get("bbox"):
            add(detail, "details")
    return rows


def collect_slots_from_experiment(
    experiment_dir: Path | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    root = experiment_dir or EXPERIMENT_DIR
    out: list[tuple[Path, dict[str, Any]]] = []
    if not root.is_dir():
        return out
    for qa_path in sorted(root.glob("*/*.formula_qa.json")):
        try:
            qa = json.loads(qa_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stem = qa_path.parent.name
        hinted = latest_timings_pdf(qa_path.parent)
        pdf = resolve_pdf(stem, hinted=hinted)
        if pdf is None:
            continue
        for slot in _slots_from_qa(stem, qa):
            slot["pdf_id"] = stem
            slot["pdf_path"] = str(pdf)
            slot["language"] = language_from_stem(stem)
            out.append((pdf, slot))
    return out


def render_formula_crop(
    pdf_path: Path,
    page: int,
    bbox: list[float] | tuple[float, float, float, float],
    *,
    scale: float = CROP_SCALE,
    pad_x: float = CROP_PAD_X,
    pad_y: float = CROP_PAD_Y,
) -> tuple[Any, int]:
    import pymupdf

    from app.formula.preprocess import to_pil_image

    doc = pymupdf.open(str(pdf_path))
    try:
        n = len(doc)
        last_err: Exception | None = None
        for idx in page_index_candidates(page, n):
            try:
                page_obj = doc[idx]
                x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                w, h = max(1.0, x1 - x0), max(1.0, y1 - y0)
                x0 = max(0.0, x0 - w * pad_x)
                x1 = min(float(page_obj.rect.width), x1 + w * pad_x)
                y0 = max(0.0, y0 - h * pad_y)
                y1 = min(float(page_obj.rect.height), y1 + h * pad_y)
                if x1 <= x0 or y1 <= y0:
                    continue
                clip = pymupdf.Rect(x0, y0, x1, y1)
                s = max(1.0, min(float(scale), 4.0))
                pix = page_obj.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=clip, alpha=False)
                im = to_pil_image(pix) or pix
                if getattr(im, "size", (0, 0))[0] < 8:
                    continue
                return im, idx
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(f"crop_failed:{last_err}")
    finally:
        doc.close()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def write_crop_png(image: Any, dest: Path) -> tuple[int, int, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(dest, format="PNG")
    data = dest.read_bytes()
    w, h = image.size
    return int(w), int(h), _sha256_bytes(data)


def build_crop_cache(
    *,
    experiment_dir: Path | None = None,
    out_dir: Path | None = None,
    scale: float = CROP_SCALE,
    limit: int = 0,
) -> dict[str, Any]:
    ensure_dirs()
    dest_root = out_dir or K5_CROPS_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    slots = collect_slots_from_experiment(experiment_dir)
    if limit > 0:
        slots = slots[:limit]
    records: list[CropSlot] = []
    for pdf, raw in slots:
        rec = CropSlot(
            id=str(raw["id"]),
            pdf_id=str(raw["pdf_id"]),
            pdf_path=str(pdf),
            page=int(raw["page"]),
            page_index=-1,
            bbox_pdf=list(raw["bbox"]),
            equation_number=str(raw.get("equation_number") or ""),
            scale=scale,
            language=str(raw.get("language") or ""),
            source=str(raw.get("source") or ""),
            extra={
                "candidate_id": raw.get("candidate_id"),
                "parser_latex": (raw.get("parser_latex") or "")[:400],
            },
        )
        rel = Path(rec.pdf_id) / f"{rec.id}.png"
        rec.crop_path = str(rel).replace("\\", "/")
        try:
            image, idx = render_formula_crop(pdf, rec.page, rec.bbox_pdf, scale=scale)
            rec.page_index = idx
            rec.width, rec.height, rec.sha256 = write_crop_png(image, dest_root / rel)
            rec.crop_ok = True
        except Exception as e:
            rec.error = f"{type(e).__name__}:{e}"
            rec.crop_ok = False
        records.append(rec)

    manifest = {
        "scale": scale,
        "pad_x": CROP_PAD_X,
        "pad_y": CROP_PAD_Y,
        "n": len(records),
        "ok": sum(1 for r in records if r.crop_ok),
        "failed": sum(1 for r in records if not r.crop_ok),
        "crops": [r.to_dict() for r in records],
    }
    (dest_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def load_crop_manifest(path: Path | None = None) -> dict[str, Any]:
    p = path or (K5_CROPS_DIR / "manifest.json")
    if not p.is_file():
        return {"crops": []}
    return json.loads(p.read_text(encoding="utf-8"))
