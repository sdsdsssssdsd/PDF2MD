"""R5.1：终态不变量 / sidecar 契约 / Worker 快照 / 架构边界。"""
from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.core.domain.document import document_from_markdown
from app.core.domain.job import ConversionRequest
from app.core.domain.quality import (
    CheckStatus,
    QualityVerdict,
    decide_status,
    make_check,
    quality_from_markdown,
)
from app.core.pipeline.checkpoint import write_run_sidecar
from app.core.pipeline.runner import JobRunner
from app.core.pipeline.stage import CallableStage, StageResult
from app.core.qa.engine import UNIFIED_CHECK_IDS
from app.core.qa.gold import evaluate_gold
from app.core.service.conversion import ConversionOptions
from app.workers.docling_worker import ConversionWorker

_GOLD_DIR = Path(__file__).resolve().parent / "fixtures" / "academic_gold" / "paper_sample"
_GOLD_MD = """# Paper

PAGE 1
PAGE 2
PAGE 3
PAGE 4

Bias and Variance.

$$
E=mc^2\\tag{1}
$$

$$
x=y\\tag{2}
$$

See Eq. (7) in the text.
"""

RUN_REQUIRED = {"schema_version", "job_id", "status", "document_ir", "quality_report"}
IR_REQUIRED = {"schema_version", "source", "pages", "blocks"}
QA_REQUIRED = {"schema_version", "status", "checks", "warnings", "blocking_failures"}
CHECK_REQUIRED = {
    "check_id",
    "scope",
    "status",
    "severity",
    "blocking",
    "affected_ids",
    "evidence",
}

_FAIL_EMPTY = make_check("empty_document", status=CheckStatus.FAIL.value, blocking=True, fatal=True)
_FAIL_FORMULA = make_check("formula_unresolved", status=CheckStatus.FAIL.value, blocking=True)
_FAIL_SOFT = make_check("placeholder_or_fake_url", status=CheckStatus.FAIL.value, blocking=False)
_WARN = make_check("page_coverage", status=CheckStatus.WARN.value, blocking=False)
_PASS = make_check("empty_document", status=CheckStatus.PASS.value, blocking=False)
_SKIP = make_check("retry_recovery_exhaustion", status=CheckStatus.SKIP.value, blocking=False)


@pytest.mark.parametrize(
    "checks,expected",
    [
        ([_FAIL_EMPTY, _SKIP, _PASS], QualityVerdict.FAILED.value),
        ([_SKIP, _WARN, _FAIL_EMPTY], QualityVerdict.FAILED.value),
        ([_FAIL_FORMULA, _FAIL_EMPTY, _WARN], QualityVerdict.FAILED.value),
        ([_FAIL_FORMULA, _SKIP, _PASS], QualityVerdict.INCOMPLETE.value),
        ([_PASS, _SKIP, _FAIL_FORMULA], QualityVerdict.INCOMPLETE.value),
        ([_FAIL_SOFT, _SKIP, _PASS], QualityVerdict.WARNINGS.value),
        ([_SKIP, _WARN, _PASS], QualityVerdict.WARNINGS.value),
        ([_PASS, _SKIP], QualityVerdict.VERIFIED.value),
        ([_SKIP, _SKIP], QualityVerdict.WARNINGS.value),
        ([_FAIL_FORMULA, _WARN], QualityVerdict.INCOMPLETE.value),
        ([_FAIL_SOFT, _WARN, _SKIP], QualityVerdict.WARNINGS.value),
    ],
)
def test_verdict_priority_order_independent(checks, expected):
    assert decide_status(checks) == expected
    assert decide_status(list(reversed(checks))) == expected


def test_failed_job_still_writes_sidecar_trio(tmp_path: Path):
    def boom(_ctx):
        return StageResult(name="parse", status="failed", error="nope")

    req = ConversionRequest(source_path=tmp_path / "a.pdf", output_dir=tmp_path, workflow="快速自动")
    result = JobRunner().run(req, [CallableStage("parse", boom)])
    assert not result.ok
    assert result.quality is not None
    run = json.loads((tmp_path / ".pdf2md" / "run.json").read_text(encoding="utf-8"))
    ir = json.loads((tmp_path / ".pdf2md" / "document.ir.json").read_text(encoding="utf-8"))
    qa = json.loads((tmp_path / ".pdf2md" / "qa.json").read_text(encoding="utf-8"))
    assert RUN_REQUIRED <= set(run)
    assert IR_REQUIRED <= set(ir)
    assert QA_REQUIRED <= set(qa)
    assert run["document_ir"] == "document.ir.json"
    assert run["quality_report"] == "qa.json"
    assert qa["status"] == QualityVerdict.FAILED.value


def test_empty_markdown_keeps_diagnostic_sidecar(tmp_path: Path):
    def qa(ctx):
        ctx["markdown_path"] = tmp_path / "out.md"
        ctx["markdown_path"].write_text("", encoding="utf-8")
        document = document_from_markdown("", source="a.pdf")
        report = quality_from_markdown("")
        ctx["document"] = document
        ctx["quality"] = report
        return StageResult(name="qa", status="failed", error="unified_qa_failed")

    req = ConversionRequest(source_path=tmp_path / "a.pdf", output_dir=tmp_path, workflow="快速自动")
    result = JobRunner().run(req, [CallableStage("qa", qa)])
    assert not result.ok
    root = tmp_path / ".pdf2md"
    assert (root / "run.json").is_file()
    assert (root / "document.ir.json").is_file()
    assert (root / "qa.json").is_file()
    qa = json.loads((root / "qa.json").read_text(encoding="utf-8"))
    empty = next(c for c in qa["checks"] if c["check_id"] == "empty_document")
    assert empty["blocking"] is True
    assert empty["severity"] == "fail"
    assert empty["evidence"]["chars"] == 0


