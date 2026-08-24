# -*- coding: utf-8 -*-
"""主窗口任务表 → Markdown 表格（一键复制）。"""
from __future__ import annotations


def _md_cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def format_task_table_markdown(
    headers: list[str],
    rows: list[list[str]],
) -> str:
    """生成 Markdown 表格；``headers`` / ``rows`` 列数须一致。"""
    if not headers:
        return ""
    n = len(headers)
    lines = [
        "| " + " | ".join(_md_cell(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in range(n)) + " |",
    ]
    for row in rows:
        cells = list(row[:n])
        while len(cells) < n:
            cells.append("")
        lines.append("| " + " | ".join(_md_cell(c) for c in cells) + " |")
    return "\n".join(lines) + "\n"
