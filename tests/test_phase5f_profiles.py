# -*- coding: utf-8 -*-
from app.ocr.deepseek_profiles import (
    DEEPSEEK_FORMULA_PROFILE,
    DEEPSEEK_PAGE_PROFILE,
    profile_for_mode,
)


def test_formula_profile_is_fast_path():
    p = DEEPSEEK_FORMULA_PROFILE
    assert p.save_results is False
    assert p.eval_mode is True
    assert p.max_new_tokens <= 512


def test_page_profile_keeps_document_crop():
    p = DEEPSEEK_PAGE_PROFILE
    assert p.crop_mode is True
    assert p.max_new_tokens >= 1024


def test_profile_for_mode():
    assert profile_for_mode("formula").name.startswith("formula")
    assert profile_for_mode("page").name.startswith("page")
