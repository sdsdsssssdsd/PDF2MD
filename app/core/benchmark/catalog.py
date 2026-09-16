"""Academic Gold v2 目录：suite + tags。不把分数写进 DocumentIR。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GOLD_SUITES: tuple[str, ...] = (
    "academic",
    "scan",
    "table",
    "multilingual",
    "pathological",
    "regression",
)

GOLD_TAGS: tuple[str, ...] = (
    "multi_column",
    "dense_formula",
    "inline_math",
    "complex_table",
    "scan",
    "rotated",
    "footnote",
    "equation_number",
    "figure_caption",
)


def gold_root() -> Path:
    env = (os.environ.get("PDF2MD_GOLD_ROOT") or "").strip()
    if env:
        return Path(env)
    repo = Path(__file__).resolve().parents[3]
    for candidate in (
        repo / "experiments" / "gold",
        repo / "tests" / "fixtures" / "gold",
    ):
        if (candidate / "catalog.json").is_file():
            return candidate
    return repo / "experiments" / "gold"


@dataclass(frozen=True)
class GoldCase:
    id: str
    suite: str
    tags: tuple[str, ...]
    gold_dir: Path
    fixture: Path
    page_count: int | None = None
    expect_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        root = gold_root()
        return {
            "id": self.id,
            "suite": self.suite,
            "tags": list(self.tags),
            "gold_dir": _rel(self.gold_dir, root),
            "fixture": _rel(self.fixture, root),
            "page_count": self.page_count,
            "expect_status": self.expect_status,
        }


def load_catalog(path: Path | None = None) -> list[GoldCase]:
    catalog_path = Path(path) if path is not None else gold_root() / "catalog.json"
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    root = catalog_path.parent
    cases: list[GoldCase] = []
    for raw in data.get("cases") or []:
        suite = str(raw.get("suite") or "academic")
        tags = tuple(str(t) for t in (raw.get("tags") or []) if str(t) in GOLD_TAGS)
        gold_dir = root / str(raw.get("gold_dir") or "")
        fixture = root / str(raw.get("fixture") or "")
        page_count = raw.get("page_count")
        cases.append(
            GoldCase(
                id=str(raw.get("id") or fixture.stem),
                suite=suite,
                tags=tags,
                gold_dir=gold_dir,
                fixture=fixture,
                page_count=int(page_count) if page_count is not None else None,
                expect_status=str(raw["expect_status"]) if raw.get("expect_status") else None,
            )
        )
    return cases


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)
