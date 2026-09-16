"""k12 Core：DocumentIR / JobRunner / Profiler / Planner / Unified QA sidecar。"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.domain.document import document_from_markdown
from app.core.domain.job import ConversionRequest
from app.core.domain.quality import QualityVerdict, quality_from_markdown
from app.core.pipeline.checkpoint import write_run_sidecar
from app.core.pipeline.planner import plan_for_request
from app.core.pipeline.runner import JobRunner
from app.core.pipeline.stage import CallableStage, StageResult
from app.core.qa.gold import evaluate_gold
from app.core.routing.profiler import profile_source
from app.core.routing.router import suggest_parser
from app.formula.config import FormulaConfig
from app.task_model import EngineChoice, WorkflowChoice

_GOLD_DIR = Path(__file__).resolve().parent / "fixtures" / "academic_gold" / "paper_sample"


def test_document_ir_roundtrip_and_markdown():
    src = "# Title\n\nHello\n\n$$\nE=mc^2\n$$\n\n![Fig](images/a.png)\n"
    ir = document_from_markdown(src, source="x.pdf", provider="test")
    kinds = [b.type for b in ir.blocks]
    assert "heading" in kinds
    assert "formula" in kinds
    assert "figure" in kinds
    md = ir.to_markdown()
    assert "E=mc^2" in md
    data = ir.to_dict()
    assert data["schema_version"] == "1.0"
    assert data["version"] == "1.0"
    assert "qa" not in data
    assert ir.to_json()


def test_quality_verdicts():
    ok = quality_from_markdown("# A\n\ntext\n")
    assert ok.verdict == QualityVerdict.VERIFIED.value
    assert ok.schema_version == "1.0"
    warn = quality_from_markdown("x <!-- PDF2MD:IMAGE:i0001:f01 -->")
    assert warn.verdict in {
        QualityVerdict.WARNINGS.value,
        QualityVerdict.INCOMPLETE.value,
    }
    empty = quality_from_markdown("  ")
    assert empty.verdict == QualityVerdict.FAILED.value
    assert "empty_document" in empty.blocking_failures


def test_job_runner_success_and_checkpoint(tmp_path: Path):
    def parse(ctx):
        ctx["markdown_path"] = tmp_path / "out.md"
        ctx["markdown_path"].write_text("# ok\n", encoding="utf-8")
        return StageResult(name="parse", status="ok")

    req = ConversionRequest(
        source_path=tmp_path / "a.pdf",
        output_dir=tmp_path,
        workflow=WorkflowChoice.STRUCTURED.value,
    )
    result = JobRunner().run(req, [CallableStage("parse", parse)])
    assert result.ok
    run = json.loads((tmp_path / ".pdf2md" / "run.json").read_text(encoding="utf-8"))
    assert run["schema_version"] == "1.0"
    assert run["document_ir"] == ""
    assert run["quality_report"] == ""


def test_job_runner_stops_on_failure(tmp_path: Path):
    def boom(_ctx):
        return StageResult(name="parse", status="failed", error="nope")

    called = {"n": 0}

    def later(_ctx):
        called["n"] += 1
        return StageResult(name="later", status="ok")

    req = ConversionRequest(source_path=tmp_path / "a.pdf", output_dir=tmp_path, workflow="快速自动")
    result = JobRunner().run(req, [CallableStage("parse", boom), CallableStage("later", later)])
    assert not result.ok
    assert called["n"] == 0


def test_job_runner_qa_is_terminal_gate(tmp_path: Path):
    def qa(ctx):
        md = ""
        path = tmp_path / "out.md"
        path.write_text(md, encoding="utf-8")
        ctx["markdown_path"] = path
        document = document_from_markdown(md, source="a.pdf")
        report = quality_from_markdown(md)
        ctx["document"] = document
        ctx["quality"] = report
        if report.status == QualityVerdict.FAILED.value:
            return StageResult(name="qa", status="failed", error="unified_qa_failed")
        return StageResult(name="qa", status="ok")

    req = ConversionRequest(source_path=tmp_path / "a.pdf", output_dir=tmp_path, workflow="快速自动")
    result = JobRunner().run(req, [CallableStage("qa", qa)])
    assert not result.ok
    assert result.quality is not None
    assert result.quality.status == QualityVerdict.FAILED.value
    run = json.loads((tmp_path / ".pdf2md" / "run.json").read_text(encoding="utf-8"))
    assert run["schema_version"] == "1.0"
    assert run["document_ir"] == "document.ir.json"
    assert run["quality_report"] == "qa.json"
    assert "checks" not in run
    qa_data = json.loads((tmp_path / ".pdf2md" / "qa.json").read_text(encoding="utf-8"))
    assert qa_data["schema_version"] == "1.0"
    assert qa_data["status"] == QualityVerdict.FAILED.value
    ir = json.loads((tmp_path / ".pdf2md" / "document.ir.json").read_text(encoding="utf-8"))
    assert ir["schema_version"] == "1.0"
    assert "qa" not in ir


def test_planner_keeps_five_profiles():
    tmp = Path("dummy.pdf")
    daily = plan_for_request(
        ConversionRequest(source_path=tmp, output_dir=tmp.parent, workflow=WorkflowChoice.DAILY.value)
    )
    assert daily.profile == "daily_vision"
    api = plan_for_request(
        ConversionRequest(source_path=tmp, output_dir=tmp.parent, workflow=WorkflowChoice.VISION_API.value)
    )
    assert api.profile == "pdf_vision_api"
    web = plan_for_request(
        ConversionRequest(source_path=tmp, output_dir=tmp.parent, workflow=WorkflowChoice.VISION_WEB.value)
    )
    assert web.profile == "pdf_vision_web"
    assert "experimental_provider" in web.notes
    repair = plan_for_request(
        ConversionRequest(source_path=tmp, output_dir=tmp.parent, workflow=WorkflowChoice.FORMAT_REPAIR.value)
    )
    assert repair.profile == "format_repair"
    structured = plan_for_request(
        ConversionRequest(source_path=tmp, output_dir=tmp.parent, workflow="快速自动")
    )
    assert structured.profile == "structured"
    assert "parse" in structured.stages
    assert "qa" in structured.stages
    assert "recover" in structured.stages


def test_suggest_parser_honors_explicit_engine():
    assert suggest_parser(engine=EngineChoice.MINERU.value) == "mineru"
    assert suggest_parser(engine=EngineChoice.DOCLING.value) == "docling"
    missing = profile_source(Path("definitely-missing-xyz.pdf"))
    assert missing.page_count == 0
    assert suggest_parser(Path("definitely-missing-xyz.pdf"), engine="自动") == "docling"


def test_write_run_sidecar(tmp_path: Path):
    ir = document_from_markdown("# T\n\nbody\n", source="a.pdf")
    qa = quality_from_markdown("# T\n\nbody\n")
    path = write_run_sidecar(
        tmp_path,
        workflow="快速自动",
        profile="structured",
        parser="docling",
        markdown_path=str(tmp_path / "a.md"),
        document=ir,
        quality=qa,
    )
    assert path.is_file()
    run = json.loads(path.read_text(encoding="utf-8"))
    assert run["schema_version"] == "1.0"
    assert run["document_ir"] == "document.ir.json"
    assert run["quality_report"] == "qa.json"
    assert "extra" not in run
    assert (tmp_path / ".pdf2md" / "document.ir.json").is_file()
    assert (tmp_path / ".pdf2md" / "qa.json").is_file()
    ir_data = json.loads((tmp_path / ".pdf2md" / "document.ir.json").read_text(encoding="utf-8"))
    assert "qa" not in ir_data
    qa_data = json.loads((tmp_path / ".pdf2md" / "qa.json").read_text(encoding="utf-8"))
    assert qa_data["schema_version"] == "1.0"
    assert "checks" in qa_data


def test_academic_gold_deterministic_pass():
    md = """# Paper

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
    report = evaluate_gold(md, _GOLD_DIR, page_count=4)
    assert report.evaluator == "academic_gold"
    assert report.status == QualityVerdict.VERIFIED.value
    ids = {c.check_id: c.status for c in report.checks}
    assert ids["page_coverage"] == "pass"
    assert ids["equation_number_preservation"] == "pass"
    assert ids["text_anchor_preservation"] == "pass"
    assert ids["forbidden_markers"] == "pass"
    by_id = {c.check_id: c for c in report.checks}
    assert by_id["page_coverage"].evidence["found"] == [1, 2, 3, 4]
    assert by_id["equation_number_preservation"].evidence["missing"] == []
    assert by_id["text_anchor_preservation"].evidence["missing"] == []
    assert by_id["forbidden_markers"].evidence["hit"] == []


