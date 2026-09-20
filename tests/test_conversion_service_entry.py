"""回归：ConversionService.run_task 入口契约（曾经在 to_dict 处直接崩溃）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.domain.job import ConversionRequest
from app.core.service.conversion import ConversionOptions, ConversionService
from app.utils.paths import SAVE_MODE_PDF_SIBLING, task_output_dir


def _pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "demo paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    return pdf


def test_conversion_options_to_dict_is_serializable(tmp_path: Path):
    options = ConversionOptions(output_root=tmp_path / "out", save_mode=SAVE_MODE_PDF_SIBLING)
    data = options.to_dict()
    import json

    text = json.dumps(data, ensure_ascii=False)  # 必须可 JSON 序列化
    assert "output_root" in text
    assert data["save_mode"] == SAVE_MODE_PDF_SIBLING
    assert isinstance(data["output_root"], str)
    # 派生只读字段也在快照里，便于诊断
    assert "docling_formula_enrich" in data
    assert "repair_keep_formulas" in data


def test_run_task_creates_output_next_to_pdf(tmp_path: Path, monkeypatch):
    """run_task 首步为 mkdir 输出目录；PDF 旁存档是默认行为。"""
    from app.core.domain.job import PipelinePlan

    pdf = _pdf(tmp_path)
    out_root = tmp_path / "out"

    created: list[Path] = []
    real_mkdir = Path.mkdir

    def spy(self, *args, **kwargs):
        created.append(self)
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", spy)

    # 只验证入口契约：计划置空，不真正跑 Docling
    monkeypatch.setattr(
        "app.core.service.conversion.plan_for_request",
        lambda *a, **k: PipelinePlan(profile="structured", parser="docling", stages=[]),
    )

    service = ConversionService(ConversionOptions(output_root=out_root))
    request_seen: list[ConversionRequest] = []

    class _Runner:
        def run(self, request, stages, *, plan=None, **kwargs):
            request_seen.append(request)
            raise RuntimeError("stop-after-entry")

    monkeypatch.setattr("app.core.service.conversion.JobRunner", _Runner)

    with pytest.raises(RuntimeError, match="stop-after-entry"):
        service.run_task(_pdf_once(pdf))

    assert created, "run_task 必须先创建输出目录"
    assert created[0] == pdf.parent / "demo paper_MD"
    assert request_seen and request_seen[0].output_dir == pdf.parent / "demo paper_MD"
    # extra["options"] 曾经让 run_task 在 to_dict 处崩溃
    assert request_seen[0].extra["options"]["save_mode"] == SAVE_MODE_PDF_SIBLING


def _pdf_once(pdf: Path):
    from app.task_model import ConvertTask

    return ConvertTask(pdf_path=pdf)


def test_task_output_dir_matches_request_output_dir(tmp_path: Path):
    pdf = _pdf(tmp_path)
    root = tmp_path / "out"
    assert task_output_dir(root, pdf) == pdf.parent / "demo paper_MD"
