# -*- coding: utf-8 -*-
from __future__ import annotations

from PIL import Image

import importlib.util
from pathlib import Path

from app.formula.vlm_crop_pad import letterbox_formula_crop_for_vlm

_spec = importlib.util.spec_from_file_location(
    "run_paddlevl_on_crops",
    Path(__file__).resolve().parents[1] / "scripts" / "run_paddlevl_on_crops.py",
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
_pred_from_vl = _mod._pred_from_vl


def test_letterbox_grows_short_crop():
    im = Image.new("RGB", (456, 49), (0, 0, 0))
    out = letterbox_formula_crop_for_vlm(im)
    assert out.size[0] >= 320
    assert out.size[1] >= 160
    assert out.size[0] % 32 == 0
    assert out.size[1] % 32 == 0
    # 原图像素仍在画布上，不是另裁 PDF
    assert out.getpixel((out.size[0] // 2, out.size[1] // 2)) == (0, 0, 0)
    assert out.getpixel((0, 0)) == (255, 255, 255)


def test_paddlevl_extracts_block_content():
    item = {
        "res": {
            "parsing_res_list": [
                {
                    "block_label": "formula",
                    "block_content": r" $$ \mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}\tag{7} $$ ",
                }
            ]
        }
    }
    pred = _pred_from_vl(item)
    assert "FPR" in pred
    assert r"\mathrm{FP}+\mathrm{TN}" in pred.replace(" ", "")


def test_paddlevl_extracts_truncated_raw():
    raw = (
        '{"res": {"parsing_res_list": [{"block_label": "formula", '
        r'"block_content": " $$ \\mathrm{FPR}=\\frac{\\mathrm{FP}}{\\mathrm{FP}+\\mathrm{TN}}\\tag{7} $$ ", '
        '"block_or'
    )
    pred = _pred_from_vl(raw)
    assert "FPR" in pred
    assert r"\mathrm{FP}+\mathrm{TN}" in pred.replace(" ", "")
