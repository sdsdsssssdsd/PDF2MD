"""R14 拆分 md_postprocess + R15 lock/SBOM/smoke。"""
from __future__ import annotations

from pathlib import Path

from app.core.lockfile import LOCK_NAME, collect_lock, lock_path
from app.core.sbom import SBOM_NAME, collect_sbom, sbom_path
from app.core.smoke import collect_smoke
from app.utils.md_postprocess import (
    collapse_extra_blank_lines,
    ensure_figure_table_separation,
    normalize_display_math_multiline,
    normalize_heading_spacing,
    postprocess_markdown,
)


def test_hard_rules_still_live_in_md_postprocess():
    text = Path("app/utils/md_postprocess.py").read_text(encoding="utf-8")
    assert "def ensure_figure_table_separation" in text
    assert "def normalize_display_math_multiline" in text
    assert Path("app/utils/md_inline_math.py").is_file()
    assert Path("app/utils/md_bold.py").is_file()
    assert Path("app/utils/md_prose.py").is_file()
    assert "def convert_inline_unicode_math" not in text


def test_heading_and_blank_rules_are_idempotent():
    raw = "para\n# Title\nnext\n\n\n\nend\n"
    once = normalize_heading_spacing(raw)
    assert once == normalize_heading_spacing(once)
    assert collapse_extra_blank_lines(once) == collapse_extra_blank_lines(
        collapse_extra_blank_lines(once)
    )
    assert "\n\n# Title\n\n" in once
    piped = postprocess_markdown(raw, pdf_path=None, fix_bold=False)
    assert ensure_figure_table_separation(piped) == piped
    assert normalize_display_math_multiline(piped) == piped


def test_lock_sbom_smoke_and_portable_script():
    assert lock_path().is_file()
    assert lock_path().name == LOCK_NAME
    lock = collect_lock()
    assert lock["isolation"]["note"]
    assert "gui" in lock["extras"]
    assert list(lock["extras"]) == [
        "gui",
        "docling",
        "mineru",
        "web",
        "deepseek-ocr",
        "paddle",
        "bench",
        "dev",
    ]
    assert lock["dependencies"][0]["name"] == "PySide6"
    assert sbom_path().is_file()
    assert sbom_path().name == SBOM_NAME
    sbom = collect_sbom()
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["components"]
    smoke = collect_smoke()
    assert smoke["ok"] is True
    assert Path("scripts/run-portable.ps1").is_file()
