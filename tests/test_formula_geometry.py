# -*- coding: utf-8 -*-
"""k3 Round-1 geometry 单测。"""
from __future__ import annotations

from app.formula.geometry import (
    formula_band_from_number_v2,
    formula_bbox_from_anchor_v2,
)
from app.formula.session import EquationAnchor, EquationAnchorIndex, formula_band_from_number


def test_v2_display_taller_than_v1_narrow():
    nb = (527.0, 512.0, 540.0, 524.0)
    v1 = formula_band_from_number(595.0, 842.0, nb)
    v2 = formula_band_from_number_v2(595.0, 842.0, nb, level="display")
    assert (v1[3] - v1[1]) <= 52.0
    assert (v2[3] - v2[1]) >= 54.0


def test_v2_multiline_can_expand_further():
    nb = (527.0, 512.0, 540.0, 524.0)
    multi = formula_band_from_number_v2(595.0, 842.0, nb, level="multiline")
    display = formula_band_from_number_v2(595.0, 842.0, nb, level="display")
    assert (multi[3] - multi[1]) >= (display[3] - display[1])


def test_v2_stays_in_column():
    nb = (527.0, 512.0, 540.0, 524.0)
    x0, y0, x1, y1 = formula_band_from_number_v2(595.0, 842.0, nb)
    assert x0 >= 280.0
    assert y0 < 512.0 < y1


def test_voronoi_respects_neighbor_anchors():
    idx = EquationAnchorIndex()
    idx.add("6", EquationAnchor(page=8, bbox=(520.0, 400.0, 532.0, 412.0), x_ratio=0.87))
    idx.add("7", EquationAnchor(page=8, bbox=(520.0, 500.0, 532.0, 512.0), x_ratio=0.87))
    anchor = idx.lookup("7")
    assert anchor is not None
    box = formula_bbox_from_anchor_v2(595.0, 842.0, anchor, idx, level="display")
    height = box[3] - box[1]
    assert 35.0 <= height <= 70.0
    assert box[1] > 412.0


def test_v1_fallback_when_band_too_small():
    nb = (100.0, 10.0, 112.0, 18.0)
    box = formula_band_from_number_v2(400.0, 500.0, nb, level="tight")
    assert box[3] > box[1]


def test_crop_bbox_suspicious_respects_crop_class():
    from app.formula.geometry import crop_bbox_suspicious

    wide = (18.0, 100.0, 300.0, 160.0)
    assert crop_bbox_suspicious(None, 0, wide, crop_class="likely_prose")
    assert not crop_bbox_suspicious(None, 0, wide, crop_class="likely_formula")


def test_tall_crop_is_suspicious():
    from app.formula.geometry import crop_bbox_suspicious

    tall = (18.0, 100.0, 300.0, 260.0)
    assert crop_bbox_suspicious(None, 0, tall)


def test_ocr_raw_is_prose_ref():
    from app.ocr.extractor import ocr_raw_is_prose_ref

    assert ocr_raw_is_prose_ref("<|ref|>text<|/ref|><|det|>[[0,0,1,1]]<|/det|>\nhello")
    assert not ocr_raw_is_prose_ref("<|ref|>equation<|/ref|>\n\\[x=1\\]")


def test_bridge_query_pairs_keep_hyphen_phrases():
    from app.formula.geometry import _bridge_query_pairs

    before = (
        "...as given by the discrete-time process:"
    )
    after = "The time t is denoted the Markov time and is distinct"
    pairs = _bridge_query_pairs(before, after)
    flat = " | ".join(f"{a}->{b}" for a, b in pairs)
    assert "discrete-time" in flat
    assert "Markov time" in flat


def test_bridge_query_pairs_membership_matrix():
    from app.formula.geometry import _bridge_query_pairs

    orig = r"\begin{cases} H_{ic}=1 & \text{if } i\in c \\ \end{cases}"
    pairs = _bridge_query_pairs("membership matrix", "goodness", orig)
    flat = " | ".join(f"{a}->{b}" for a, b in pairs)
    assert "membership matrix" in flat
    assert "goodness of the partition" in flat


