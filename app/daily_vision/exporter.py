"""日常识图 Markdown 导出。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.daily_vision.figure_crop import crop_regions
from app.daily_vision.models import DailyVisionResult, FigureRegion
from app.daily_vision.prompts import DAILY_PROMPT_VERSION

IMAGE_MARKER_RE = re.compile(r"<!--\s*PDF2MD:IMAGE:([^>]+)\s*-->")


def parse_daily_response(text: str) -> DailyVisionResult:
    raw = (text or "").strip()
    if not raw:
        return DailyVisionResult()
    # 尝试 JSON envelope
    for candidate in (raw, _extract_json_block(raw)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("markdown") is not None:
            regions = []
            for r in data.get("regions") or []:
                if not isinstance(r, dict):
                    continue
                regions.append(
                    FigureRegion(
                        marker=str(r.get("marker") or ""),
                        source_image=int(r.get("source_image") or 1),
                        region_type=str(r.get("type") or "figure"),
                        bbox=[float(x) for x in (r.get("bbox") or [])[:4]],
                    )
                )
            return DailyVisionResult(
                markdown=str(data.get("markdown") or ""),
                regions=regions,
                raw_json=candidate,
            )
    return DailyVisionResult(markdown=raw, raw_json=raw)


def _extract_json_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return ""


def replace_image_markers(md: str, marker_to_path: dict[str, Path]) -> str:
    def _repl(match: re.Match) -> str:
        key = match.group(1).strip()
        path = marker_to_path.get(key)
        if path is None:
            return match.group(0)
        rel = path.as_posix()
        return f"![Figure]({rel})"

    return IMAGE_MARKER_RE.sub(_repl, md)


def export_archive(
    image_paths: list[Path],
    result: DailyVisionResult,
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = out_dir / "sources"
    sources.mkdir(exist_ok=True)
    for i, p in enumerate(image_paths, start=1):
        dest = sources / f"source_{i:04d}{p.suffix.lower() or '.png'}"
        dest.write_bytes(Path(p).read_bytes())

    images_dir = out_dir / "images"
    crops = crop_regions(image_paths, result.regions, images_dir)
    md_body = replace_image_markers(result.markdown, {k: v.relative_to(out_dir) for k, v in crops.items()})
    md_path = out_dir / "document.md"
    md_path.write_text(md_body, encoding="utf-8")

    meta_dir = out_dir / ".pdf2md"
    meta_dir.mkdir(exist_ok=True)
    (meta_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "prompt_version": DAILY_PROMPT_VERSION,
                "source_count": len(image_paths),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return md_path
