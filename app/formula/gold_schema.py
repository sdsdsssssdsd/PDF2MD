# -*- coding: utf-8 -*-
"""Academic100 Gold Core 记录格式（k5 §七）。编号与公式内容分离。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Difficulty = Literal["easy", "medium", "hard", "extreme"]
SplitName = Literal["regression", "hard200", "holdout"]


@dataclass
class FormulaGoldRecord:
    id: str
    pdf_id: str
    language: str
    page: int
    bbox_pdf: list[float] = field(default_factory=list)
    crop_path: str = ""
    bbox_pdf_tight: list[float] = field(default_factory=list)
    crop_path_tight: str = ""
    crop_quality: list[str] = field(default_factory=list)
    equation_number: str = ""
    gold_latex_raw: str = ""
    gold_latex_canonical: str = ""
    difficulty: str = "medium"
    tags: list[str] = field(default_factory=list)
    split: str = "regression"
    verified: bool = False
    notes: str = ""
    machine_pred: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> FormulaGoldRecord:
        bbox = row.get("bbox_pdf") or []
        if not isinstance(bbox, list):
            bbox = []
        tags = row.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        tight = row.get("bbox_pdf_tight") or []
        if not isinstance(tight, list):
            tight = []
        quality = row.get("crop_quality") or []
        if not isinstance(quality, list):
            quality = []
        return cls(
            id=str(row.get("id") or ""),
            pdf_id=str(row.get("pdf_id") or ""),
            language=str(row.get("language") or ""),
            page=int(row.get("page") or 0),
            bbox_pdf=[float(x) for x in bbox[:4]],
            crop_path=str(row.get("crop_path") or ""),
            bbox_pdf_tight=[float(x) for x in tight[:4]],
            crop_path_tight=str(row.get("crop_path_tight") or ""),
            crop_quality=[str(t) for t in quality],
            equation_number=str(row.get("equation_number") or ""),
            gold_latex_raw=str(row.get("gold_latex_raw") or ""),
            gold_latex_canonical=str(row.get("gold_latex_canonical") or ""),
            difficulty=str(row.get("difficulty") or "medium"),
            tags=[str(t) for t in tags],
            split=str(row.get("split") or "regression"),
            verified=bool(row.get("verified")),
            notes=str(row.get("notes") or ""),
            machine_pred=str(row.get("machine_pred") or ""),
        )


def validate_gold_record(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    rec = FormulaGoldRecord.from_dict(row)
    if not rec.id:
        issues.append("missing_id")
    if not rec.pdf_id:
        issues.append("missing_pdf_id")
    if rec.page < 0:
        issues.append("missing_page")
    if rec.gold_latex_raw.strip() and "\\tag" in rec.gold_latex_raw:
        issues.append("gold_must_not_contain_tag")
    if rec.equation_number and rec.equation_number in (rec.gold_latex_raw or ""):
        # 编号允许偶然出现在公式里，但禁止整段只是 (12)
        if rec.gold_latex_raw.strip() in {rec.equation_number, f"({rec.equation_number})"}:
            issues.append("gold_is_equation_number_only")
    if rec.verified and not rec.gold_latex_raw.strip():
        issues.append("verified_without_latex")
    return issues
