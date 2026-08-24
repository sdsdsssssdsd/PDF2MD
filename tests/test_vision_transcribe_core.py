"""高保真视觉转录单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.vision_transcribe.batch_planner import plan_batches, split_batch_for_retry
from app.vision_transcribe.batch_validator import validate_batch_markdown
from app.vision_transcribe.cleaner import clean_vision_markdown
from app.vision_transcribe.figure_writeback import writeback_figures
from app.vision_transcribe.manifest import VisionManifest, save_manifest, load_manifest
from app.vision_transcribe.merger import merge_accepted_batches
from app.vision_transcribe.models import BatchInfo, BatchStatus, FigureRecord, PAGE_MARKER_RE
from app.vision_transcribe.prompt_builder import build_prompt
from app.vision_transcribe.prompts import PROMPT_VERSION


def test_vision_task_output_dir_suffix():
    from app.utils.paths import vision_task_output_dir

    root = Path("D:/out")
    pdf = Path("D:/papers/foo.pdf")
    assert vision_task_output_dir(root, pdf) == Path("D:/out/foo_高保真")


def test_plan_batches_73_pages():
    batches = plan_batches(73, 10)
    assert len(batches) == 8
    assert batches[0].start_page == 1 and batches[0].end_page == 10
    assert batches[-1].start_page == 71 and batches[-1].end_page == 73


def test_split_retry():
    b = BatchInfo(id=3, start_page=21, end_page=30)
    parts = split_batch_for_retry(b)
    assert len(parts) == 2
    assert parts[0].end_page == 25
    assert parts[1].start_page == 26


def test_page_marker_regex():
    md = "<!-- PDF2MD:PAGE:0007 -->\nhello\n<!-- PDF2MD:PAGE:0008 -->"
    pages = [int(m.group(1)) for m in PAGE_MARKER_RE.finditer(md)]
    assert pages == [7, 8]


def test_validator_accept():
    parts = []
    for p in range(1, 4):
        parts.append(f"<!-- PDF2MD:PAGE:{p:04d} -->\n正文 {p}\n")
    md = "\n".join(parts)
    r = validate_batch_markdown(md, start_page=1, end_page=3)
    assert r.ok, r.errors


def test_validator_reject_missing():
    md = "<!-- PDF2MD:PAGE:0001 -->\nA\n<!-- PDF2MD:PAGE:0003 -->\nC\n"
    r = validate_batch_markdown(md, start_page=1, end_page=3)
    assert not r.ok
    assert any("缺页" in e for e in r.errors)


def test_cleaner_strips_page_keeps_figure():
    md = (
        "<!-- PDF2MD:PAGE:0001 -->\n"
        "text\n"
        "<!-- PDF2MD:FIGURE:p0001:f01 -->\n"
        "---\n"
        "more\n"
    )
    out = clean_vision_markdown(md)
    assert "PDF2MD:PAGE" not in out
    assert "PDF2MD:FIGURE:p0001:f01" in out
    assert "---" not in out.splitlines() or not any(
        line.strip() == "---" for line in out.splitlines()
    )


def test_merger_order(tmp_path: Path):
    out = tmp_path
    m = VisionManifest(page_count=4, batch_size=2)
    m.set_batches(
        [
            BatchInfo(1, 1, 2, BatchStatus.ACCEPTED.value),
            BatchInfo(2, 3, 4, BatchStatus.ACCEPTED.value),
        ]
    )
    save_manifest(out, m)
    b1 = out / ".vision" / "batches" / "batch_0001"
    b2 = out / ".vision" / "batches" / "batch_0002"
    b1.mkdir(parents=True)
    b2.mkdir(parents=True)
    (b1 / "response.md").write_text(
        "<!-- PDF2MD:PAGE:0001 -->\nA\n<!-- PDF2MD:PAGE:0002 -->\nB\n", encoding="utf-8"
    )
    (b2 / "response.md").write_text(
        "<!-- PDF2MD:PAGE:0003 -->\nC\n<!-- PDF2MD:PAGE:0004 -->\nD\n", encoding="utf-8"
    )
    path = merge_accepted_batches(out, load_manifest(out))
    text = path.read_text(encoding="utf-8")
    assert text.index("PAGE:0001") < text.index("PAGE:0003")


def test_figure_writeback():
    md = "before\n<!-- PDF2MD:FIGURE:p0008:f01 -->\nafter\n"
    figs = [
        FigureRecord(
            marker="p0008:f01",
            page=8,
            index=1,
            file="figures/p0008_fig01.png",
            status="done",
        )
    ]
    out = writeback_figures(md, figs)
    assert "![](figures/p0008_fig01.png)" in out
    assert "PDF2MD:FIGURE" not in out


def test_clean_figure_marker_before_page_strip():
    raw = (
        "<!-- PDF2MD:PAGE:0002 -->\n\n"
        "Figure 1: Test caption.\n"
    )
    out = clean_vision_markdown(raw)
    assert "PDF2MD:FIGURE:p0002:f01" in out
    assert "PDF2MD:PAGE" not in out


def test_repair_missing_figure_markers():
    from app.vision_transcribe.figure_markers import repair_missing_figure_markers

    md = (
        "<!-- PDF2MD:PAGE:0002 -->\n\n"
        "Figure 1: Illustration of model.\n"
    )
    out = repair_missing_figure_markers(md)
    assert "PDF2MD:FIGURE:p0002:f01" in out


def test_figure_numbers_by_marker():
    from app.vision_transcribe.figure_markers import figure_numbers_by_marker

    md = (
        "<!-- PDF2MD:FIGURE:p0007:f01 -->\n\n"
        "**Figure 2: Predicted probabilities**\n"
    )
    nums = figure_numbers_by_marker(md)
    assert nums["p0007:f01"] == 2


def test_repair_example_com_figure_urls():
    from app.vision_transcribe.vision_structure_repair import (
        repair_deepseek_placeholder_figures,
    )

    md = (
        "<!-- PDF2MD:PAGE:0002 -->\n"
        "Caption\nhttps://example.com/figure1.png\n"
        "![Figure 2](https://example.com/figure2.png)\n"
    )
    out = repair_deepseek_placeholder_figures(md)
    assert "example.com" not in out
    assert "PDF2MD:FIGURE:p0002:f01" in out
    assert "PDF2MD:FIGURE:p0002:f02" in out


def test_formula_integrity_orphan_where():
    from app.vision_transcribe.formula_integrity import formula_integrity_errors

    bad = (
        "The model, considering the nested nature and the interaction effects, was:\n\n"
        "where $P_{ijc}$ represents the probability.\n"
        r"\logit(P) = \beta_0 \quad (2)\n"
    )
    errs = formula_integrity_errors(bad)
    assert errs
    assert any("缺失" in e or "不连续" in e for e in errs)

    good = (
        "The model was:\n\n"
        r"$$\n\logit(P_{ijc}) = \beta_0 + \beta_1 X \quad (1)\n$$\n\n"
        "where $P_{ijc}$ represents the probability.\n"
        r"$$\n\logit(P_{ijc}) = \beta_0 + \gamma \quad (2)\n$$\n"
    )
    assert not formula_integrity_errors(good)


def test_validator_rejects_missing_equation():
    parts = []
    for p in range(1, 3):
        parts.append(f"<!-- PDF2MD:PAGE:{p:04d} -->\n" + "x" * 400 + "\n")
    md = "\n".join(parts)
    md += (
        "The model, considering the nested nature and the interaction effects, was:\n\n"
        "where $P_{ijc}$ represents the probability.\n"
        r"\logit(P_{ijc}) = \beta_0 \quad (2)\n"
    )
    r = validate_batch_markdown(md, start_page=1, end_page=2)
    assert not r.ok
    assert any("公式" in e or "不连续" in e for e in r.errors)


def test_pick_best_prefers_complete_formulas():
    from app.vision_transcribe.transcript_quality import pick_best_transcript

    dom = (
        "<!-- PDF2MD:PAGE:0001 -->\n" + "a" * 5000 + "\n"
        "The model was:\n\nwhere $P$ is prob.\n"
        r"\logit(P) = \beta \quad (2)\n"
    )
    clip = (
        "<!-- PDF2MD:PAGE:0001 -->\n" + "a" * 3000 + "\n"
        "The model was:\n\n"
        r"$$\n\logit(P) = \beta_0 \quad (1)\n$$\n\n"
        "where $P$ is prob.\n"
        r"$$\n\logit(P) = \beta_0 + \gamma \quad (2)\n$$\n"
    )
    src, text = pick_best_transcript(("dom-md", dom), ("clipboard", clip))
    assert src == "clipboard"
    assert "(1)" in text


    p = build_prompt(21, 30)
    assert "PAGE 0021" in p and "PAGE 0030" in p
    assert "不得遗漏" in p or "完整保留" in p
    assert PROMPT_VERSION.startswith("vision-transcribe")


def test_katex_scrap_detects_dom_formula_garbage():
    from app.vision_transcribe.browser.katex_scrap import has_dom_katex_scrap

    sample = "The model was:\nlogit\n(\n𝑝\n𝑖\n𝑗\n𝑐\n)\n=\n𝛽\n0\n+\n"
    assert has_dom_katex_scrap(sample)


def test_katex_scrap_accepts_proper_latex():
    from app.vision_transcribe.browser.katex_scrap import has_dom_katex_scrap

    sample = (
        "The model was:\n$$\n"
        r"\operatorname{logit}(p_{ijc}) = \beta_0 + \beta_1 \text{TMA1}_i"
        "\n$$\n"
    )
    assert not has_dom_katex_scrap(sample)


def test_validator_rejects_katex_scrap():
    parts = []
    for p in range(1, 3):
        parts.append(f"<!-- PDF2MD:PAGE:{p:04d} -->\n正文 {p}\n")
    md = "\n".join(parts)
    md += "logit\n(\n𝑝\n𝑖\n𝑗\n𝑐\n)\n=\n𝛽\n0\n+\n𝛽\n1\n+\n𝛽\n2\n+\n"
    r = validate_batch_markdown(md, start_page=1, end_page=2)
    assert not r.ok
    assert any("竖排" in e for e in r.errors)


def test_clipboard_sanitize_strips_sidebar_and_prompt():
    from app.vision_transcribe.clipboard_sanitize import (
        has_clipboard_contamination,
        sanitize_vision_clipboard,
    )

    junk = (
        "Cursor聊天记录\nPDF转Markdown\nHigh-SES students\n"
        "你正在执行 PDF → Markdown 高保真内容转录任务。\n"
        "本批次为 PAGE 0001 至 PAGE 0010。\n"
        "<!-- PDF2MD:PAGE:0001 -->\n"
        "Paper title\n"
    )
    assert has_clipboard_contamination(junk)
    out = sanitize_vision_clipboard(junk)
    assert out.startswith("<!-- PDF2MD:PAGE:0001 -->")
    assert "Cursor聊天记录" not in out
    assert "你正在执行 PDF" not in out


def test_validator_rejects_sidebar_contamination():
    md = (
        "Cursor聊天记录\nPDF转Markdown\n"
        "你正在执行 PDF → Markdown 高保真内容转录任务。\n"
        "<!-- PDF2MD:PAGE:0001 -->\nbody\n"
    )
    r = validate_batch_markdown(md, start_page=1, end_page=1)
    assert not r.ok
    assert any("侧栏" in e or "Prompt" in e for e in r.errors)


def test_reset_all_batches_for_rerun():
    from app.vision_transcribe.manifest import VisionManifest
    from app.vision_transcribe.models import BatchInfo, BatchStatus, PipelineState

    m = VisionManifest()
    m.set_batches(
        [
            BatchInfo(1, 1, 10, BatchStatus.ACCEPTED.value),
            BatchInfo(2, 11, 11, BatchStatus.ACCEPTED.value),
        ]
    )
    m.state = PipelineState.DONE.value
    n = m.reset_all_batches_for_rerun()
    assert n == 2
    assert all(b.status == BatchStatus.PENDING.value for b in m.get_batches())
    assert m.state == PipelineState.READY_TO_TRANSCRIBE.value


def test_next_pending_after_full_reset():
    from app.vision_transcribe.manifest import VisionManifest
    from app.vision_transcribe.models import BatchInfo, BatchStatus

    m = VisionManifest()
    m.set_batches([BatchInfo(1, 1, 10, BatchStatus.ACCEPTED.value)])
    m.reset_all_batches_for_rerun()
    b = m.next_pending_batch()
    assert b is not None and b.id == 1
    from app.vision_transcribe.manifest import VisionManifest
    from app.vision_transcribe.models import BatchInfo, BatchStatus

    m = VisionManifest()
    m.set_batches(
        [
            BatchInfo(1, 1, 10, BatchStatus.WAITING_RESPONSE.value),
            BatchInfo(2, 11, 11, BatchStatus.PENDING.value),
        ]
    )
    b = m.next_pending_batch()
    assert b is not None and b.id == 1
    m.reset_incomplete_batches()
    assert all(x.status == BatchStatus.PENDING.value for x in m.get_batches())


def test_batch_transcript_complete_requires_all_pages():
    from app.vision_transcribe.transcript_quality import batch_transcript_complete

    partial = "<!-- PDF2MD:PAGE:0001 -->\n" + ("x" * 25_000)
    assert not batch_transcript_complete(partial, start_page=1, end_page=10)

    full = "".join(f"<!-- PDF2MD:PAGE:{p:04d} -->\n" for p in range(1, 11))
    full += "x" * 15_000
    assert batch_transcript_complete(full, start_page=1, end_page=10)
