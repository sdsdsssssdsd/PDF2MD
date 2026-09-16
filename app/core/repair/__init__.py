"""Markdown 层 RepairRule 登记。IR 修复见 app.core.repair.ir；不拆走硬规则函数。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable

from app.utils.md_postprocess import (
    collapse_extra_blank_lines,
    ensure_figure_table_separation,
    normalize_display_math_multiline,
    normalize_heading_spacing,
)

RepairFn = Callable[[str], str]


@dataclass(frozen=True)
class RepairRule:
    id: str
    phase: str
    deterministic: bool
    enabled: bool
    fn: RepairFn


@dataclass(frozen=True)
class RepairTrace:
    rule_id: str
    before_hash: str
    after_hash: str
    changed: bool


MARKDOWN_RULES: tuple[RepairRule, ...] = (
    RepairRule(
        id="figure_table_separation",
        phase="markdown",
        deterministic=True,
        enabled=True,
        fn=ensure_figure_table_separation,
    ),
    RepairRule(
        id="display_math_multiline",
        phase="markdown",
        deterministic=True,
        enabled=True,
        fn=normalize_display_math_multiline,
    ),
    RepairRule(
        id="heading_spacing",
        phase="markdown",
        deterministic=True,
        enabled=True,
        fn=normalize_heading_spacing,
    ),
    RepairRule(
        id="extra_blank_lines",
        phase="markdown",
        deterministic=True,
        enabled=True,
        fn=collapse_extra_blank_lines,
    ),
    RepairRule(
        id="legacy_correction",
        phase="legacy_correction",
        deterministic=False,
        enabled=False,
        fn=lambda text: text or "",
    ),
)


def iter_rules(*, phase: str | None = None, enabled_only: bool = True) -> tuple[RepairRule, ...]:
    rules = MARKDOWN_RULES
    if phase:
        rules = tuple(r for r in rules if r.phase == phase)
    if enabled_only:
        rules = tuple(r for r in rules if r.enabled)
    return rules


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def apply_markdown_rules(text: str) -> str:
    out, _traces = apply_markdown_rules_traced(text)
    return out


def apply_markdown_rules_traced(text: str) -> tuple[str, tuple[RepairTrace, ...]]:
    out = text or ""
    traces: list[RepairTrace] = []
    for rule in iter_rules(phase="markdown"):
        before = out
        out = rule.fn(out)
        traces.append(
            RepairTrace(
                rule_id=rule.id,
                before_hash=_sha(before),
                after_hash=_sha(out),
                changed=out != before,
            )
        )
    return out, tuple(traces)


def rule_is_idempotent(rule: RepairRule, text: str) -> bool:
    once = rule.fn(text or "")
    return rule.fn(once) == once
