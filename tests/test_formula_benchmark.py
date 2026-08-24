# -*- coding: utf-8 -*-
"""Formula Benchmark Lab：矩阵展开 / gold / 假 OCR 跑通。"""
from __future__ import annotations

from pathlib import Path

from app.formula.benchmark import (
    BenchmarkCase,
    BenchmarkConfig,
    BenchmarkRow,
    expand_matrix,
    gold_match,
    list_pdf_equations,
    pareto_summary,
    preview_crop,
    run_benchmark,
    save_benchmark_run,
)
from app.formula.preprocess import apply_named_preprocess
from app.formula.recognizer import FormulaRecognitionResult


class _FakeRec:
    name = "pix2tex"

    def recognize(self, image, context=None):
        assert context is None
        return FormulaRecognitionResult(
            latex=r"Recall = \frac{TP}{TP+FN}",
            success=True,
            recognizer=self.name,
            raw=r"Recall = \frac{TP}{TP+FN}",
        )


def _tiny_pdf(tmp_path: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Recall can be calculated using Eq. (4)")
    page.insert_text((500, 200), "(4)")
    path = tmp_path / "lab.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_expand_matrix_default_is_small():
    cfgs = expand_matrix()
    assert len(cfgs) == 2
    assert {c.label for c in cfgs} == {"2× medium original", "2.5× medium original"}


def test_expand_matrix_full_36():
    cfgs = expand_matrix(
        scales=(1.5, 2.0, 2.5, 3.0),
        paddings=("small", "medium", "large"),
        preprocesses=("original", "contrast", "sharpen"),
    )
    assert len(cfgs) == 36


def test_gold_match_and_pareto():
    assert gold_match(r"Recall=\frac{TP}{TP+FN}", r"Recall = \frac{TP}{TP+FN}") == "yes"
    assert gold_match(r"\omega", r"Recall = x") == "no"
    assert gold_match("x", "") == "—"
    rows = [
        BenchmarkRow(
            config_label="2× medium original",
            scale=2.0,
            padding="medium",
            preprocess="original",
            recognizer="pix2tex",
            ocr_seconds=1.0,
            decision="accept",
            gold_match="yes",
        ),
        BenchmarkRow(
            config_label="3× contrast",
            scale=3.0,
            padding="medium",
            preprocess="contrast",
            recognizer="pix2tex",
            ocr_seconds=4.0,
            decision="reject",
            gold_match="no",
        ),
    ]
    p = pareto_summary(rows)
    assert p["accept_n"] == 1
    assert p["gold_match_n"] == 1
    assert p["fastest_accept"]["label"] == "2× medium original"
    assert p["by_scale"]["2"]["accept_rate"] == 1.0


def test_run_benchmark_with_fake_ocr(tmp_path):
    pdf = _tiny_pdf(tmp_path)
    case = BenchmarkCase(
        pdf_path=str(pdf),
        page=0,
        eq_number="4",
        parser_latex=r"\Gamma",
        context_before="Recall can be calculated using Eq. (4):",
        gold_latex=r"Recall = \frac{TP}{TP+FN}",
    )
    payload = run_benchmark(
        case,
        [BenchmarkConfig(scale=2.0, padding="medium", preprocess="original")],
        recognizer=_FakeRec(),
    )
    assert payload["rows"]
    row = payload["rows"][0]
    assert row["decision"] == "accept"
    assert row["gold_match"] == "yes"
    assert payload["pareto"]["accept_n"] == 1
    out = save_benchmark_run(payload, dest_dir=tmp_path)
    assert out.exists()
    assert "eq4" in out.name


def test_preview_and_list_eq(tmp_path):
    pdf = _tiny_pdf(tmp_path)
    info = list_pdf_equations(pdf)
    assert info["page_count"] == 1
    assert "4" in info["all"]
    img, page, bbox = preview_crop(
        BenchmarkCase(pdf_path=str(pdf), page=0, eq_number="4")
    )
    assert page == 0
    assert bbox[2] > bbox[0]
    assert img is not None


def test_named_preprocess_original_keeps_size():
    from PIL import Image

    img = Image.new("RGB", (20, 10), "white")
    out = apply_named_preprocess(img, "original")
    assert out.size == (20, 10)
    sharp = apply_named_preprocess(img, "sharpen")
    assert sharp.size[0] >= 20
