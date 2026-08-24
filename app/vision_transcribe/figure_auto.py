"""高保真 Figure：复用 Docling 自动裁图（与快速自动 AssetPipeline 同源）。"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

from app.vision_transcribe.figure_store import load_figures_json, save_figures_json
from app.vision_transcribe.manifest import vision_dir
from app.vision_transcribe.models import FIGURE_MARKER_RE, FigureRecord

LogFn = Callable[[str], None]

_IMG_MD = re.compile(
    r"!\[[^\]]*\]\((?P<url>images/[^)]+)\)",
    re.IGNORECASE,
)
_FIGURE_CAPTION = re.compile(r"Figure\s+(\d+)", re.IGNORECASE)


def _resolve_picture_path(item, images_dir: Path, doc) -> Path | None:
    """从 Docling PictureItem 解析已导出文件路径，必要时用 get_image 落盘。"""
    from docling_core.types.doc import PictureItem

    if not isinstance(item, PictureItem):
        return None

    if item.image is not None and item.image.uri is not None:
        uri = item.image.uri
        if isinstance(uri, Path):
            if uri.is_file():
                return uri.resolve()
        else:
            scheme = getattr(uri, "scheme", None)
            if scheme == "file":
                p = Path(unquote(str(uri.path)))
                if p.is_file():
                    return p.resolve()
            name = Path(str(uri)).name
            if name:
                for base in (images_dir, images_dir.parent / "images"):
                    cand = base / name
                    if cand.is_file():
                        return cand.resolve()

    try:
        pil = item.get_image(doc)
    except Exception:
        pil = None
    if pil is None:
        return None
    images_dir.mkdir(parents=True, exist_ok=True)
    page_no = int(item.prov[0].page_no) if item.prov else 0
    idx = len(list(images_dir.glob(f"_tmp_p{page_no:04d}_*.png"))) + 1
    dest = images_dir / f"_tmp_p{page_no:04d}_{idx:02d}.png"
    pil.save(dest, format="PNG", optimize=True)
    return dest.resolve()


def collect_docling_pictures_by_page(document, images_dir: Path) -> dict[int, list[Path]]:
    """按 PDF 页码收集 Docling 导出的图片（阅读顺序）。"""
    from docling_core.types.doc import PictureItem

    by_page: dict[int, list[Path]] = {}
    for item, _level in document.iterate_items():
        if not isinstance(item, PictureItem) or not item.prov:
            continue
        page_no = int(item.prov[0].page_no)
        path = _resolve_picture_path(item, images_dir, document)
        if path is None:
            continue
        by_page.setdefault(page_no, []).append(path)
    return by_page


def _ordered_images_from_docling_md(md_path: Path) -> list[Path]:
    """从 Docling 导出的 raw.md 按出现顺序收集 images/ 路径。"""
    if not md_path.is_file():
        return []
    text = md_path.read_text(encoding="utf-8-sig")
    base = md_path.parent
    out: list[Path] = []
    for m in _IMG_MD.finditer(text):
        rel = m.group("url").strip()
        p = (base / rel).resolve()
        if p.is_file():
            out.append(p)
    return out


def _figure_number_paths_from_docling_md(md_path: Path) -> dict[int, Path]:
    """Figure N 标题附近最近的图片 → 用于与 Vision 占位符按序号对齐。"""
    if not md_path.is_file():
        return {}
    lines = md_path.read_text(encoding="utf-8-sig").splitlines()
    mapping: dict[int, Path] = {}
    last_fig_num: int | None = None
    base = md_path.parent
    for line in lines:
        cap = _FIGURE_CAPTION.search(line)
        if cap:
            last_fig_num = int(cap.group(1))
        for m in _IMG_MD.finditer(line):
            if last_fig_num is None:
                continue
            rel = m.group("url").strip()
            p = (base / rel).resolve()
            if p.is_file() and last_fig_num not in mapping:
                mapping[last_fig_num] = p
    return mapping


def _materialize_figure_file(
    src: Path,
    *,
    images_dir: Path,
    pdf_stem: str,
    global_order: int,
) -> str:
    """复制到 images/ 并返回文件名（与快速模式 image_N_stem 风格一致）。"""
    images_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower() if src.suffix else ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        ext = ".png"
    name = f"image_{global_order}_{pdf_stem}{ext}"
    dest = images_dir / name
    if src.resolve() != dest.resolve():
        if dest.exists():
            dest.unlink()
        shutil.copy2(src, dest)
    if not dest.is_file():
        raise FileNotFoundError(dest)
    return name


def _assign_figure_paths(
    figures: list[FigureRecord],
    *,
    by_page: dict[int, list[Path]],
    ordered_paths: list[Path],
    fig_num_paths: dict[int, Path],
    fig_nums_by_marker: dict[str, int],
    images_dir: Path,
    pdf_stem: str,
    log: LogFn | None,
) -> int:
    """将 Docling 图片路径绑定到 Vision FIGURE 标记。"""
    pending = sorted(figures, key=lambda f: (f.page, f.index))
    targets: list[Path | None] = [None] * len(pending)

    # 1) PDF 页码 + 页内序号（与 FIGURE:p0007:f01 一致，最优先）
    if by_page:
        for i, rec in enumerate(pending):
            page_imgs = by_page.get(int(rec.page), [])
            idx = int(rec.index) - 1
            if 0 <= idx < len(page_imgs):
                targets[i] = page_imgs[idx]
                if log:
                    log(
                        f"Figure {rec.marker}：按页码 p{rec.page:04d} "
                        f"第 {rec.index} 张匹配"
                    )

    # 2) Docling 题注 Figure N（用 Vision 题注编号，不用列表下标）
    if fig_num_paths and fig_nums_by_marker:
        for i, rec in enumerate(pending):
            if targets[i] is not None:
                continue
            n = fig_nums_by_marker.get(rec.marker)
            if n is not None and n in fig_num_paths:
                targets[i] = fig_num_paths[n]
                if log:
                    log(f"Figure {rec.marker}：按题注 Figure {n} 匹配")

    # 3) 全局顺序兜底（Docling 常多一张页眉/logo，跳过首张）
    if any(t is None for t in targets) and ordered_paths:
        skip = max(0, len(ordered_paths) - len(pending))
        pool = ordered_paths[skip:]
        for i, rec in enumerate(pending):
            if targets[i] is not None:
                continue
            if i < len(pool):
                targets[i] = pool[i]
                if log:
                    log(f"Figure {rec.marker}：按 Docling 导出顺序兜底")

    filled = 0
    all_figs_list = load_figures_json(images_dir.parent) or list(figures)
    all_figs = {f.marker: f for f in all_figs_list}
    global_order = 0
    for rec, src in zip(pending, targets):
        if src is None or not src.is_file():
            if log:
                log(f"Figure {rec.marker}：未匹配到 Docling 图片")
            continue
        global_order += 1
        fname = _materialize_figure_file(
            src,
            images_dir=images_dir,
            pdf_stem=pdf_stem,
            global_order=global_order,
        )
        target = all_figs.get(rec.marker, rec)
        target.file = fname
        target.status = "done"
        rec.file = fname
        rec.status = "done"
        filled += 1
    save_figures_json(images_dir.parent, list(all_figs.values()))
    return filled


def auto_fill_figures_from_docling(
    pdf_path: Path,
    output_dir: Path,
    figures: list[FigureRecord],
    *,
    image_path_mode: str = "relative",
    images_scale: float = 2.0,
    log: LogFn | None = None,
) -> int:
    """对 FIGURE 占位符：Docling 出图 → 写入 output_dir/images/ → 按 Figure 序号/页码匹配。"""
    if not figures:
        return 0

    def emit(msg: str) -> None:
        if log:
            log(msg)

    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    export_dir = vision_dir(output_dir) / "docling_export"
    export_dir.mkdir(parents=True, exist_ok=True)
    scratch_md = export_dir / f"{pdf_path.stem}.raw.md"

    emit("Figure：Docling 自动裁图（与快速自动相同）…")
    emit("Figure：Docling 解析 PDF 中（首次约 1–3 分钟，请稍候）…")
    from app.engines.docling_engine import _ensure_hf_mirror, _export_markdown, _get_converter

    _ensure_hf_mirror()
    converter, _use_cuda, _threads, _reused = _get_converter(
        keep_images=True,
        keep_tables=False,
        keep_formulas=False,
        ocr_mode="auto",
        images_scale=float(images_scale),
    )
    result = converter.convert(str(pdf_path))
    emit("Figure：Docling 解析完成，导出图片…")
    _export_markdown(
        result,
        scratch_md,
        True,
        image_path_mode=image_path_mode,
    )

    export_images = scratch_md.parent / "images"
    if export_images.is_dir():
        for p in export_images.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                continue
            dest = images_dir / p.name
            if not dest.exists() or dest.stat().st_size != p.stat().st_size:
                shutil.copy2(p, dest)

    by_page = collect_docling_pictures_by_page(result.document, images_dir)
    ordered_paths = _ordered_images_from_docling_md(scratch_md)
    if not ordered_paths:
        ordered_paths = sorted(
            [
                p
                for p in images_dir.iterdir()
                if p.is_file()
                and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
                and not p.name.startswith("_tmp_")
            ],
            key=lambda p: p.name,
        )
    fig_num_paths = _figure_number_paths_from_docling_md(scratch_md)

    cleaned_md_path = vision_dir(output_dir) / "document.cleaned.md"
    fig_nums_by_marker: dict[str, int] = {}
    if cleaned_md_path.is_file():
        from app.vision_transcribe.figure_markers import figure_numbers_by_marker

        fig_nums_by_marker = figure_numbers_by_marker(
            cleaned_md_path.read_text(encoding="utf-8")
        )

    if not ordered_paths and not by_page:
        emit("Figure：Docling 未检测到可导出图片")
        return 0

    emit(
        f"Figure：Docling 导出 {len(ordered_paths)} 张图，"
        f"待匹配 Vision 占位符 {len(figures)} 个"
    )
    filled = _assign_figure_paths(
        figures,
        by_page=by_page,
        ordered_paths=ordered_paths,
        fig_num_paths=fig_num_paths,
        fig_nums_by_marker=fig_nums_by_marker,
        images_dir=images_dir,
        pdf_stem=pdf_path.stem,
        log=log,
    )
    emit(f"Figure：Docling 自动写入 {filled}/{len(figures)} 张 → images/")
    return filled
