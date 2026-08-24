# -*- coding: utf-8 -*-
"""Phase 5H：Equation Identity Resolver v2 反例与 O-018 锁。"""
from __future__ import annotations

from app.formula.deepseek_production_pass import stable_candidate_id
from app.formula.equation_identity import (
    bind_equation_identities,
    classify_equation_mention,
    iter_equation_mentions,
    resolve_equation_identities,
    safe_eq_id_token,
)
from app.formula.equation_identity_gate import find_identity_content_conflicts
from app.formula.types import FormulaCandidate
from app.formula.writeback import RecoveryWritebackItem


def test_stable_id_uses_bound_equation_number():
    cand = FormulaCandidate(
        text=r"\quad",
        page=7,
        equation_number="6",
        display_mode="display",
    )
    assert stable_candidate_id(cand, seq=1) == "page7_eq6"


def test_stable_id_unresolved_not_steal_context_eq():
    cand = FormulaCandidate(
        text=r"\quad",
        page=7,
        equation_number="",
        context_before="TPR using Eq. (6), against FPR using Eq. (7)",
        display_mode="display",
    )
    assert stable_candidate_id(cand, seq=2) == "page7_eqi2"


def test_o018_eq6_eq7_identity_binding():
    md = (
        "TPR using Eq. (6), against FPR using Eq. (7) at thresholds.\n\n"
        "<!-- formula-not-decoded -->\n\n"
        "<!-- formula-not-decoded -->\n"
    )
    ids = bind_equation_identities(md)
    slots = sorted(ids.keys())
    assert len(slots) == 2
    assert ids[slots[0]].equation_number == "6"
    assert ids[slots[1]].equation_number == "7"
    assert ids[slots[0]].confidence >= 0.75
    assert ids[slots[0]].source in {"prose_definition", "local_order"}


def test_tpr_eq6_fpr_eq7_comma_list_binds():
    """k2：TPR Eq. (6), FPR Eq. (7). 同句列举须绑定连续槽。"""
    md = (
        "TPR Eq. (6), FPR Eq. (7).\n\n"
        "<!-- formula-not-decoded -->\n\n"
        "<!-- formula-not-decoded -->\n"
    )
    ids = bind_equation_identities(md)
    nums = [ids[k].equation_number for k in sorted(ids)]
    assert nums == ["6", "7"]


def test_reference_unlike_does_not_bind_next_formula():
    md = (
        "Unlike Eq. (2), the proposed model improves recall.\n\n"
        "The recall is calculated as:\n"
        "<!-- formula-not-decoded -->\n"
    )
    ids = bind_equation_identities(md)
    # Eq.(2) 是回指，不应绑到后面的新公式
    assert ids == {} or all(i.equation_number != "2" for i in ids.values())


def test_defining_colon_binds():
    md = "Recall can be calculated using Eq. (4):\n<!-- formula-not-decoded -->\n"
    ids = bind_equation_identities(md)
    assert len(ids) == 1
    assert list(ids.values())[0].equation_number == "4"


def test_sequential_eq_one_each():
    md = (
        "defined by Eq. (1):\n<!-- formula-not-decoded -->\n"
        "using Eq. (2):\n<!-- formula-not-decoded -->\n"
    )
    ids = bind_equation_identities(md)
    nums = [ids[k].equation_number for k in sorted(ids)]
    assert nums == ["1", "2"]


def test_one_to_one_no_duplicate_labels():
    md = (
        "defined by Eq. (3):\n<!-- formula-not-decoded -->\n"
        "<!-- formula-not-decoded -->\n"
    )
    ids = bind_equation_identities(md)
    # 只有一个 defining mention → 最多绑一槽为 3，另一槽 unresolved
    nums = [i.equation_number for i in ids.values()]
    assert nums.count("3") <= 1
    assert len(ids) <= 1


def test_appendix_and_letter_labels():
    md = (
        "given by Eq. (A.1):\n<!-- formula-not-decoded -->\n"
        "expressed by Eq. (4a):\n<!-- formula-not-decoded -->\n"
    )
    ids = bind_equation_identities(md)
    nums = {i.equation_number for i in ids.values()}
    assert "A.1" in nums
    assert "4a" in nums


def test_safe_eq_id_token():
    assert safe_eq_id_token("A.1") == "A.1"
    assert safe_eq_id_token("4a") == "4a"
    assert stable_candidate_id(
        FormulaCandidate(text="x", page=7, equation_number="A.1"), seq=1
    ) == "page7_eqA.1"


def test_mention_classifier():
    assert (
        classify_equation_mention(before="Unlike ", after=", the model", raw="Eq. (2)")
        == "reference"
    )
    assert (
        classify_equation_mention(
            before="calculated using ", after=":\n", raw="Eq. (4)"
        )
        == "defining"
    )


def test_pdf_printed_label_mock():
    class _Page:
        class _R:
            width = 600.0

        rect = _R()

        def get_text(self, mode: str):
            assert mode == "words"
            # 左栏公式；编号在公式右侧、仍在左栏内
            return [
                (260.0, 105.0, 280.0, 120.0, "(7)", 0, 0, 0),
            ]

    from app.formula.equation_identity import find_pdf_printed_label

    hit = find_pdf_printed_label(_Page(), (40.0, 100.0, 250.0, 130.0))
    assert hit is not None
    assert hit[0] == "7"


def test_twocolumn_does_not_steal_other_column_label():
    class _Page:
        class _R:
            width = 600.0

        rect = _R()

        def get_text(self, mode: str):
            # left formula; right column has (9) — must not bind
            return [
                (520.0, 105.0, 540.0, 120.0, "(9)", 0, 0, 0),
            ]

    from app.formula.equation_identity import find_pdf_printed_label

    # left-column formula
    hit = find_pdf_printed_label(_Page(), (40.0, 100.0, 250.0, 130.0))
    assert hit is None


def test_identity_content_conflict_o018_lock():
    items = [
        RecoveryWritebackItem(
            candidate_id="page7_eq6",
            recovered_latex=r"FPR=\frac{FP}{FP+TN}",
            gate_accepted=True,
            would_replace=True,
            page=7,
        ),
        RecoveryWritebackItem(
            candidate_id="page7_eq7",
            recovered_latex=r"FPR=\frac{FP}{FP+TN}",
            gate_accepted=True,
            would_replace=True,
            page=7,
        ),
    ]
    c = find_identity_content_conflicts(items)
    assert "page7_eq6" in c


def test_unresolved_when_no_evidence():
    md = "Some prose without numbers.\n<!-- formula-not-decoded -->\n"
    ids, qa = resolve_equation_identities(md)
    assert ids == {}
    assert qa.identity_unresolved == 1


def test_mentions_split_defining_reference():
    md = "Unlike Eq. (2), see Eq. (3). Defined by Eq. (5):\n"
    ms = iter_equation_mentions(md)
    kinds = {m.label: m.kind for m in ms}
    assert kinds.get("2") == "reference"
    assert kinds.get("5") == "defining"
