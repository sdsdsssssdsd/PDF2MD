"""k10 Correction Core golden tests。"""
from __future__ import annotations

import json

from app.correction.local_fixer import apply_local_fixes
from app.correction.models import CorrectionConfig
from app.correction.patch_gate import validate_patch
from app.correction.pipeline import CorrectionPipeline
from app.format_repair.integrity import integrity_ok


def test_plain_brackets_become_display_math():
    src = "公式如下：\n[\n\\boxed{x > 0}\n]\n继续。\n"
    result = CorrectionPipeline(CorrectionConfig(mode="off")).run(src)
    assert "$$" in result.output_text
    assert "[\n\\boxed" not in result.output_text
    assert integrity_ok(src, result.output_text)


def test_gamma_ocr_repair():
    src = r"\frac1m Gamma!\left(\frac{n+1}{2m}\right)"
    out, patches = apply_local_fixes(src)
    assert r"\Gamma\!\left" in out
    assert "Gamma!" not in out
    assert patches


def test_o_spacing_repair():
    src = r"O!\left(\lambda\right)"
    out, _ = apply_local_fixes(src)
    assert r"O\!\left" in out


def test_array_row_break_repair():
    src = r"\begin{array}{l}a\[1mm]b\[1mm]c\end{array}"
    out, patches = apply_local_fixes(src)
    assert r"\\[1mm]" in out
    assert patches


def test_inline_variable_restored():
    src = "若 (n) 为奇数，则继续。\n"
    out, patches = apply_local_fixes(src)
    assert "$n$" in out
    assert "(n)" not in out or "$n$" in out
    assert patches


def test_equation_reference_protected():
    src = "由公式 (19) 可得。\n"
    out, patches = apply_local_fixes(src)
    assert "(19)" in out
    assert not patches


def test_patch_gate_rejects_number_change():
    ok, reason = validate_patch("n+1", "n+2")
    assert not ok
    assert reason == "number_mismatch"


def test_patch_gate_rejects_equation_number_change():
    ok, reason = validate_patch("公式 (19)", "公式 (20)")
    assert not ok


def test_horizontal_rules_removed_via_format_layer():
    src = "上文\n\n---\n\n[\n\\boxed{a}\n]\n\n下文\n"
    result = CorrectionPipeline(
        CorrectionConfig(mode="off", compact_display_math=False)
    ).run(src)
    assert result.integrity_ok
    assert "\n---\n" not in result.output_text
    assert "$$" in result.output_text


def test_typora_whitelist_accepts_sim_boxed_ge():
    from app.utils.typora_math_repair import find_undefined_math_commands

    body = r"\sim \boxed{x} x \ge 0"
    assert not find_undefined_math_commands(body)


def test_correction_report_sidecar_path(tmp_path):
    from app.correction.models import CorrectionResult
    from app.correction.report import correction_report_path, write_correction_report

    md = tmp_path / "paper.md"
    md.write_text("# x", encoding="utf-8")
    assert correction_report_path(md).name == "paper.correction.json"
    result = CorrectionResult(output_text="# x", stats={"mode": "auto"})
    out = write_correction_report(md, result)
    assert out is not None and out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["mode"] == "auto"


def test_patch_needs_vision_on_operator_change():
    from app.correction.patch_gate import patch_needs_vision

    assert patch_needs_vision("a < b", "a \\le b", gate_reason="operator_mismatch")