def test_academic_gold_flags_unresolved_formula():
    md = """# Paper

PAGE 1
PAGE 2
PAGE 3
PAGE 4

Bias and Variance.
formula-not-decoded

$$
E=mc^2\\tag{1}
$$

$$
x=y\\tag{2}
$$

See Eq. (7).
"""
    report = evaluate_gold(md, _GOLD_DIR, page_count=4)
    assert report.status == QualityVerdict.INCOMPLETE.value
    assert "formula_unresolved" in report.blocking_failures or "forbidden_markers" in report.blocking_failures


def test_formula_config_groups_runtime_split():
    cfg = FormulaConfig()
    groups = cfg.groups()
    assert groups.runtime.deepseek_idle_unload_minutes == cfg.deepseek_idle_unload_minutes
    assert groups.routing.recovery_preset == cfg.recovery_preset
    assert groups.detection.suspicious_threshold == cfg.suspicious_threshold


def test_deepseek_config_has_no_qt():
    text = Path("app/deepseek_api/config.py").read_text(encoding="utf-8")
    assert "PySide6" not in text
    assert "QSettings" not in text
    assert "settings_dialog" not in text


def test_conversion_worker_source_is_qt_bridge():
    text = Path("app/workers/docling_worker.py").read_text(encoding="utf-8")
    assert "ConversionService" in text
    for forbidden in (
        "RepairPipeline",
        "parse_pdf",
        "write_run_sidecar",
        "AssetPipeline",
        "if workflow",
        "if use_docling",
        "mineru_available",
    ):
        assert forbidden not in text
