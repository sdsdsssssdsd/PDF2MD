# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from app.formula.gold_schema import FormulaGoldRecord, validate_gold_record
from app.utils.paths import APP_ROOT, K5_CROPS_DIR


def test_o018_verified_seed_has_five_crops():
    gold = APP_ROOT / "benchmarks" / "gold" / "o018_verified.jsonl"
    if not gold.is_file():
        return
    rows = []
    for line in gold.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        assert validate_gold_record(obj) == []
        rec = FormulaGoldRecord.from_dict(obj)
        assert rec.verified
        assert rec.equation_number in {"1", "4", "5", "6", "7"}
        if rec.equation_number == "1":
            assert "Var" in rec.gold_latex_raw
        assert not rec.crop_path.startswith("tight/"), "production crop_path must stay production"
        crop = K5_CROPS_DIR / rec.crop_path
        assert crop.is_file(), rec.crop_path
        if rec.crop_path_tight:
            tight = K5_CROPS_DIR / rec.crop_path_tight
            assert tight.is_file(), rec.crop_path_tight
            assert rec.crop_path_tight.startswith("tight/")
        rows.append(rec)
    assert len(rows) == 5


def test_academic100_inventory_split():
    man = APP_ROOT / "benchmarks" / "manifests" / "academic100_regression_v1.json"
    if not man.is_file():
        return
    data = json.loads(man.read_text(encoding="utf-8"))
    assert data["n"] == 100
    assert data["english"] == 50
    assert data["chinese"] == 50
    assert data["do_not_train"] is True


def test_harvest_display_is_unverified_and_bilingual():
    path = APP_ROOT / "benchmarks" / "gold" / "harvest_display.jsonl"
    if not path.is_file():
        return
    rows = []
    zh = en = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        rec = FormulaGoldRecord.from_dict(obj)
        assert "harvest_display" in rec.tags or "harvest_display" in rec.notes
        if rec.verified:
            assert rec.gold_latex_raw.strip()
            assert "\\tag" not in rec.gold_latex_raw
        else:
            assert not rec.gold_latex_raw.strip()
        if rec.language == "zh":
            zh += 1
        else:
            en += 1
        rows.append(rec)
    assert len(rows) >= 10
    assert zh >= 1
    assert en >= 1


def test_human_verified_v2_is_complete_crop_only():
    gold = APP_ROOT / "benchmarks" / "gold" / "human_verified_v2.jsonl"
    if not gold.is_file():
        return
    rows = []
    for line in gold.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        assert validate_gold_record(obj) == []
        rec = FormulaGoldRecord.from_dict(obj)
        assert rec.verified
        assert rec.gold_latex_raw.strip()
        assert "\\tag" not in rec.gold_latex_raw
        assert not rec.crop_path.startswith("tight/")
        rows.append(rec)
    assert len(rows) >= 3


def test_preserve_verified_fields_survives_reexport(tmp_path: Path):
    from app.formula.gold_crop import preserve_verified_fields

    existing = tmp_path / "sk.jsonl"
    existing.write_text(
        json.dumps(
            {
                "id": "x",
                "verified": True,
                "gold_latex_raw": r"z=(x-\mu)/\sigma",
                "gold_latex_canonical": "z=(x-\\mu)/\\sigma",
                "notes": "human_from_tight_crop",
                "tags": ["human_verified"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fresh = [{"id": "x", "verified": False, "gold_latex_raw": "", "notes": "skeleton_only"}]
    out = preserve_verified_fields(fresh, existing)
    assert out[0]["verified"] is True
    assert out[0]["gold_latex_raw"] == r"z=(x-\mu)/\sigma"