def test_sidecar_json_public_contract(tmp_path: Path):
    ir = document_from_markdown("# T\n\nbody\n", source="paper.pdf")
    qa = quality_from_markdown("# T\n\nbody\n")
    write_run_sidecar(
        tmp_path,
        workflow="快速自动",
        profile="structured",
        parser="docling",
        source="paper.pdf",
        markdown_path="paper.md",
        job_id="abc123",
        document=ir,
        quality=qa,
    )
    run = json.loads((tmp_path / ".pdf2md" / "run.json").read_text(encoding="utf-8"))
    ir_data = json.loads((tmp_path / ".pdf2md" / "document.ir.json").read_text(encoding="utf-8"))
    qa_data = json.loads((tmp_path / ".pdf2md" / "qa.json").read_text(encoding="utf-8"))
    assert run["schema_version"] == "1.0"
    assert RUN_REQUIRED <= set(run)
    assert run["job_id"] == "abc123"
    assert run["document_ir"] == "document.ir.json"
    assert run["quality_report"] == "qa.json"
    assert "checks" not in run
    assert ir_data["schema_version"] == "1.0"
    assert IR_REQUIRED <= set(ir_data)
    assert "qa" not in ir_data
    assert qa_data["schema_version"] == "1.0"
    assert QA_REQUIRED <= set(qa_data)
    for check in qa_data["checks"]:
        assert CHECK_REQUIRED <= set(check)
        assert check["severity"] == check["status"]
        assert isinstance(check["blocking"], bool)
        assert isinstance(check["affected_ids"], list)
        assert isinstance(check["evidence"], dict)


def test_academic_gold_evidence_and_determinism():
    r1 = evaluate_gold(_GOLD_MD, _GOLD_DIR, page_count=4)
    r2 = evaluate_gold(_GOLD_MD, _GOLD_DIR, page_count=4)
    assert r1.status == QualityVerdict.VERIFIED.value
    assert [c.check_id for c in r1.checks] == list(UNIFIED_CHECK_IDS)
    by_id = {c.check_id: c for c in r1.checks}
    assert by_id["page_coverage"].evidence["found"] == [1, 2, 3, 4]
    assert by_id["page_coverage"].affected_ids == []
    assert by_id["equation_number_preservation"].evidence["missing"] == []
    assert set(by_id["equation_number_preservation"].evidence["found"]) >= {"1", "2", "7"}
    assert by_id["text_anchor_preservation"].evidence["missing"] == []
    assert by_id["forbidden_markers"].evidence["hit"] == []
    assert by_id["placeholder_or_fake_url"].evidence["count"] == 0
    assert r1.to_canonical_dict() == r2.to_canonical_dict()


def test_conversion_options_snapshot_is_frozen():
    opt = ConversionOptions(
        output_root=Path("."),
        per_folder=False,
        ocr_mode="auto",
        keep_formulas=False,
        deepseek_limited_production=True,
    )
    with pytest.raises(FrozenInstanceError):
        opt.keep_formulas = True  # type: ignore[misc]
    w = ConversionWorker(
        [],
        output_root=Path("."),
        per_folder=False,
        ocr_mode="auto",
        keep_formulas=False,
        deepseek_limited_production=True,
    )
    assert w._options_snapshot.parse_keep_formulas() is True
    with pytest.raises(FrozenInstanceError):
        w._options_snapshot.deepseek_limited_production = False  # type: ignore[misc]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_conversion_worker_architecture_imports():
    path = Path("app/workers/docling_worker.py")
    imported = _imported_modules(path)
    forbidden_prefixes = (
        "app.core.providers",
        "app.core.pipeline",
        "app.repair",
        "app.formula",
        "app.engines",
        "app.assets",
        "app.ocr",
    )
    for name in imported:
        assert not any(
            name == p or name.startswith(p + ".") for p in forbidden_prefixes
        ), f"Worker 不得 import {name}"
    assert "PySide6.QtCore" in imported or any(n.startswith("PySide6") for n in imported)
    assert "app.core.service.conversion" in imported
    text = path.read_text(encoding="utf-8")
    assert "ConversionService" in text
    assert "ConversionOptions" in text
    assert "_options_snapshot" in text


def test_main_window_source_is_view_not_orchestrator():
    path = Path("app/main_window.py")
    text = path.read_text(encoding="utf-8")
    assert "from app.workers.docling_worker" not in text
    assert "from app.workers." not in text
    assert "ConversionService(" not in text
    assert "VisionConversionWorker(" not in text
    assert "DailyVisionWorker(" not in text
    assert "FormatRepairWorker(" not in text
    assert "VisionFigureRebuildWorker(" not in text
    tree = ast.parse(text)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = (
        "app.workers",
        "app.workers.docling_worker",
        "app.core.service",
        "app.core.service.conversion",
        "app.core.providers",
        "app.core.pipeline",
        "app.repair",
        "app.formula",
        "app.engines",
        "app.assets",
    )
    for name in imported:
        assert not any(
            name == p or name.startswith(p + ".") for p in forbidden
        ), f"MainWindow 不得 import {name}"
    assert "app.ui.conversion_controller" in imported
    assert "app.ui.vision_controller" in imported
    assert "app.ui.daily_vision_controller" in imported
    assert "app.ui.repair_controller" in imported
