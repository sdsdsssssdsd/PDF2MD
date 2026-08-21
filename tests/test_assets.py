"""AssetPipeline 单元测试。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from app.assets.caption_matcher import (
    extract_subfigure_labels,
    normalize_subfigure_index,
    parse_caption_line,
)
from app.assets.md_rewriter import rewrite_markdown_figures
from app.assets.models import AssetConfig, FigureAsset
from app.assets.pipeline import AssetPipeline
from app.assets.subfigure_detector import detect_subfigures
from app.utils.md_postprocess import ensure_figure_table_separation


def test_parse_caption_fig():
    p = parse_caption_line("Fig. 1. Example of an observation window.")
    assert p is not None
    assert "1" in p.number_token
    assert "Fig" in p.label
    assert "Example" in p.body


def test_parse_caption_figure_s1():
    p = parse_caption_line("Figure S1: Supplemental results.")
    assert p is not None
    assert p.number_token.upper().startswith("S")
    assert "Supplemental" in p.body


def test_extract_sublabels():
    labs = extract_subfigure_labels("Results for (a) BERT, (b) RoBERTa, and (c) LLaMA.")
    assert labs == ["a", "b", "c"]


def test_normalize_subfigure_index():
    assert normalize_subfigure_index("a") == 1
    assert normalize_subfigure_index("c") == 3
    assert normalize_subfigure_index("ii") == 2


def test_table_and_image_must_have_blank_line():
    """硬规则：表格与图片之间必须空一行，否则图片会并入表格。"""
    bad = (
        "| Region | chi2 | 12 | 16.325 | 0.1768 |\n"
        "![Figure 5](images/image_5_paper.png)\n"
        "**Figure 5.** Caption.\n"
    )
    fixed = ensure_figure_table_separation(bad)
    assert "|\n\n![Figure 5]" in fixed

    bad_rev = (
        "![Figure 1](images/a.png)\n"
        "| a | b |\n"
        "| --- | --- |\n"
    )
    fixed_rev = ensure_figure_table_separation(bad_rev)
    assert "png)\n\n|" in fixed_rev


def test_subfigure_no_vision_skipped():
    fig = FigureAsset(
        asset_id="fig_0001",
        asset_index=1,
        file="image_1_x.png",
        caption="Figure 1: (a) foo (b) bar",
        figure_label="Figure 1",
    )
    plans, status = detect_subfigures(fig, enable_split=True)
    assert plans == []
    assert status == "skipped"


def test_subfigure_conflict_uncertain():
    fig = FigureAsset(
        asset_id="fig_0001",
        asset_index=1,
        file="image_1_x.png",
        caption="Figure 1: (a) foo (b) bar (c) baz",
        figure_label="Figure 1",
    )
    vision = {
        "has_subfigures": True,
        "subfigures": [
            {"label": "a", "bbox": [0, 0, 0.5, 1], "confidence": 0.99},
            {"label": "b", "bbox": [0.5, 0, 1, 1], "confidence": 0.99},
        ],
    }
    plans, status = detect_subfigures(fig, vision_result=vision, require_all=True)
    assert plans == []
    assert status == "uncertain"


def test_subfigure_match_extracted():
    fig = FigureAsset(
        asset_id="fig_0001",
        asset_index=1,
        file="image_1_x.png",
        caption="Figure 1: (a) foo (b) bar",
        figure_label="Figure 1",
    )
    vision = {
        "has_subfigures": True,
        "subfigures": [
            {"label": "a", "bbox": [0.0, 0.0, 0.5, 1.0], "confidence": 0.99},
            {"label": "b", "bbox": [0.5, 0.0, 1.0, 1.0], "confidence": 0.98},
        ],
    }
    plans, status = detect_subfigures(fig, vision_result=vision)
    assert status == "extracted"
    assert [p.index for p in plans] == [1, 2]
    assert [p.label for p in plans] == ["a", "b"]


def test_rewrite_uses_label_not_asset_index(tmp_path: Path):
    images = tmp_path / "images"
    images.mkdir()
    fig = FigureAsset(
        asset_id="fig_0005",
        asset_index=5,
        file="image_5_paper.png",
        figure_label="Figure 3",
        caption="Figure 3. Results.",
        caption_body="Results.",
    )
    md = tmp_path / "paper.md"
    text = "![Image](images/old.png)\n"
    # only one figure with index 5 won't match order 1 — use index 1
    fig.asset_index = 1
    fig.file = "image_1_paper.png"
    out = rewrite_markdown_figures(
        text,
        [fig],
        md_path=md,
        images_dir=images,
    )
    assert "![Figure 3](" in out
    assert "image_1_paper.png" in out
    assert "**Figure 3.** Results." in out
    assert "Figure 5" not in out


def test_pipeline_renames_and_manifest(tmp_path: Path):
    pdf = tmp_path / "my_paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    images = tmp_path / "images"
    images.mkdir()
    # tiny png
    src = images / "image_000000_abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789.png"
    Image.new("RGB", (8, 8), color=(20, 40, 60)).save(src)

    md = tmp_path / "my_paper.raw.md"
    md.write_text(
        "Fig. 1. A demo figure.\n\n"
        f"![Image](images/{src.name})\n\n"
        "Some text.\n",
        encoding="utf-8",
    )

    result = AssetPipeline(AssetConfig(cleanup_parser_files=True, write_manifest=True)).run(
        pdf_path=pdf,
        markdown_path=md,
        images_dir=images,
        parser_source="test",
    )
    assert (images / "image_1_my_paper.png").is_file()
    assert not src.exists()  # cleaned
    text = md.read_text(encoding="utf-8")
    assert "image_1_my_paper.png" in text
    assert "![Fig. 1](" in text
    assert "**Fig. 1.**" in text
    man = json.loads((images / "manifest.json").read_text(encoding="utf-8"))
    assert man["figures"][0]["asset_index"] == 1
    assert man["figures"][0]["figure_label"].startswith("Fig")
    assert man["figures"][0]["file"] == "image_1_my_paper.png"
    assert result.figures[0].subfigure_status in {"none", "skipped"}
