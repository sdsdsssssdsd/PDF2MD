"""保存位置：PDF 旁「PDF名_MD」独立文件夹（默认）+ 导出根目录回退。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.task_model import WorkflowChoice
from app.ui.conversion_controller import ConversionUiInputs, compile_options
from app.ui.vision_controller import VisionUiInputs, compile_vision_options
from app.utils.paths import (
    DEFAULT_SAVE_MODE,
    MD_SIBLING_SUFFIX,
    SAVE_MODE_PDF_SIBLING,
    SAVE_MODE_ROOT_FLAT,
    SAVE_MODE_ROOT_FOLDER,
    SAVE_MODES,
    normalize_save_mode,
    resolve_output_dir,
    resolve_vision_output_dir,
    resolve_vision_paths,
    sibling_archive_dir,
    sibling_archive_dir_writable,
    task_output_dir,
)

STRUCTURED = WorkflowChoice.STRUCTURED.value
VISION_WEB = WorkflowChoice.VISION_WEB.value
VISION_API = WorkflowChoice.VISION_API.value


def _pdf(tmp_path: Path, name: str = "paper.pdf") -> Path:
    pdf = tmp_path / name
    pdf.write_bytes(b"%PDF-1.4\n")
    return pdf


def test_default_save_mode_is_pdf_sibling():
    assert DEFAULT_SAVE_MODE == SAVE_MODE_PDF_SIBLING
    assert normalize_save_mode(None) == SAVE_MODE_PDF_SIBLING
    assert normalize_save_mode("不存在") == SAVE_MODE_PDF_SIBLING
    assert normalize_save_mode(SAVE_MODE_ROOT_FOLDER) == SAVE_MODE_ROOT_FOLDER
    assert set(SAVE_MODES) == {
        SAVE_MODE_PDF_SIBLING,
        SAVE_MODE_ROOT_FOLDER,
        SAVE_MODE_ROOT_FLAT,
    }


def test_sibling_dir_is_next_to_pdf(tmp_path: Path):
    pdf = _pdf(tmp_path)
    assert sibling_archive_dir(pdf) == tmp_path / f"paper{MD_SIBLING_SUFFIX}"


def test_task_output_dir_default_is_pdf_sibling(tmp_path: Path):
    pdf = _pdf(tmp_path)
    root = tmp_path / "out"
    out = task_output_dir(root, pdf)
    assert out == tmp_path / f"paper{MD_SIBLING_SUFFIX}"
    assert out.parent == pdf.parent


def test_task_output_dir_explicit_sibling_mode(tmp_path: Path):
    pdf = _pdf(tmp_path)
    out = task_output_dir(tmp_path / "out", pdf, False, save_mode=SAVE_MODE_PDF_SIBLING)
    # sibling 模式忽略 per_folder，仍在 PDF 旁
    assert out == tmp_path / f"paper{MD_SIBLING_SUFFIX}"


def test_root_folder_and_flat_modes_unchanged(tmp_path: Path):
    pdf = _pdf(tmp_path)
    root = tmp_path / "out"
    assert (
        task_output_dir(root, pdf, True, save_mode=SAVE_MODE_ROOT_FOLDER) == root / "paper"
    )
    assert task_output_dir(root, pdf, False, save_mode=SAVE_MODE_ROOT_FOLDER) == root
    # root_flat 由 save_mode 决定；per_folder 不再能覆盖它（UI 中两者联动）
    assert task_output_dir(root, pdf, True, save_mode=SAVE_MODE_ROOT_FLAT) == root


def test_sibling_unwritable_falls_back_to_output_root(tmp_path: Path, monkeypatch):
    pdf = _pdf(tmp_path)
    root = tmp_path / "out"
    monkeypatch.setattr(
        "app.utils.paths.sibling_archive_dir_writable", lambda *_a, **_k: False
    )
    assert task_output_dir(root, pdf, save_mode=SAVE_MODE_PDF_SIBLING) == root / "paper"
    assert resolve_vision_output_dir(
        root, pdf, VISION_WEB, save_mode=SAVE_MODE_PDF_SIBLING
    ) == root / "paper_高保真"


def test_sibling_writable_helper(tmp_path: Path):
    pdf = _pdf(tmp_path)
    assert sibling_archive_dir_writable(pdf) is True
    target = sibling_archive_dir(pdf)
    target.mkdir()
    assert sibling_archive_dir_writable(pdf) is True
    missing_parent = tmp_path / "nope" / "paper.pdf"
    assert sibling_archive_dir_writable(missing_parent) is False


def test_vision_and_structured_suffixes_do_not_collide(tmp_path: Path):
    pdf = _pdf(tmp_path)
    root = tmp_path / "out"
    structured = resolve_output_dir(
        root, pdf, STRUCTURED, save_mode=SAVE_MODE_PDF_SIBLING
    )
    vision = resolve_output_dir(root, pdf, VISION_WEB, save_mode=SAVE_MODE_PDF_SIBLING)
    api = resolve_output_dir(root, pdf, VISION_API, save_mode=SAVE_MODE_PDF_SIBLING)
    assert structured == tmp_path / "paper_MD"
    assert vision == tmp_path / "paper_高保真"
    assert api == tmp_path / "paper_API视觉"
    assert len({structured, vision, api}) == 3


def test_resolve_output_dir_respects_root_modes(tmp_path: Path):
    pdf = _pdf(tmp_path)
    root = tmp_path / "out"
    assert (
        resolve_output_dir(root, pdf, STRUCTURED, save_mode=SAVE_MODE_ROOT_FOLDER)
        == root / "paper"
    )
    # 视觉模式 root_flat：结果扁平落在导出目录，工作目录移到应用侧 _vision_work
    paths = resolve_vision_paths(root, pdf, VISION_WEB, save_mode=SAVE_MODE_ROOT_FLAT)
    assert paths.flat is True
    assert paths.result_dir == root
    assert paths.images_dir == root / "paper.images"
    assert paths.work_dir != root
    assert "_vision_work" in paths.work_dir.parts
    # 兼容入口返回工作目录（manifest / 渲染页在那里）
    assert (
        resolve_output_dir(root, pdf, VISION_WEB, save_mode=SAVE_MODE_ROOT_FLAT)
        == paths.work_dir
    )


def test_vision_paths_non_flat_keeps_single_dir(tmp_path: Path):
    pdf = _pdf(tmp_path)
    root = tmp_path / "out"
    for mode, expected in (
        (SAVE_MODE_ROOT_FOLDER, root / "paper_高保真"),
        (SAVE_MODE_PDF_SIBLING, tmp_path / "paper_高保真"),
    ):
        paths = resolve_vision_paths(root, pdf, VISION_WEB, save_mode=mode)
        assert paths.flat is False
        assert paths.work_dir == expected
        assert paths.result_dir == expected
        assert paths.images_dir == expected / "images"
        assert paths.images_name == "images"


def test_vision_paths_flat_includes_path_hash(tmp_path: Path):
    """扁平保存：工作目录按「PDF 名 + 路径哈希」隔离，同名不同路径不共享。"""
    pdf = _pdf(tmp_path)
    root = tmp_path / "out"
    paths = resolve_vision_paths(root, pdf, VISION_API, save_mode=SAVE_MODE_ROOT_FLAT)
    assert paths.flat is True
    assert paths.work_dir.name.startswith("paper_API视觉_")
    assert paths.work_dir.parent.name == "_vision_work"

    other_dir = tmp_path / "sub"
    other_dir.mkdir()
    other = _pdf(other_dir)
    fresh = resolve_vision_paths(root, other, VISION_API, save_mode=SAVE_MODE_ROOT_FLAT)
    assert fresh.work_dir != paths.work_dir


def test_vision_paths_flat_adopts_legacy_work_dir(tmp_path: Path):
    """扁平化之前遗留的 <导出目录>/<PDF名>_API视觉/ 继续当工作目录：不重渲染、不重调 API。"""
    import json

    pdf = _pdf(tmp_path)
    root = tmp_path / "out"
    legacy = root / "paper_API视觉"
    (legacy / ".vision").mkdir(parents=True)
    (legacy / ".vision" / "manifest.json").write_text(
        json.dumps({"pdf": "paper.pdf"}), encoding="utf-8"
    )

    paths = resolve_vision_paths(root, pdf, VISION_API, save_mode=SAVE_MODE_ROOT_FLAT)
    assert paths.work_dir == legacy
    assert paths.result_dir == root
    assert paths.images_name == "paper.images"


def test_vision_paths_flat_rejects_legacy_of_another_pdf(tmp_path: Path):
    """旧 manifest 记了别的 PDF 路径时不得沿用（否则会串用别人的转录结果）。"""
    import json

    pdf = _pdf(tmp_path)
    other_dir = tmp_path / "sub"
    other_dir.mkdir()
    other = _pdf(other_dir)
    root = tmp_path / "out"
    legacy = root / "paper_API视觉"
    (legacy / ".vision").mkdir(parents=True)
    (legacy / ".vision" / "manifest.json").write_text(
        json.dumps({"pdf": "paper.pdf", "pdf_path": str(other)}), encoding="utf-8"
    )

    mine = resolve_vision_paths(root, pdf, VISION_API, save_mode=SAVE_MODE_ROOT_FLAT)
    theirs = resolve_vision_paths(root, other, VISION_API, save_mode=SAVE_MODE_ROOT_FLAT)
    assert mine.work_dir != legacy
    assert theirs.work_dir == legacy


def test_compile_conversion_options_carries_save_mode(tmp_path: Path):
    pdf = _pdf(tmp_path)
    inputs = ConversionUiInputs(
        output_root=tmp_path / "out",
        per_folder=True,
        save_mode=SAVE_MODE_PDF_SIBLING,
    )
    options = compile_options(inputs)
    assert options.save_mode == SAVE_MODE_PDF_SIBLING
    assert options.worker_kwargs()["save_mode"] == SAVE_MODE_PDF_SIBLING
    assert (
        task_output_dir(
            options.output_root, pdf, options.per_folder, save_mode=options.save_mode
        )
        == tmp_path / "paper_MD"
    )


def test_compile_vision_options_carries_save_mode(tmp_path: Path):
    inputs = VisionUiInputs(
        output_root=tmp_path / "out", api=False, save_mode=SAVE_MODE_ROOT_FOLDER
    )
    options = compile_vision_options(inputs)
    assert options.save_mode == SAVE_MODE_ROOT_FOLDER
    assert options.worker_kwargs()["save_mode"] == SAVE_MODE_ROOT_FOLDER


def test_conversion_options_normalizes_unknown_save_mode(tmp_path: Path):
    from app.core.service.conversion import ConversionOptions

    options = ConversionOptions(output_root=tmp_path, save_mode="legacy-unknown")
    assert options.save_mode == DEFAULT_SAVE_MODE


def test_cli_default_save_mode_is_sibling(tmp_path: Path, capsys):
    from app.core.cli_convert import main

    pdf = _pdf(tmp_path)
    code = main([str(pdf), "--plan-only"])
    assert code == 0
    out = capsys.readouterr().out
    assert f"save_mode={SAVE_MODE_PDF_SIBLING}" in out


@pytest.mark.parametrize("mode", list(SAVE_MODES))
def test_cli_accepts_every_save_mode(tmp_path: Path, mode: str, capsys):
    from app.core.cli_convert import main

    pdf = _pdf(tmp_path)
    assert main([str(pdf), "--plan-only", "--save-mode", mode]) == 0
    assert f"save_mode={mode}" in capsys.readouterr().out
