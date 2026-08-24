# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from app.formula.crop_cache import CROP_PAD_X, CROP_PAD_Y
from app.formula.gold_crop import (
    GOLD_PAD_X_PT,
    GOLD_PAD_Y_PT,
    crop_quality_tags,
    detect_running_header_ymax,
    line_eq_number,
    looks_like_prose,
    text_in_bbox,
    tight_bbox_for_equation,
)
from app.formula.gold_schema import FormulaGoldRecord, validate_gold_record


def test_production_pads_stay_loose():
    assert CROP_PAD_X == 0.10
    assert CROP_PAD_Y == 0.12
    assert GOLD_PAD_X_PT <= 4.0
    assert GOLD_PAD_Y_PT <= 4.0


def test_line_eq_number_ignores_prose_ref():
    assert line_eq_number("TPR = TP/(TP+FN)     (6)") == "6"
    assert line_eq_number(" (7) ") == "7"
    assert line_eq_number("Recall can be calculated using Eq. (4):") == ""
    assert line_eq_number("Where Y is the true target value") == ""
    assert line_eq_number("9") == ""
    assert line_eq_number("3") == ""
    assert line_eq_number(r"\Theta = \lambda I + \gamma(11T)") == ""
    assert line_eq_number("A = B (1a)") == "1a"


def test_prose_vs_formula():
    assert looks_like_prose("Where Y is the true target value, f is the model's prediction")
    assert looks_like_prose("CODE AVAILABILITY")
    assert not looks_like_prose("TPR = TP/(TP+FN) (6)")
    assert not looks_like_prose("model · min(step_num^{-0.5}, step_num · warmup_steps^{-1.5})")
    assert looks_like_prose("为提高樽海鞘算法在求解问题时的收敛速度和寻优精度")
    assert not looks_like_prose("Nu = A1 + B1 Re^{0.5}")


def _synthetic_two_eq_pdf(tmp_path: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=420, height=360)
    page.insert_text((16, 28), "Received: August 19, 2025. Revised: September 16, 2025", fontsize=8)
    page.insert_text((24, 88), "TPR = TP/(TP+FN)          (6)", fontsize=11)
    page.insert_text((24, 128), "FPR = FP/(FP+TN)          (7)", fontsize=11)
    path = tmp_path / "header_neighbors.pdf"
    doc.save(path)
    doc.close()
    return path


def test_tight_excludes_header_and_neighbor(tmp_path: Path):
    import pymupdf

    pdf = _synthetic_two_eq_pdf(tmp_path)
    doc = pymupdf.open(str(pdf))
    page = doc[0]
    header_ymax = detect_running_header_ymax(page)
    assert header_ymax > 20

    seed6 = [10.0, 18.0, 300.0, 110.0]
    seed7 = [10.0, 80.0, 300.0, 170.0]
    assert "header_overlap" in crop_quality_tags(seed6, header_ymax, [seed7])
    assert "neighbor_eq" in crop_quality_tags(seed6, header_ymax, [seed7])

    tight6 = tight_bbox_for_equation(
        page, seed6, equation_number="6", neighbor_bboxes=[seed7], header_ymax=header_ymax
    )
    tight7 = tight_bbox_for_equation(
        page, seed7, equation_number="7", neighbor_bboxes=[seed6], header_ymax=header_ymax
    )
    t6 = text_in_bbox(page, tight6)
    t7 = text_in_bbox(page, tight7)
    doc.close()

    assert "Received" not in t6
    assert "Revised" not in t6
    assert "(7)" not in t6
    assert "TPR" in t6
    assert "(6)" in t6
    assert "Received" not in t7
    assert "(6)" not in t7
    assert "FPR" in t7
    assert tight6[3] <= tight7[1] + 2.0


def test_tight_completes_formula_left_of_seed(tmp_path: Path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=520, height=200)
    page.insert_text((40, 90), "Attention(Q, K, V) = softmax(QK) V          (1)", fontsize=11)
    path = tmp_path / "attn.pdf"
    doc.save(path)
    doc.close()
    doc = pymupdf.open(str(path))
    page = doc[0]
    seed = [200.0, 70.0, 500.0, 120.0]
    tight = tight_bbox_for_equation(page, seed, equation_number="1")
    text = text_in_bbox(page, tight)
    doc.close()
    assert "Attention" in text
    assert "(1)" in text
    assert tight[0] < seed[0] - 4.0


