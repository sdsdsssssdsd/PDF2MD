# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.consensus import dual_model_consensus
from app.formula.risk import assess_formula_risk


def test_consensus_accept_canonical():
    r = dual_model_consensus(r"\frac{a}{b}", r"$$\dfrac{a}{b}$$")
    assert r.decision == "ACCEPT"


def test_consensus_visual_over():
    r = dual_model_consensus(r"\frac{a}{b}", r"{a \over b}")
    assert r.decision in {"ACCEPT", "ACCEPT_VISUAL"}


def test_consensus_disagree():
    r = dual_model_consensus(r"x_i", r"x_l")
    assert r.decision == "DISAGREE"


def test_consensus_incomplete():
    r = dual_model_consensus("", r"x")
    assert r.decision == "INCOMPLETE"


def test_risk_abstain_on_disagree():
    a = assess_formula_risk(
        latex=r"x_i",
        page=1,
        bbox=(10, 10, 80, 40),
        peer_latex=r"x_l",
        require_consensus=True,
    )
    assert a.decision == "abstain"
    assert a.risk == "high"


def test_risk_accept_when_layers_ok_no_peer():
    a = assess_formula_risk(
        latex=r"E=mc^{2}",
        page=1,
        bbox=(10, 10, 80, 40),
        require_consensus=False,
    )
    assert a.decision == "accept"
    assert a.risk == "low"


def test_risk_abstain_missing_bbox():
    a = assess_formula_risk(latex=r"E=mc^{2}", page=1, bbox=None)
    assert a.decision == "abstain"
