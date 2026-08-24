# -*- coding: utf-8 -*-
"""Phase 3A：EquationExtractor 校准 — 用 O-018 真实 DeepSeek 输出做回归。"""
from __future__ import annotations

from pathlib import Path

from app.ocr.extractor import (
    EquationExtractor,
    FormulaFromDocumentOCRExtractor,
    parse_equation_blocks,
    raw_ocr_contains_gold,
)
from app.ocr.deepseek_benchmark import DEFAULT_O018_CASES

FIXTURES = Path(__file__).resolve().parents[1] / "debug" / "formula_benchmark" / "fixtures"

_CASES = {str(c["eq_number"]): c for c in DEFAULT_O018_CASES}


def _load(name: str) -> str:
    p = FIXTURES / name
    assert p.exists(), f"missing fixture {p}"
    return p.read_text(encoding="utf-8")


def test_parse_region_eq4_has_numbered_block():
    md = _load("o018_eq4_deepseek_region.md")
    blocks = parse_equation_blocks(md)
    nums = {b.equation_number for b in blocks}
    assert "4" in nums
    assert "3" in nums or "5" in nums  # 同 region 常带邻式


def test_extract_eq4_from_region_not_prose():
    md = _load("o018_eq4_deepseek_region.md")
    ex = EquationExtractor()
    er = ex.extract(
        md,
        eq_number="4",
        context_before=_CASES["4"]["context_before"],
    )
    assert er.block is not None
    assert er.method in {"exact_number", "number_nearby", "label_match"}
    assert "TP" in er.latex and "FN" in er.latex
    assert "quantifies the ratio" not in er.latex


def test_extract_eq4_from_page():
    md = _load("o018_eq4_deepseek_page.md")
    er = EquationExtractor().extract(
        md, eq_number="4", context_before=_CASES["4"]["context_before"]
    )
    assert er.block is not None
    assert er.block.equation_number == "4"
    assert "Recall" in er.latex or "TP" in er.latex


def test_extract_eq1_from_page():
    md = _load("o018_eq1_deepseek_page.md")
    er = EquationExtractor().extract(
        md, eq_number="1", context_before=_CASES["1"]["context_before"]
    )
    assert er.block is not None
    assert er.block.equation_number == "1"
    assert "Bias" in er.latex or "varepsilon" in er.latex or "ε" in er.latex


def test_extract_eq6_and_eq7_from_page6_fixture():
    md = _load("o018_eq6_deepseek_page.md")
    ex = EquationExtractor()
    r6 = ex.extract(md, eq_number="6", context_before=_CASES["6"]["context_before"])
    r7 = ex.extract(md, eq_number="7", context_before=_CASES["7"]["context_before"])
    assert r6.block and r6.block.equation_number == "6"
    assert "TPR" in r6.latex or "TP" in r6.latex
    assert r7.block and r7.block.equation_number == "7"
    assert "FPR" in r7.latex or "FP" in r7.latex
    # 不能抽成同一块
    assert r6.latex != r7.latex or r6.block.order != r7.block.order


def test_never_invent_from_context():
    er = EquationExtractor().extract(
        "hello world no math",
        eq_number="4",
        context_before="Recall can be calculated using Eq. (4):",
    )
    assert er.block is None
    assert er.failure_reason


def test_raw_ocr_contains_gold_vs_extractor_on_region():
    md = _load("o018_eq4_deepseek_region.md")
    gold = _CASES["4"]["gold_latex"]
    assert raw_ocr_contains_gold(md, gold) == "yes"
    er = EquationExtractor().extract(md, eq_number="4", context_before=_CASES["4"]["context_before"])
    assert er.block is not None
    # 抽取后应含 TP/FN
    assert "TP" in er.latex


def test_compat_formula_from_document_ocr_extractor():
    md = _load("o018_eq4_deepseek_formula.md")
    cand = FormulaFromDocumentOCRExtractor().extract(
        md, eq_number="4", context_before=_CASES["4"]["context_before"]
    )
    assert cand is not None
    assert "TP" in cand.text


def test_all_o018_fixtures_extractor_regression():
    """固定五式 × region/page：编号必须抽到公式而非散文。"""
    ex = EquationExtractor()
    failures: list[str] = []
    for n, spec in _CASES.items():
        for mode in ("region", "page", "formula"):
            name = f"o018_eq{n}_deepseek_{mode}.md"
            path = FIXTURES / name
            if not path.exists():
                continue
            md = path.read_text(encoding="utf-8")
            er = ex.extract(
                md,
                eq_number=n,
                context_before=str(spec["context_before"]),
            )
            raw_ok = raw_ocr_contains_gold(md, str(spec["gold_latex"]))
            if raw_ok == "yes" and (er.block is None or not _looks_math(er.latex)):
                failures.append(f"{name}: raw has gold but extract failed method={er.method} latex={er.latex[:60]!r}")
            if er.block and "quantifies" in er.latex:
                failures.append(f"{name}: extracted prose")
    assert not failures, "\n".join(failures)


def _looks_math(s: str) -> bool:
    return bool(s) and (("=" in s) or ("\\frac" in s) or ("TP" in s) or ("Bias" in s))