def test_tight_includes_align_previous_line(tmp_path: Path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=420, height=220)
    page.insert_text((40, 70), "logit(P) = b0 + b1 X", fontsize=11)
    page.insert_text((40, 100), "+ sum beta k Xk                 (1)", fontsize=11)
    path = tmp_path / "align.pdf"
    doc.save(path)
    doc.close()
    doc = pymupdf.open(str(path))
    page = doc[0]
    seed = [30.0, 88.0, 400.0, 130.0]
    tight = tight_bbox_for_equation(page, seed, equation_number="1")
    text = text_in_bbox(page, tight)
    doc.close()
    assert "logit" in text
    assert "(1)" in text


def test_gold_schema_roundtrip_tight_fields():
    rec = FormulaGoldRecord.from_dict(
        {
            "id": "x",
            "pdf_id": "p",
            "page": 1,
            "bbox_pdf": [1, 2, 3, 4],
            "crop_path": "prod/x.png",
            "bbox_pdf_tight": [1.5, 2.5, 2.8, 3.2],
            "crop_path_tight": "tight/p/x.png",
            "crop_quality": ["header_overlap"],
            "gold_latex_raw": r"a=b",
            "verified": True,
        }
    )
    d = rec.to_dict()
    assert d["crop_path"] == "prod/x.png"
    assert d["crop_path_tight"] == "tight/p/x.png"
    assert d["crop_quality"] == ["header_overlap"]
    assert validate_gold_record(d) == []


def test_tight_formula_only_drops_prose_above(tmp_path: Path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=420, height=240)
    page.insert_text((40, 70), "variation of information between two partitions defined as:", fontsize=10)
    page.insert_text((40, 120), "VI(H,H') = (2O-O-O)/log(N)          (8)", fontsize=11)
    path = tmp_path / "vi.pdf"
    doc.save(path)
    doc.close()
    doc = pymupdf.open(str(path))
    page = doc[0]
    seed = [30.0, 50.0, 400.0, 160.0]
    tight = tight_bbox_for_equation(page, seed, equation_number="8")
    text = text_in_bbox(page, tight)
    doc.close()
    assert "VI" in text
    assert "(8)" in text
    assert "partitions" not in text


def test_tight_same_row_completes_right_label(tmp_path: Path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=420, height=180)
    page.insert_text((40, 90), "v(t,t') = v(H(t),H(t'))", fontsize=11)
    page.insert_text((360, 90), "(10)", fontsize=11)
    path = tmp_path / "nu.pdf"
    doc.save(path)
    doc.close()
    doc = pymupdf.open(str(path))
    page = doc[0]
    seed = [340.0, 70.0, 410.0, 120.0]
    tight = tight_bbox_for_equation(page, seed, equation_number="10")
    text = text_in_bbox(page, tight)
    doc.close()
    assert "v(t" in text or "H(t)" in text
    assert "(10)" in text
    assert tight[0] < 80.0


def test_tight_does_not_take_next_column_header(tmp_path: Path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=520, height=180)
    page.insert_text((40, 90), "VI(t,t') = VI(H(t),H(t'))", fontsize=11)
    page.insert_text((250, 90), "(10)", fontsize=11)
    page.insert_text((360, 90), "CODE AVAILABILITY", fontsize=11)
    path = tmp_path / "gutter.pdf"
    doc.save(path)
    doc.close()
    doc = pymupdf.open(str(path))
    page = doc[0]
    seed = [20.0, 70.0, 280.0, 120.0]
    tight = tight_bbox_for_equation(page, seed, equation_number="10")
    text = text_in_bbox(page, tight)
    doc.close()
    assert "VI" in text
    assert "(10)" in text
    assert "CODE" not in text
    assert "AVAILABILITY" not in text


def test_production_modules_do_not_import_gold_crop():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for rel in (
        "app/formula/pipeline.py",
        "app/formula/writeback.py",
        "app/formula/geometry.py",
        "app/formula/crop_cache.py",
    ):
        src = (root / rel).read_text(encoding="utf-8")
        assert "gold_crop" not in src, rel
        assert "gold_harvest" not in src, rel
