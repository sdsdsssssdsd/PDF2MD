"""Analyzer-only tests (detect, do not repair)."""
from __future__ import annotations

from app.repair.analyzer import analyze_markdown
from app.repair.models import IssueType


def _types(md: str) -> set[str]:
    return {i.type.value for i in analyze_markdown(md)}


def test_detect_decimal_split():
    issues = analyze_markdown("score 0 . 5 at cutoff")
    assert any(i.type == IssueType.DECIMAL_SPLIT for i in issues)


def test_detect_hat_corruption():
    issues = analyze_markdown("use ˆ p as probability")
    assert any(i.type == IssueType.HAT_CORRUPTION for i in issues)


def test_detect_detached_script():
    issues = analyze_markdown("where x ( t ) i is early")
    assert any(i.type == IssueType.DETACHED_SCRIPT for i in issues)


def test_prose_in_math_inside_span_not_between_spans():
    # Adjacent math spans should not false-positive on text between them
    md = "For each $t \\in T$ , we construct $D(t)$."
    issues = [i for i in analyze_markdown(md) if i.type == IssueType.PROSE_IN_MATH]
    assert issues == []


def test_suspicious_operator_subscript():
    md = r"bad $t \in_{T}$ pattern"
    assert IssueType.SUSPICIOUS_SUBSCRIPT.value in _types(md)
