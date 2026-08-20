"""Geometry phrase repairs without requiring a real PDF (chars mocked)."""
from __future__ import annotations

from app.repair.pdf.geometry import (
    GeoChar,
    _repair_high_confidence_phrases,
    repair_detached_scripts_in_text,
)


def _fake_chars_with_small() -> list[GeoChar]:
    # Enough size variation so geometry gate passes
    chars: list[GeoChar] = []
    for i, ch in enumerate("xRtiabcdefghijklmnopqrstuvwxyz"):
        size = 10.0 if i < 20 else 6.0
        chars.append(
            GeoChar(
                char=ch,
                x0=float(i),
                y0=0.0,
                x1=float(i) + 1,
                y1=10.0,
                size=size,
                font="Test",
                origin_y=10.0,
            )
        )
    return chars


def test_xti_phrase():
    text = "where x ( t ) i is an early representation"
    out, n = repair_detached_scripts_in_text(text, _fake_chars_with_small())
    assert n > 0
    assert r"$x_{i}^{(t)}$" in out


def test_bowtie_from_rtimes_ltimes():
    text = "joins only, $S (\\le t) 1$ ⋊ ⋉ $S (\\le t) 2).$"
    out, n = _repair_high_confidence_phrases(text)
    assert n >= 1
    assert r"\bowtie" in out
    assert "⋊" not in out
    assert r"$S_{1}^{(\le t)} \bowtie S_{2}^{(\le t)}$" in out


def test_t_set_phrase():
    text = "Let T = { t 1 , . . . , t K } denote cutoffs."
    out, n = _repair_high_confidence_phrases(text)
    assert n >= 1
    assert r"$T = \{t_1, \ldots, t_K\}$" in out


def test_no_geometry_without_small_chars():
    text = "where x ( t ) i is early"
    flat = [
        GeoChar("x", 0, 0, 1, 10, 10.0, "F", 10.0),
        GeoChar("i", 1, 0, 2, 10, 10.0, "F", 10.0),
    ]
    out, n = repair_detached_scripts_in_text(text, flat)
    assert n == 0
    assert out == text
