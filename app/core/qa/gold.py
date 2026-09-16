"""Academic Gold：expectations.json 驱动同一组 QualityCheck。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.domain.document import document_from_markdown
from app.core.domain.quality import QualityReport
from app.core.qa.engine import run_unified_qa


@dataclass
class GoldExpectations:
    required_pages: list[int] = field(default_factory=list)
    max_unresolved_formulas: int = 0
    required_equation_ids: list[str] = field(default_factory=list)
    forbidden_markers: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoldExpectations:
        return cls(
            required_pages=[int(x) for x in (data.get("required_pages") or [])],
            max_unresolved_formulas=int(data.get("max_unresolved_formulas") or 0),
            required_equation_ids=[str(x) for x in (data.get("required_equation_ids") or [])],
            forbidden_markers=[str(x) for x in (data.get("forbidden_markers") or [])],
            anchors=[str(x) for x in (data.get("anchors") or [])],
        )


def load_gold_dir(gold_dir: Path) -> tuple[GoldExpectations, dict[str, Any]]:
    root = Path(gold_dir)
    raw: dict[str, Any] = {}
    exp_path = root / "expectations.json"
    if exp_path.is_file():
        raw = json.loads(exp_path.read_text(encoding="utf-8"))
    expectations = GoldExpectations.from_dict(raw)
    anchors_path = root / "anchors.json"
    if anchors_path.is_file():
        extra = json.loads(anchors_path.read_text(encoding="utf-8"))
        needles = extra.get("anchors") or extra.get("needles") or []
        if isinstance(needles, list):
            expectations.anchors = [str(x) for x in needles] or expectations.anchors
    eq_path = root / "equations.json"
    if eq_path.is_file():
        extra = json.loads(eq_path.read_text(encoding="utf-8"))
        ids = extra.get("required_equation_ids") or extra.get("ids") or []
        if isinstance(ids, list) and ids:
            expectations.required_equation_ids = [str(x) for x in ids]
    formulas_path = root / "formulas.json"
    if formulas_path.is_file():
        extra = json.loads(formulas_path.read_text(encoding="utf-8"))
        if extra.get("max_unresolved_formulas") is not None:
            expectations.max_unresolved_formulas = int(extra["max_unresolved_formulas"])
        markers = extra.get("forbidden_markers") or []
        if isinstance(markers, list) and markers:
            expectations.forbidden_markers = [str(x) for x in markers]
    return expectations, raw


def evaluate_gold(
    markdown: str,
    gold_dir: Path | None = None,
    *,
    expectations: GoldExpectations | None = None,
    page_count: int | None = None,
    context: dict[str, Any] | None = None,
) -> QualityReport:
    exp = expectations
    if exp is None and gold_dir is not None:
        exp, _ = load_gold_dir(gold_dir)
    exp = exp or GoldExpectations()
    document = document_from_markdown(markdown, provider="gold")
    return run_unified_qa(
        markdown,
        document=document,
        page_count=page_count,
        required_pages=exp.required_pages or None,
        required_equation_ids=exp.required_equation_ids or None,
        anchors=exp.anchors or None,
        forbidden_markers=exp.forbidden_markers
        or ["formula-not-decoded"],
        max_unresolved_formulas=exp.max_unresolved_formulas,
        context=context,
        evaluator="academic_gold",
    )
