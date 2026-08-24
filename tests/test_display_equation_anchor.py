# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.session import is_display_equation_number


def test_inline_reference_not_display_number():
    page_w = 612.0
    mid = page_w * 0.5
    # 左栏正文行内 "similarity (1)"
    assert not is_display_equation_number(page_w, mid * 0.35, mid * 0.42)
    # 右栏展示编号 (5)
    assert is_display_equation_number(page_w, page_w * 0.78, page_w * 0.82)


def test_left_column_display_number_at_margin():
    page_w = 612.0
    mid = page_w * 0.5
    assert is_display_equation_number(page_w, mid - 40, mid - 4)