def test_bridge_query_pairs_min_direction():
    from app.formula.geometry import _bridge_query_pairs

    orig = r"\min_{\tau,H} \mathrm{Tr}[R(\tau,H)]"
    pairs = _bridge_query_pairs("", "", orig)
    flat = " | ".join(f"{a}->{b}" for a, b in pairs)
    assert "which is to be maximised" in flat
    assert "weighted" in flat or "Markov Stability" in flat


def test_bridge_query_pairs_strips_embedded_math():
    from app.formula.geometry import _bridge_query_pairs

    before = (
        "Markov Stability is defined as\n\n"
        "$$\\min_{t} \\mathrm{Tr}[R]$$\n\n"
        "which is to be maximised at every time"
    )
    pairs = _bridge_query_pairs(before, "Owing to the optimisation", r"\min Tr")
    flat = " | ".join(f"{a}->{b}" for a, b in pairs)
    assert "which is to be maximised" in flat


def test_bbox_vertically_distinct():
    from app.formula.geometry import _bbox_vertically_distinct

    a = (50.0, 430.0, 300.0, 535.0)
    b = (50.0, 382.0, 300.0, 423.0)
    assert _bbox_vertically_distinct(a, b)
    assert not _bbox_vertically_distinct(a, (50.0, 432.0, 300.0, 538.0))


def test_normalize_ligatures_defined():
    from app.formula.geometry import _normalize_ligatures

    assert "defined" in _normalize_ligatures("de fi ned as:")
    assert "dened" not in _normalize_ligatures("de fi ned as:")


def test_bridge_query_pairs_dtw_and_vi():
    from app.formula.geometry import _bridge_query_pairs

    dtw_pairs = _bridge_query_pairs(
        "The DTW similarity kernel is de fi ned as:",
        "where Dl denotes the DTW distance.",
        r"k_l(x,y)=\exp(-D/\sigma^2)",
    )
    flat = " | ".join(f"{a}->{b}" for a, b in dtw_pairs)
    assert "DTW similarity kernel" in flat
    assert "where Dl denotes" in flat

    vi_pairs = _bridge_query_pairs(
        "normalised variation of information between two partitions de fi ned as:",
        "where Shannon entropy",
        r"VI(H,H')=\frac{2\Omega-\Omega(H)-\Omega(H')}{\log N}",
    )
    vi_flat = " | ".join(f"{a}->{b}" for a, b in vi_pairs)
    assert "variation of information" in vi_flat
    assert "Shannon entropy" in vi_flat


def test_bridge_query_pairs_f1_metrics():
    from app.formula.geometry import _bridge_query_pairs

    before = (
        "Fixed-threshold performance: we report the F1 score at threshold 0.5 (F1@0.5), "
        "which balances precision and recall. For this metric, we convert probabilities "
        "to labels via 0 otherwise:"
    )
    after = "Having defined the leakage-excluded evaluation protocol, we next quantify"
    orig = r"F 1 & = \frac { 2 \Pr e c { R e c } } { \Pr e c { + R e c } }"
    pairs = _bridge_query_pairs(before, after, orig)
    flat = " | ".join(f"{a}->{b}" for a, b in pairs)
    assert "we convert probabilities" in flat
    assert "Having defined" in flat

    brier_before = (
        "Calibration: we report the Brier score (lower is better), "
        "defined as the mean squared error between outcomes and predicted probabilities [9]:"
    )
    brier_after = (
        "The Brier score is a strictly proper scoring rule for binary events [10].\n\n"
        "Fixed-threshold performance: we report the F1 score"
    )
    brier_pairs = _bridge_query_pairs(brier_before, brier_after, r"\text{wein}")
    brier_flat = " | ".join(f"{a}->{b}" for a, b in brier_pairs)
    assert "probabilities [9]" in brier_flat or "strictly proper" in brier_flat
    assert "we convert probabilities" not in brier_flat

