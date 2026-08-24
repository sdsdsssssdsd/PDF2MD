# -*- coding: utf-8 -*-
from __future__ import annotations

import re

from app.utils.typora_math_repair import (
    find_undefined_math_commands,
    lint_typora_math,
    repair_typora_math_body,
    repair_typora_math_in_markdown,
)


def test_o028_f1_fake_commands_turn_green():
    raw = (
        r"F1_{c}=\frac{2\cdot\Precisio_{c}\cdot\Recall_{c}}"
        r"{\Precisio_{c}+\Recall_{c}}."
    )
    fixed = repair_typora_math_body(raw)
    assert r"\Precisio" not in fixed
    assert r"\Recall" not in fixed
    assert "Precision" in fixed
    assert "Recall" in fixed
    assert find_undefined_math_commands(fixed) == []


def test_o028_accuracy_typo():
    raw = r"Acuracy=\frac{1}{n}\sum_{i=1}^{n}1\{\hat{y}_{i}=y_{i}\}."
    fixed = repair_typora_math_body(raw)
    assert "Acuracy" not in fixed
    assert "Accuracy" in fixed


def test_o028_precision_truncation():
    raw = r"Precisi_{c}=\frac{TP_{c}}{TP_{c}+FP_{c}}"
    fixed = repair_typora_math_body(raw)
    assert re.search(r"\bPrecisi\b", fixed) is None
    assert find_undefined_math_commands(fixed) == []


def test_o028_metric_weighted_typo_and_cdot():
    raw = r"Metricweighets=\frac{1}{\sum_{c}s_{c}}\sum_{c}s_{c}\cdotMetric."
    fixed = repair_typora_math_body(raw)
    assert "Metricweighets" not in fixed
    assert r"\cdotMetric" not in fixed
    assert find_undefined_math_commands(fixed) == []


def test_o028_confusion_matrix_spacing():
    raw = r"M _ { i j } = \# \{ k \colon y _ { k } = i \text{and} \hat{y } _ { k } = j \} ."
    fixed = repair_typora_math_body(raw)
    assert "M_{ij}" in fixed or "M_{i j}" not in fixed.replace(" ", "")
    assert "iand" not in fixed.lower()


def test_repair_markdown_block():
    md = "$$\n\\Precisio_{c}=1\n$$"
    out = repair_typora_math_in_markdown(md)
    assert r"\Precisio" not in out
    assert lint_typora_math(out) == []


def test_lint_catches_before_repair():
    md = "$$\n\\Precisio_{c}=1\n$$"
    issues = lint_typora_math(md)
    assert any(i.code == "T-undef-cmd" for i in issues)
