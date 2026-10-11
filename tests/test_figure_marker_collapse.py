"""FIGURE 占位符合并：同一张图的多个子图被模型拆成多个占位符（真实病例回归）。

病例：[01]_Kuzilek2017 第 7 页整页只有一张 Figure 5，是 a–f 六个子图，模型连着写了
6 个占位符；Docling 那一页只导出 1 张图 → 3 个占位符无图可插 → 完成门判整篇失败。
"""
from __future__ import annotations

from app.vision_transcribe.figure_markers import (
    adjacent_figure_merge_notes,
    collapse_adjacent_figure_markers,
    count_figure_captions,
    figure_completion_errors,
)

# 真实病例片段（batch_0002 原文开头）：同一页 6 个占位符紧挨着，中间没有任何正文
_REAL_PAGE7 = """<!-- PDF2MD:PAGE:0007 -->
<!-- PDF2MD:FIGURE:p0007:f01 -->
<!-- PDF2MD:FIGURE:p0007:f02 -->
<!-- PDF2MD:FIGURE:p0007:f03 -->
<!-- PDF2MD:FIGURE:p0007:f04 -->
<!-- PDF2MD:FIGURE:p0007:f05 -->
<!-- PDF2MD:FIGURE:p0007:f06 -->
**Figure 5.** Comparison of attributes of OULAD (red) and testing data (blue).
"""

# 同一篇第 3 页：两个占位符中间夹着正文 → 确实是两张图，不能合并
_REAL_PAGE3 = """<!-- PDF2MD:PAGE:0003 -->
<!-- PDF2MD:FIGURE:p0003:f01 -->
**Figure 1.** Distribution of the module presentations.

Some body text in between.

<!-- PDF2MD:FIGURE:p0003:f02 -->
**Figure 2.** Another real figure.
"""


def test_adjacent_markers_are_collapsed_to_one():
    out = collapse_adjacent_figure_markers(_REAL_PAGE7)
    assert out.count("PDF2MD:FIGURE") == 1
    assert "p0007:f01" in out  # 保留第一个，位置不变
    assert "**Figure 5.**" in out  # 题注不受影响


def test_markers_separated_by_text_are_kept():
    out = collapse_adjacent_figure_markers(_REAL_PAGE3)
    assert "p0003:f01" in out and "p0003:f02" in out
    assert out == _REAL_PAGE3  # 原样返回


def test_blank_lines_do_not_break_a_run():
    md = (
        "<!-- PDF2MD:FIGURE:p0012:f01 -->\n\n\n"
        "<!-- PDF2MD:FIGURE:p0012:f02 -->\n\ntext\n"
    )
    out = collapse_adjacent_figure_markers(md)
    assert out.count("PDF2MD:FIGURE") == 1
    assert "text" in out


def test_different_pages_are_never_merged():
    md = "<!-- PDF2MD:FIGURE:p0005:f01 -->\n<!-- PDF2MD:FIGURE:p0006:f01 -->\n"
    out = collapse_adjacent_figure_markers(md)
    assert out.count("PDF2MD:FIGURE") == 2


def test_collapse_is_idempotent_and_empty_safe():
    once = collapse_adjacent_figure_markers(_REAL_PAGE7)
    assert collapse_adjacent_figure_markers(once) == once
    assert collapse_adjacent_figure_markers("") == ""
    assert collapse_adjacent_figure_markers("no markers here") == "no markers here"


def test_merge_notes_explain_what_happened():
    notes = adjacent_figure_merge_notes(_REAL_PAGE7)
    assert len(notes) == 1
    assert "第 7 页" in notes[0] and "6 个" in notes[0] and "p0007:f01" in notes[0]
    assert adjacent_figure_merge_notes(_REAL_PAGE3) == []


def test_completion_gate_passes_once_markers_are_collapsed():
    """完成门必须放行：合并后占位符全部能换成图片、图题数量也不再虚高。"""
    collapsed = collapse_adjacent_figure_markers(_REAL_PAGE7)
    # 模拟 Docling 只给这一页 1 张图：写回后全文只剩 1 张图 + 1 个图题
    written = collapsed.replace(
        "<!-- PDF2MD:FIGURE:p0007:f01 -->",
        "![Figure](images/image_5_[01]_Kuzilek2017.png)",
    )
    assert count_figure_captions(written) == [5]
    assert figure_completion_errors(written) == []


def test_uncollapsed_document_would_fail_the_gate():
    """反向验证：不合并时，3 个占位符无图可插 → 完成门报错（修复前的现象）。"""
    written = _REAL_PAGE7.replace(
        "<!-- PDF2MD:FIGURE:p0007:f01 -->",
        "![Figure](images/image_5_[01]_Kuzilek2017.png)",
    )
    errors = figure_completion_errors(written)
    assert any("FIGURE 占位符" in e for e in errors)
