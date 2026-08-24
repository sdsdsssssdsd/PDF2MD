# -*- coding: utf-8 -*-
"""DeepSeek-OCR 2 实验层：extractor / cache / fake benchmark。"""
from __future__ import annotations

from pathlib import Path

from app.ocr.cache import PageOCRCache, RegionOCRCache, file_sha1
from app.ocr.extractor import FormulaFromDocumentOCRExtractor
from app.ocr import OCRMode, DocumentOCRResult
from app.ocr.deepseek_ocr2 import FakeDeepSeekOCR2Recognizer, DeepSeekOCR2Recognizer
from app.ocr.deepseek_benchmark import (
    DeepSeekBenchmarkConfig,
    FormulaBenchmarkService,
    build_o018_cases,
    run_deepseek_benchmark,
)
from app.formula.benchmark import BenchmarkCase
from app.formula.recognizer import NullFormulaRecognizer


def test_extractor_by_equation_number():
    md = r"""
Some text
$$Recall = \frac{TP}{TP+FN}$$
(4)
More
"""
    ex = FormulaFromDocumentOCRExtractor()
    cand = ex.extract(md, eq_number="4", context_before="Recall Eq. (4)")
    assert cand is not None
    assert "TP" in cand.text
    assert "FN" in cand.text


def test_extractor_never_invents_from_context_alone():
    ex = FormulaFromDocumentOCRExtractor()
    # OCR 输出完全无关，不能因为 context 有 Recall 就发明公式
    cand = ex.extract(
        "hello world no math here",
        eq_number="4",
        context_before="Recall can be calculated using Eq. (4):",
    )
    assert cand is None


def test_page_cache_reuses_same_page():
    cache = PageOCRCache()
    key = cache.make_key(pdf_hash="abc", page=6, recognizer="ds", config={"a": 1})
    res = DocumentOCRResult(
        raw_output="x",
        markdown="x",
        recognizer="ds",
        mode="page",
        elapsed_seconds=1.0,
        success=True,
    )
    assert cache.get(key) is None
    cache.put(key, res)
    assert cache.get(key) is res
    assert cache.stats.hits == 1
    assert cache.stats.misses == 1


def test_deepseek_unavailable_without_cuda_when_cpu_disallowed(monkeypatch):
    DeepSeekOCR2Recognizer.reset_class_model()

    class FakeTorch:
        @staticmethod
        def cuda():
            class C:
                @staticmethod
                def is_available():
                    return False

            return C()

    # 只测 _resolve_device 逻辑
    rec = DeepSeekOCR2Recognizer(allow_cpu=False, device="auto")
    monkeypatch.setattr("torch.cuda.is_available", lambda: False)
    try:
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    except Exception:
        pass
    from app.ocr import DeepSeekOCRUnavailable

    try:
        rec._resolve_device()
        raised = False
    except DeepSeekOCRUnavailable as e:
        raised = True
        assert e.reason == "gpu_recommended"
    assert raised


def test_fake_benchmark_page_cache(tmp_path: Path):
    # 最小 PDF：用 pymupdf 建一页空白 + 右侧 (4)
    import pymupdf

    pdf = tmp_path / "tiny.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((500, 400), "(4)", fontsize=12)
    page.insert_text((320, 400), "Recall = TP/(TP+FN)", fontsize=11)
    doc.save(pdf)
    doc.close()

    md = "$$Recall=\\frac{TP}{TP+FN}$$\n(4)\n$$FPR=\\frac{FP}{FP+TN}$$\n(7)\n"
    fake = FakeDeepSeekOCR2Recognizer({"page": md, "region": md, "formula": md, "*": md})
    cfg = DeepSeekBenchmarkConfig(
        experiment_only=True,
        run_baseline=True,
        baseline_recognizer="null",
        run_deepseek_formula=False,
        run_deepseek_region=False,
        run_deepseek_page=True,
    )
    cases = [
        BenchmarkCase(pdf_path=str(pdf), eq_number="4", gold_latex=r"Recall=\frac{TP}{TP+FN}"),
        BenchmarkCase(pdf_path=str(pdf), eq_number="4", gold_latex=r"Recall=\frac{TP}{TP+FN}"),
    ]
    svc = FormulaBenchmarkService(
        cfg,
        doc_recognizer=fake,
        formula_recognizer=NullFormulaRecognizer(),
    )
    r1 = svc.run_case(cases[0])
    r2 = svc.run_case(cases[1])
    assert r1["modes"]["deepseek_page"]["extracted_latex"]
    assert r2["modes"]["deepseek_page"]["timing"]["cache_hit"] is True
    assert svc.telemetry["unique_pages_ocr"] == 1
    assert svc.telemetry["cache_hits"] >= 1


def test_run_deepseek_benchmark_fake_writes_json(tmp_path: Path):
    import pymupdf

    pdf = tmp_path / "t.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((500, 500), "(4)", fontsize=12)
    doc.save(pdf)
    doc.close()
    out = tmp_path / "out.json"
    md = "$$Recall=\\frac{TP}{TP+FN}$$\n(4)\n"
    fake = FakeDeepSeekOCR2Recognizer({"*": md, "page": md, "formula": md, "region": md})
    payload = run_deepseek_benchmark(
        pdf,
        cfg=DeepSeekBenchmarkConfig(
            experiment_only=True,
            run_baseline=False,
            run_deepseek_formula=True,
            run_deepseek_region=True,
            run_deepseek_page=True,
        ),
        cases=[BenchmarkCase(pdf_path=str(pdf), eq_number="4", gold_latex=r"Recall=\frac{TP}{TP+FN}")],
        doc_recognizer=fake,
        out_path=out,
    )
    assert out.exists()
    assert payload["experiment_only"] is True
    assert "summary" in payload
