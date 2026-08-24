# -*- coding: utf-8 -*-
from __future__ import annotations

from app.ui.task_table_markdown import format_task_table_markdown


def test_format_task_table_markdown_basic():
    md = format_task_table_markdown(
        ["文件", "状态"],
        [["a.pdf", "完成"], ["b|x.pdf", "失败"]],
    )
    assert md.startswith("| 文件 | 状态 |")
    assert "b\\|x.pdf" in md
    assert md.endswith("\n")


def test_empty_headers():
    assert format_task_table_markdown([], []) == ""
