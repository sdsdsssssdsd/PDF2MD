"""R14：IR-first repair + legacy 收敛。"""
from __future__ import annotations

import warnings

from app.core.domain.document import (
    BLOCK_FIGURE,
    BLOCK_TABLE,
    BLOCK_TEXT,
    BlockIR,
    DocumentIR,
)
from app.core.repair.ir import apply_ir_rules, ir_rules_are_idempotent
from app.formula.backends import BACKEND_MODE_K5_SPECIALIST, is_specialist_backend
from app.formula.config import FormulaConfig


def test_ir_repair_is_idempotent_and_associates_caption():
    doc = DocumentIR(
        blocks=[
            BlockIR(id="f1", type=BLOCK_FIGURE, content="![x](a.png)", page=1),
            BlockIR(id="c1", type=BLOCK_TEXT, content="Figure 1. Ablation.", page=1),
            BlockIR(id="c1dup", type=BLOCK_TEXT, content="Figure 1. Ablation.", page=1),
            BlockIR(
                id="t1",
                type=BLOCK_TABLE,
                content="| a | b |\n| --- | --- |\n| 1 | 2 | 3 |",
                page=1,
            ),
        ]
    )
    once, traces = apply_ir_rules(doc)
    ids = {t.rule_id for t in traces}
    assert "duplicate_block" in ids
    assert "caption_association" in ids
    assert any(r.kind == "caption_of" for r in once.relations)
    assert any(b.id == "t1" and b.attributes.get("table_inconsistent") for b in once.blocks)
    assert [b.id for b in once.blocks] == ["f1", "c1", "t1"]
    assert ir_rules_are_idempotent(once) is True
    twice, _ = apply_ir_rules(once)
    assert once.to_json() == twice.to_json()


def test_k_flags_have_semantic_names():
    assert is_specialist_backend(BACKEND_MODE_K5_SPECIALIST) is True
    assert is_specialist_backend("specialist") is True
    assert is_specialist_backend("legacy_deepseek") is False
    cfg = FormulaConfig()
    assert cfg.specialist_shadow_only == cfg.k5_shadow_only


def test_correction_is_legacy_and_vision_api_compat_warns():
    from app.correction import LEGACY, PHASE

    assert LEGACY is True
    assert PHASE == "legacy_correction"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import importlib

        import app.vision_api.compatibility as compat

        importlib.reload(compat)
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
