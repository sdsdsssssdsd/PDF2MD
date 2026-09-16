"""日常识图 Markdown 导出。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.daily_vision.figure_crop import crop_regions
from app.daily_vision.models import DailyVisionResult, FigureRegion
from app.daily_vision.prompts import DAILY_PROMPT_VERSION
from app.deepseek_api.config import DEFAULT_MODEL, DEFAULT_MODEL_FAMILY
from app.deepseek_api.profiles import DAILY_VISION

IMAGE_MARKER_RE = re.compile(r"<!--\s*PDF2MD:IMAGE:([^>]+)\s*-->")


def parse_daily_response(text: str | dict) -> DailyVisionResult:
    if isinstance(text, dict):
        data = text
        raw = json.dumps(text, ensure_ascii=False)
        if data.get("markdown") is not None:
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
                raw_json=raw,
            )
        return DailyVisionResult()
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
                "provider": "deepseek",
                "model": DEFAULT_MODEL,
                "model_family": DEFAULT_MODEL_FAMILY,
                "task_profile": DAILY_VISION.name,
                "thinking": "disabled",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        from app.core.domain.document import document_from_markdown
        from app.core.domain.quality import quality_from_markdown
        from app.core.pipeline.checkpoint import write_run_sidecar

        ir = document_from_markdown(
            md_body, source=str(image_paths[0] if image_paths else ""), provider="daily_vision"
        )
        qa = quality_from_markdown(md_body)
        write_run_sidecar(
            out_dir,
            workflow="日常识图",
            profile="daily_vision",
            markdown_path=str(md_path),
            status="done",
            extra={
                "model": DEFAULT_MODEL,
                "task_profile": DAILY_VISION.name,
                "source_count": len(image_paths),
            },
            document=ir,
            quality=qa,
        )
    except Exception:
        pass
    return md_path
