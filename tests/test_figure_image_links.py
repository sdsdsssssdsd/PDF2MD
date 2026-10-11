"""图片链接相对路径：md 与图片不同层时不能多算一级目录（真实病例回归）。

病例：[01]_Kuzilek2017 的终稿在
    文献/[01]_Kuzilek2017_API视觉/[01]_Kuzilek2017.md
图片在
    文献/[01]_Kuzilek2017_API视觉/images/image_1_*.png
却写成 ![Figure 1]([01]_Kuzilek2017_API视觉/images/image_1_*.png) —— 多了一层目录名，
从 md 所在文件夹拼出来是 [01]_Kuzilek2017_API视觉/[01]_Kuzilek2017_API视觉/images/…，
图片全部打不开。
"""
from __future__ import annotations

from pathlib import Path

from app.vision_transcribe.figure_writeback import writeback_figures
from app.vision_transcribe.models import FigureRecord

_MD = "<!-- PDF2MD:FIGURE:p0002:f01 -->\n\n正文\n"


def _fig(name: str, marker: str = "p0002:f01") -> FigureRecord:
    return FigureRecord(marker=marker, page=2, index=1, file=name, status="done")


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def test_subfolder_layout_uses_path_relative_to_the_document(tmp_path: Path):
    """pdf_sibling：md 与 images/ 同在 <PDF名>_API视觉/ 下 → 链接就是 images/x.png。"""
    result_dir = tmp_path / "[01]_Kuzilek2017_API视觉"
    images_dir = result_dir / "images"
    md_path = result_dir / "[01]_Kuzilek2017.md"
    _touch(images_dir / "image_1_[01]_Kuzilek2017.png")

    out = writeback_figures(
        _MD,
        [_fig("image_1_[01]_Kuzilek2017.png")],
        md_path=md_path,
        output_dir=result_dir,
        images_dir=images_dir,
        image_path_mode="relative",
    )
    assert "](images/image_1_[01]_Kuzilek2017.png)" in out
    assert "[01]_Kuzilek2017_API视觉/images/" not in out  # 不能多一层目录名


def test_flat_layout_links_stay_inside_the_export_dir(tmp_path: Path):
    """扁平保存：md 在导出目录、图片在同级的 <PDF名>.images/ → 链接就是 <PDF名>.images/x.png。"""
    export = tmp_path / "总"
    images_dir = export / "[01]_Kuzilek2017.images"
    md_path = export / "[01]_Kuzilek2017.md"
    _touch(images_dir / "image_1.png")

    out = writeback_figures(
        _MD,
        [_fig("image_1.png")],
        md_path=md_path,
        output_dir=export,
        images_dir=images_dir,
        image_path_mode="relative",
    )
    assert "]([01]_Kuzilek2017.images/image_1.png)" in out
    assert "总/" not in out


def test_absolute_mode_and_missing_image(tmp_path: Path):
    export = tmp_path / "out"
    images_dir = export / "images"
    md_path = export / "paper.md"
    _touch(images_dir / "image_1.png")

    out = writeback_figures(
        _MD,
        [_fig("image_1.png")],
        md_path=md_path,
        images_dir=images_dir,
        image_path_mode="absolute",
    )
    assert str(images_dir.resolve()) in out  # 绝对路径模式不受影响

    # 图片文件不存在时保留占位符（交给完成门报错），不写出坏链接
    kept = writeback_figures(
        _MD, [_fig("missing.png")], md_path=md_path, images_dir=images_dir
    )
    assert kept == _MD


def test_link_resolves_to_the_real_file(tmp_path: Path):
    """真正的验收：按写出的链接从 md 所在目录拼回去，必须指向存在的文件。"""
    result_dir = tmp_path / "[01]_Kuzilek2017_API视觉"
    images_dir = result_dir / "images"
    md_path = result_dir / "[01]_Kuzilek2017.md"
    _touch(images_dir / "image_5_[01]_Kuzilek2017.png")

    out = writeback_figures(
        _MD,
        [_fig("image_5_[01]_Kuzilek2017.png")],
        md_path=md_path,
        images_dir=images_dir,
        image_path_mode="relative",
    )
    url = out.split("](", 1)[1].split(")", 1)[0]
    assert (md_path.parent / url).resolve() == (images_dir / "image_5_[01]_Kuzilek2017.png").resolve()
