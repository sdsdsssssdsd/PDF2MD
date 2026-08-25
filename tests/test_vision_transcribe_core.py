"""高保真视觉转录单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.vision_transcribe.batch_ingest import read_raw_response
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
        parts.append(
            f"<!-- PDF2MD:PAGE:{p:04d} -->\n"
            + ("正文 " * 400)
            + f" page{p}\n"
        )
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
    assert "images/p0008_fig01.png" in out
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
    assert "公式编号以论文原图内容为准" in p
    assert "\\tag{1}" in p
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


def test_recover_wait_drops_user_prompt_keeps_paper():
    from app.vision_transcribe.clipboard_sanitize import (
        looks_like_user_prompt,
        recover_wait_transcript,
    )

    prompt = (
        "你正在执行 PDF → Markdown 高保真内容转录任务。\n"
        "本批次为 PAGE 0001 至 PAGE 0009。\n"
        "只允许将原内容转换为 Typora。\n"
    )
    assert looks_like_user_prompt(prompt)
    assert recover_wait_transcript(prompt) == ""

    paper = (
        "<!-- PDF2MD:PAGE:0001 -->\n"
        + ("学术正文。" * 80)
        + "\n"
    )
    assert not looks_like_user_prompt(paper)
    assert recover_wait_transcript(paper).startswith("<!-- PDF2MD:PAGE:0001 -->")

    mixed = prompt + paper
    out = recover_wait_transcript(mixed)
    assert out.startswith("<!-- PDF2MD:PAGE:0001 -->")
    assert "你正在执行 PDF" not in out


def test_formula_integrity_accepts_tag_as_eq1():
    from app.vision_transcribe.formula_integrity import formula_integrity_errors

    md = (
        "$$\nE[y]=x\\tag{1}\n$$\n\n"
        "$$\nE[z]=w\\quad (2)\n$$\n"
    )
    assert not formula_integrity_errors(md)


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


def test_pick_copy_consensus_two_of_three():
    from app.vision_transcribe.capture.consensus import pick_copy_consensus

    text = "A" * 1000
    text2 = "B" * 1000
    label, picked, stable, fail = pick_copy_consensus(
        [
            ("copy_api_1", text),
            ("copy_api_2", text),
            ("clipboard_1", text2),
        ]
    )
    assert stable is True
    assert picked == text
    assert fail == ""
    assert "copy_api" in label


def test_pick_copy_consensus_unstable():
    from app.vision_transcribe.capture.consensus import pick_copy_consensus

    a = "x" * 5000
    b = "y" * 9000
    _, _, stable, fail = pick_copy_consensus(
        [("copy_api_1", a), ("clipboard_1", b)]
    )
    assert stable is False
    assert fail == "EXTRACTION_UNSTABLE"


def test_split_pages_with_end():
    from app.vision_transcribe.capture.page_split import split_pages

    md = (
        "<!-- PDF2MD:PAGE:0001 -->\n"
        "alpha beta 0.913\n"
        "<!-- PDF2MD:PAGE_END:0001 -->\n"
        "<!-- PDF2MD:PAGE:0002 -->\n"
        "gamma delta\n"
        "<!-- PDF2MD:PAGE_END:0002 -->\n"
    )
    pages = split_pages(md)
    assert 1 in pages and pages[1].has_end
    assert "0.913" in pages[1].body


def test_source_guard_missing_numeric():
    from app.vision_transcribe.integrity.source_guard import check_page_anchors

    guard = {
        "enabled": True,
        "anchors": ["0.913", "0.927", "0.845", "0.801"],
        "numeric_anchors": ["0.913", "0.927", "0.845", "0.801"],
    }
    vision = "ResNet-50 0.913"
    miss = check_page_anchors(27, vision, guard)
    assert len(miss) >= 3


def test_source_guard_filters_paper_id():
    from app.vision_transcribe.integrity.source_guard import extract_anchors

    text = (
        "3785022.3785030 Proceedings 2066 [26] 10.1007/978-3 "
        "Experimental Results ResNet-50 accuracy 0.912 0.927"
    )
    anchors = extract_anchors(text)
    assert "3785022.3785030" not in anchors
    assert "[26]" not in anchors
    assert "0.912" in anchors or "0.927" in anchors


def test_validator_v2_soft_markers_warning_only():
    from app.vision_transcribe.prompts import PROMPT_VERSION

    parts = []
    for p in range(1, 3):
        parts.append(
            f"<!-- PDF2MD:PAGE:{p:04d} -->\n"
            + ("正文 " * 400)
            + f" page{p}\n"
        )
    md = "\n".join(parts)
    r = validate_batch_markdown(
        md, start_page=1, end_page=2, batch_id=1, prompt_version=PROMPT_VERSION
    )
    assert r.ok, r.errors
    assert any("PAGE_END" in w or "BATCH_END" in w for w in r.warnings)


def test_validator_v2_reject_short_page():
    from app.vision_transcribe.prompts import PROMPT_VERSION

    md = (
        "<!-- PDF2MD:PAGE:0001 -->\nshort\n"
        "<!-- PDF2MD:PAGE_END:0001 -->\n"
        "<!-- PDF2MD:BATCH_END:0001 -->\n"
    )
    r = validate_batch_markdown(
        md, start_page=1, end_page=1, batch_id=1, prompt_version=PROMPT_VERSION
    )
    assert not r.ok
    assert any("过短" in e for e in r.errors)


def test_validator_figure_heavy_short_page_ok():
    from app.vision_transcribe.prompts import PROMPT_VERSION

    body = (
        "<!-- PDF2MD:FIGURE:p0016:f01 -->\n"
        "Figure 10. Mean |(SHAP value)|.\n"
        "<!-- PDF2MD:PAGE_END:0016 -->"
    )
    md = f"<!-- PDF2MD:PAGE:0016 -->\n{body}\n<!-- PDF2MD:BATCH_END:0002 -->\n"
    r = validate_batch_markdown(
        md, start_page=16, end_page=16, batch_id=2, prompt_version=PROMPT_VERSION
    )
    assert r.ok, r.errors


def test_validator_bold_figure_caption_page_ok():
    from app.vision_transcribe.prompts import PROMPT_VERSION

    body = (
        "**Figure 6.** Predicted probability distribution by true class (XGBoost).\n\n"
        "**Figure 7.** Performance comparison of models (test set).\n"
        "<!-- PDF2MD:PAGE_END:0013 -->"
    )
    md = f"<!-- PDF2MD:PAGE:0013 -->\n{body}\n<!-- PDF2MD:BATCH_END:0002 -->\n"
    r = validate_batch_markdown(
        md, start_page=13, end_page=13, batch_id=2, prompt_version=PROMPT_VERSION
    )
    assert r.ok, r.errors


def test_validator_figure_only_very_short_ok():
    from app.vision_transcribe.prompts import PROMPT_VERSION

    body = "**Figure 10.** Mean |(SHAP value)|.\n<!-- PDF2MD:PAGE_END:0016 -->"
    md = f"<!-- PDF2MD:PAGE:0016 -->\n{body}\n<!-- PDF2MD:BATCH_END:0002 -->\n"
    r = validate_batch_markdown(
        md, start_page=16, end_page=16, batch_id=2, prompt_version=PROMPT_VERSION
    )
    assert r.ok, r.errors


def test_validator_reference_tail_page_ok():
    from app.vision_transcribe.prompts import PROMPT_VERSION

    ref = (
        "Wickham, H., & Bryan, J. (2023). readxl: Read excel files "
        "[Computer software manual]. Retrieved from https://readxl.tidyverse.org"
    )
    md = (
        f"<!-- PDF2MD:PAGE:0014 -->\n{ref}\n"
        "<!-- PDF2MD:PAGE_END:0014 -->\n"
        "<!-- PDF2MD:BATCH_END:0002 -->\n"
    )
    r = validate_batch_markdown(
        md, start_page=14, end_page=14, batch_id=2, prompt_version=PROMPT_VERSION
    )
    assert r.ok, r.errors


def test_validator_boilerplate_tail_page_ok():
    from app.vision_transcribe.prompts import PROMPT_VERSION

    body = (
        "npj Science of Learning (2019) 14\n"
        "Published in partnership with The University of Queensland\n"
        "<!-- PDF2MD:PAGE_END:0010 -->"
    )
    md = f"<!-- PDF2MD:PAGE:0010 -->\n{body}\n<!-- PDF2MD:BATCH_END:0001 -->\n"
    r = validate_batch_markdown(
        md, start_page=10, end_page=10, batch_id=1, prompt_version=PROMPT_VERSION
    )
    assert r.ok, r.errors


def test_looks_like_vision_response_rejects_sidebar():
    from app.vision_transcribe.browser.deepseek_ui import looks_like_vision_response

    sidebar = "开启新对话\n今天\n" + "PDF转Markdown\n" * 20
    assert not looks_like_vision_response(sidebar, start_page=11, end_page=20)


def test_clipboard_hook_js_has_isolate_default():
    from app.vision_transcribe.browser.clipboard_interceptor import CLIPBOARD_HOOK_JS

    assert "__PDF2MD_CLIPBOARD_ISOLATE__" in CLIPBOARD_HOOK_JS
    assert "if (isolated()) return;" in CLIPBOARD_HOOK_JS


def test_repair_bold_figure_caption_inserts_marker():
    from app.vision_transcribe.figure_markers import repair_missing_figure_markers

    md = (
        "<!-- PDF2MD:PAGE:0016 -->\n\n"
        "**Figure 10.** Mean |(SHAP value)|.\n"
    )
    out = repair_missing_figure_markers(md)
    assert "PDF2MD:FIGURE:p0016:f01" in out


def test_figure_completion_rejects_bare_markers():
    from app.vision_transcribe.figure_markers import figure_completion_errors

    md = (
        "![Figure 1](images/a.png)\n\n"
        "<!-- PDF2MD:FIGURE:p0001:f01 -->\n\n"
        "**Figure 1.** Caption\n"
    )
    errs = figure_completion_errors(md)
    assert any("未替换" in e for e in errs)


def test_figure_completion_rejects_missing_images():
    from app.vision_transcribe.figure_markers import figure_completion_errors

    md = (
        "![Figure 1](images/a.png)\n\n"
        "**Figure 1.** One\n\n"
        "**Figure 2.** Two\n\n"
        "**Figure 3.** Three\n"
    )
    errs = figure_completion_errors(md)
    assert any("未全部插入" in e for e in errs)


def test_strip_orphan_marker_after_image():
    from app.vision_transcribe.figure_markers import (
        figure_completion_errors,
        strip_orphan_figure_markers_after_images,
    )

    md = (
        "![Figure 1](images/a.png)\n\n"
        "<!-- PDF2MD:FIGURE:p0001:f01 -->\n\n"
        "**Figure 1.** Caption\n"
    )
    cleaned = strip_orphan_figure_markers_after_images(md)
    assert "PDF2MD:FIGURE" not in cleaned
    assert not figure_completion_errors(cleaned)


def test_model_degeneration_detects_k_loop():
    from app.vision_transcribe.transcript_quality import has_model_degeneration

    bad = "[33] K. P. " + "K. " * 60
    assert has_model_degeneration(bad)


def test_model_degeneration_allows_real_author_initials():
    from app.vision_transcribe.transcript_quality import has_model_degeneration

    ok = (
        '[76] S. S. K. K. A. C. A. S. A. L. G. C. Silva, '
        '"Interpretable machine learning models for dropout prediction," '
        "*IEEE Trans. Learn. Technol.*, vol. 14, no. 4, pp. 500–512, 2021."
    )
    assert not has_model_degeneration(ok)

    # Course-Level 真实作者 K. K. K. R. T. E.；即使参考文献被复制多份也不该误杀
    real_kkkr = (
        '[53] M. S. Pillai, R. A. A. Kadhar, and K. K. K. R. T. E., '
        '"Classroom-based EM model for predicting student performance," '
        "Arabian J. Sci. Eng., vol. 47, no. 1, pp. 10667–10678, Dec. 2020.\n"
        '[79] M. S. Pillai, R. A. A. Kadhar, and K. K. K. R., '
        '"Classroom-based EM model for predicting student performance," '
        "Arabian J. Sci. Eng., vol. 47, no. 1, pp. 10519–10534, Jan. 2022.\n"
    )
    assert not has_model_degeneration(real_kkkr)
    assert not has_model_degeneration(real_kkkr * 6)


def test_validator_rejects_model_degeneration():
    from app.vision_transcribe.prompts import PROMPT_VERSION

    body = "<!-- PDF2MD:PAGE:0001 -->\n[33] K. P. " + "K. " * 60 + "\n"
    body += "<!-- PDF2MD:PAGE_END:0001 -->\n<!-- PDF2MD:BATCH_END:0001 -->\n"
    r = validate_batch_markdown(
        body, start_page=1, end_page=1, batch_id=1, prompt_version=PROMPT_VERSION
    )
    assert not r.ok
    assert any("模型输出退化" in e for e in r.errors)


def test_model_degeneration_detects_raw_kkkk():
    from app.vision_transcribe.transcript_quality import has_model_degeneration

    assert has_model_degeneration("end of refs " + ("k" * 80) + " more")
    assert has_model_degeneration("[33] K. P. " + ("K. K. K. " * 10))


def test_document_validator_rejects_degeneration_and_page_blowup():
    from app.vision_transcribe.document_validator import validate_document
    from app.vision_transcribe.prompts import PROMPT_VERSION

    pages = []
    for i in range(1, 3):
        pages.append(f"<!-- PDF2MD:PAGE:{i:04d} -->\n")
        pages.append("Normal academic paragraph. " * 40 + "\n")
        pages.append(f"<!-- PDF2MD:PAGE_END:{i:04d} -->\n")
    pages.append("<!-- PDF2MD:PAGE:0003 -->\n")
    pages.append("[33] K. P. " + "K. " * 80 + "\n")
    pages.append("<!-- PDF2MD:PAGE_END:0003 -->\n")
    r = validate_document(
        "".join(pages), 3, prompt_version=PROMPT_VERSION
    )
    assert not r.ok
    assert any("模型输出退化" in e or "异常过长" in e for e in r.errors)


def test_page_guard_rejects_exploded_page():
    from app.vision_transcribe.integrity.page_guard import validate_page_integrity
    from app.vision_transcribe.prompts import PROMPT_VERSION

    body = "<!-- PDF2MD:PAGE:0001 -->\n" + ("word " * 8000) + "\n<!-- PDF2MD:PAGE_END:0001 -->\n"
    errs, _warns, _sl = validate_page_integrity(
        body, start_page=1, end_page=1, batch_id=1, prompt_version=PROMPT_VERSION
    )
    assert any("异常过长" in e for e in errs)


def test_revalidate_accepted_resets_degenerated_batch(tmp_path):
    from app.vision_transcribe.batch_ingest import ingest_raw_response
    from app.vision_transcribe.config import VisionConfig
    from app.vision_transcribe.pipeline import VisionPipeline
    from app.vision_transcribe.prompts import PROMPT_VERSION

    out = tmp_path / "out"
    out.mkdir()
    m = VisionManifest()
    m.prompt_version = PROMPT_VERSION
    m.page_count = 1
    m.set_batches(
        [BatchInfo(id=1, start_page=1, end_page=1, status=BatchStatus.ACCEPTED.value)]
    )
    save_manifest(out, m)
    ingest_raw_response(
        out,
        1,
        "<!-- PDF2MD:PAGE:0001 -->\n[33] K. P. " + "K. " * 60
        + "\n<!-- PDF2MD:PAGE_END:0001 -->\n",
    )
    pipe = VisionPipeline(tmp_path / "fake.pdf", out, VisionConfig())
    pipe.manifest = m
    n = pipe._revalidate_accepted_batches(m)
    assert n == 1
    assert m.get_batches()[0].status == BatchStatus.PENDING.value


def test_plan_batch_recovery_degeneration_full_batch():
    from app.vision_transcribe.recovery.planner import plan_batch_recovery

    action, _pages = plan_batch_recovery(
        errors=["模型输出退化（连续重复字符/作者缩写循环），请开启新对话后重试本批次"],
        recopy_tried=False,
    )
    assert action == "full_batch"


def test_plan_batch_recovery_skips_retried_pages():
    from app.vision_transcribe.recovery.planner import plan_batch_recovery

    action, pages = plan_batch_recovery(
        errors=[
            "PAGE 0013 过短（273 字，期望 ≥280）",
            "PAGE 0016 过短（145 字，期望 ≥280）",
        ],
        recopy_tried=True,
        page_retry_pages={13},
    )
    assert action == "page_retry"
    assert pages == [16]


def test_recovery_planner_recopy():
    from app.vision_transcribe.recovery.planner import suggest_recovery
    from app.vision_transcribe.recovery.taxonomy import CLIPBOARD_TRUNCATED

    assert suggest_recovery(CLIPBOARD_TRUNCATED) == "recopy"


def test_replace_page_in_batch():
    from app.vision_transcribe.capture.page_merge import replace_page_in_batch

    md = (
        "<!-- PDF2MD:PAGE:0001 -->\nalpha\n"
        "<!-- PDF2MD:PAGE:0002 -->\nbeta old\n"
    )
    out = replace_page_in_batch(md, 2, "<!-- PDF2MD:PAGE:0002 -->\nbeta NEW\n")
    assert "beta NEW" in out
    assert "beta old" not in out
    assert "alpha" in out


def test_plan_batch_recovery_page_retry():
    from app.vision_transcribe.recovery.planner import plan_batch_recovery

    action, pages = plan_batch_recovery(
        errors=["PAGE 0004 过短（120 字，期望 ≥280）"],
        recopy_tried=True,
        page_retry_tried=False,
    )
    assert action == "page_retry"
    assert pages == [4]


def test_plan_batch_recovery_sub_batch():
    from app.vision_transcribe.recovery.planner import plan_batch_recovery

    action, pages = plan_batch_recovery(
        errors=[
            "PAGE 0004 过短（120 字）",
            "PAGE 0005 过短（90 字）",
        ],
        recopy_tried=True,
        page_retry_tried=True,
        sub_batch_tried=False,
    )
    assert action == "sub_batch"
    assert pages == [4, 5]


def test_pick_copy_consensus_prefers_majority_longer():
    from app.vision_transcribe.capture.consensus import pick_copy_consensus

    a = "a" * 13000
    b = "b" * 15000
    _, picked, stable, _ = pick_copy_consensus(
        [("copy_api_1", a), ("copy_api_2", b), ("clipboard_1", b)]
    )
    assert stable is True
    assert len(picked) == 15000


def test_prompt_guard_fingerprint():
    from app.vision_transcribe.browser.prompt_guard import prompt_fingerprint

    t = "A" * 100 + "END"
    fp = prompt_fingerprint(t)
    assert fp["len"] == len(t)
    assert str(fp["prefix"]).startswith("AAA")


def test_content_preservation_ok():
    from app.vision_transcribe.integrity.content_preservation import (
        content_preservation_check,
    )

    raw = "alpha beta " * 500 + "<!-- PDF2MD:PAGE:0001 -->\n"
    cleaned = "alpha beta " * 500
    ok, _, stats = content_preservation_check(raw, cleaned)
    assert ok, stats


def test_diagnose_clipboard_truncated():
    from app.vision_transcribe.capture.consensus import diagnose_transport_mismatch

    assert (
        diagnose_transport_mismatch(
            copy_api_text="x" * 15000,
            clipboard_text="y" * 12000,
        )
        == "CLIPBOARD_TRUNCATED"
    )


def test_manifest_v2_record_acceptance(tmp_path):
    from app.vision_transcribe.manifest import VisionManifest, save_manifest

    out = tmp_path / "out"
    out.mkdir()
    m = VisionManifest()
    m.set_batches(
        [
            __import__(
                "app.vision_transcribe.models", fromlist=["BatchInfo"]
            ).BatchInfo(id=1, start_page=1, end_page=2),
        ]
    )
    md = (
        "<!-- PDF2MD:PAGE:0001 -->\n"
        + ("正文 " * 400)
        + "\n<!-- PDF2MD:PAGE:0002 -->\n"
        + ("更多 " * 400)
        + "\n"
    )
    m.record_batch_acceptance(
        1,
        md,
        out,
        extract_stats={"source": "dom-md", "copy_consensus_stable": True},
    )
    save_manifest(out, m)
    b = m.batches[0]
    assert b.get("pages", {}).get("1", {}).get("chars", 0) > 200
    assert b.get("confidence") == "high"
    assert b.get("extract_source") == "dom-md"


def test_manifest_v1_load_backward_compatible(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    v1 = {
        "version": 1,
        "pdf": "paper.pdf",
        "page_count": 2,
        "batches": [
            {
                "id": 1,
                "start_page": 1,
                "end_page": 2,
                "status": "accepted",
                "error": "",
            }
        ],
        "state": "ready_to_merge",
    }
    (out / ".vision").mkdir()
    (out / ".vision" / "manifest.json").write_text(
        __import__("json").dumps(v1, ensure_ascii=False),
        encoding="utf-8",
    )
    m = load_manifest(out)
    assert m is not None
    assert m.version == 1
    batches = m.get_batches()
    assert len(batches) == 1
    assert batches[0].status == BatchStatus.ACCEPTED.value


def test_middle_page_truncation_rejected():
    parts = []
    for p in range(1, 4):
        body = "正文 " * 400 if p != 2 else "短\n"
        parts.append(f"<!-- PDF2MD:PAGE:{p:04d} -->\n{body}\n")
    md = "\n".join(parts)
    r = validate_batch_markdown(md, start_page=1, end_page=3)
    assert not r.ok
    assert any("过短" in e or "0002" in e for e in r.errors)


def test_should_force_vision_rerun_defaults_complete(tmp_path):
    from app.vision_transcribe.manifest import should_force_vision_rerun

    out = tmp_path / "out"
    out.mkdir()
    m = VisionManifest()
    m.set_batches(
        [
            BatchInfo(id=1, start_page=1, end_page=5, status=BatchStatus.ACCEPTED.value),
        ]
    )
    save_manifest(out, m)
    assert should_force_vision_rerun(out, checkbox=False, task_was_done=False)
    assert should_force_vision_rerun(None, checkbox=False, task_was_done=True)
    assert not should_force_vision_rerun(None, checkbox=False, task_was_done=False)

    incomplete = tmp_path / "inc"
    incomplete.mkdir()
    m2 = VisionManifest()
    m2.set_batches(
        [
            BatchInfo(id=1, start_page=1, end_page=5, status=BatchStatus.ACCEPTED.value),
            BatchInfo(id=2, start_page=6, end_page=10, status=BatchStatus.PENDING.value),
        ]
    )
    save_manifest(incomplete, m2)
    assert not should_force_vision_rerun(incomplete, checkbox=False, task_was_done=False)
    assert should_force_vision_rerun(incomplete, checkbox=True, task_was_done=False)


def test_all_accepted_restarts_batches(tmp_path):
    from app.vision_transcribe.config import VisionConfig
    from app.vision_transcribe.pipeline import VisionPipeline

    out = tmp_path / "out"
    out.mkdir()
    m = VisionManifest()
    m.set_batches(
        [
            BatchInfo(id=1, start_page=1, end_page=5, status=BatchStatus.ACCEPTED.value),
            BatchInfo(id=2, start_page=6, end_page=10, status=BatchStatus.ACCEPTED.value),
        ]
    )
    save_manifest(out, m)
    pipe = VisionPipeline(tmp_path / "fake.pdf", out, VisionConfig())
    pipe.manifest = m
    pipe._restart_all_batches(m, reason="test")
    statuses = [b.status for b in m.get_batches()]
    assert statuses == [BatchStatus.PENDING.value, BatchStatus.PENDING.value]


def test_continue_incomplete_preserves_raw(tmp_path):
    from app.vision_transcribe.batch_ingest import ingest_raw_response
    from app.vision_transcribe.config import VisionConfig
    from app.vision_transcribe.pipeline import VisionPipeline

    out = tmp_path / "out"
    out.mkdir()
    (out / "bookfigures").mkdir()
    m = VisionManifest()
    m.set_batches(
        [
            BatchInfo(id=1, start_page=1, end_page=5, status=BatchStatus.ACCEPTED.value),
            BatchInfo(
                id=2,
                start_page=6,
                end_page=10,
                status=BatchStatus.NEEDS_RETRY.value,
                error="test",
            ),
        ]
    )
    save_manifest(out, m)
    ingest_raw_response(out, 2, "<!-- PDF2MD:PAGE:0006 -->\n" + ("x" * 8000))

    pipe = VisionPipeline(tmp_path / "fake.pdf", out, VisionConfig())
    pipe.manifest = m
    pipe._continue_incomplete_batches(m)

    b2 = {b.id: b for b in m.get_batches()}[2]
    assert b2.status == BatchStatus.NEEDS_RETRY.value
    assert read_raw_response(out, 2) is not None


def test_batch_transcript_complete_requires_all_pages():
    from app.vision_transcribe.transcript_quality import batch_transcript_complete

    partial = "<!-- PDF2MD:PAGE:0001 -->\n" + ("x" * 25_000)
    assert not batch_transcript_complete(partial, start_page=1, end_page=10)

    full = "".join(f"<!-- PDF2MD:PAGE:{p:04d} -->\n" for p in range(1, 11))
    full += "x" * 15_000
    assert batch_transcript_complete(full, start_page=1, end_page=10)


def test_wait_releases_to_copy_when_dom_dropped_page_markers():
    from app.vision_transcribe.transcript_quality import (
        batch_transcript_complete,
        wait_should_release_to_copy,
    )

    body = "Academic paragraph. " * 2000  # ~40k，无 PAGE 注释
    assert not batch_transcript_complete(body, start_page=1, end_page=10)
    assert wait_should_release_to_copy(body, start_page=1, end_page=10)
    assert not wait_should_release_to_copy("short", start_page=1, end_page=10)


def test_fatal_page_eval_error_detection():
    from app.vision_transcribe.browser.deepseek_web import DeepSeekPlaywrightAdapter

    err = Exception(
        "Page.evaluate: Target page, context or browser has been closed"
    )
    assert DeepSeekPlaywrightAdapter._is_fatal_page_eval_error(err)
    assert not DeepSeekPlaywrightAdapter._is_fatal_page_eval_error(
        Exception("timeout")
    )


def test_detect_upload_server_busy():
    from unittest.mock import MagicMock

    from app.vision_transcribe.browser.upload_guard import detect_upload_server_busy

    page = MagicMock()
    page.evaluate.return_value = {"busy": True, "sample": "服务器繁忙", "count": 3}
    busy, hint = detect_upload_server_busy(page)
    assert busy
    assert "服务器繁忙" in hint
    assert "3" in hint


def test_raise_if_upload_server_busy():
    from unittest.mock import MagicMock

    import pytest

    from app.vision_transcribe.browser.base import ServerBusyCooldownError
    from app.vision_transcribe.browser.upload_guard import raise_if_upload_server_busy

    page = MagicMock()
    page.evaluate.return_value = {"busy": True, "sample": "服务器繁忙", "count": 1}
    with pytest.raises(ServerBusyCooldownError) as ei:
        raise_if_upload_server_busy(page, cooldown_seconds=600)
    assert ei.value.cooldown_seconds == 600


def test_server_busy_from_response():
    from app.vision_transcribe.browser.base import server_busy_from_response

    exc = server_busy_from_response(
        {"ok": False, "server_busy": True, "cooldown_seconds": 600, "error": "限流"}
    )
    assert exc is not None
    assert exc.cooldown_seconds == 600
    assert "限流" in str(exc)


def test_detect_upload_server_busy_template_l2():
    from unittest.mock import MagicMock, patch

    from app.vision_transcribe.browser.upload_guard import detect_upload_server_busy

    page = MagicMock()
    page.evaluate.return_value = {"busy": False, "sample": "", "count": 0}
    with patch(
        "app.vision_transcribe.browser.deepseek_ui.is_upload_server_busy_template_visible",
        return_value=(True, "图模板 upload_server_busy"),
    ):
        busy, hint = detect_upload_server_busy(page)
    assert busy
    assert "upload_server_busy" in hint
