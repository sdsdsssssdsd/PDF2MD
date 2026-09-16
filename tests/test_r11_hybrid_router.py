"""R11：QA 驱动的 Page / Block Hybrid Router，禁止整篇 fallback。"""
from __future__ import annotations

import ast
from pathlib import Path

from app.core.domain.document import BLOCK_FORMULA, BlockIR, document_from_markdown
from app.core.domain.job import ConversionRequest
from app.core.domain.quality import QualityVerdict
from app.core.domain.recovery import RecoveryPatch, RecoveryStatus
from app.core.pipeline.planner import plan_for_request
from app.core.providers.descriptor import Capability
from app.core.qa.engine import run_unified_qa
from app.core.routing.profiler import DocumentProfile, PageProfile
from app.core.routing.recovery import apply_patch, plan_recovery, resolve_recovery, run_recovery
from app.core.routing.router import suggest_page_fallbacks, suggest_parser
from app.task_model import WorkflowChoice


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_mixed_pages_keep_base_parser_and_local_capabilities():
    prof = DocumentProfile(
        page_count=18,
        scan_ratio=0.12,
        formula_density=0.06,
        table_density=0.06,
        page_profiles=[
            PageProfile(number=15, table_like=True, text_chars=800),
            PageProfile(number=16, formula_like=True, text_chars=600),
            PageProfile(number=18, scan_like=True, text_chars=8),
        ],
    )
    assert suggest_parser(engine="自动", profile=prof) == "docling"
    fallbacks = suggest_page_fallbacks(prof)
    assert fallbacks["15"] == Capability.TABLE_STRUCTURE
    assert fallbacks["16"] == Capability.FORMULA_RECOGNITION
    assert fallbacks["18"] == Capability.VISION_PAGE
    plan = plan_for_request(
        ConversionRequest(
            source_path=Path("dummy.pdf"),
            output_dir=Path("."),
            workflow=WorkflowChoice.STRUCTURED.value,
        ),
        profile=prof,
    )
    assert plan.parser == "docling"
    assert plan.page_overrides == fallbacks
    assert "recover" in plan.stages
    assert "page_recovery" in plan.notes


def test_qa_formula_failure_becomes_block_or_page_request():
    md = """# Paper

PAGE 16

$$
formula-not-decoded
$$
"""
    document = document_from_markdown(md, source="a.pdf", page_count=18)
    quality = run_unified_qa(md, document=document, page_count=18)
    assert quality.status == QualityVerdict.INCOMPLETE.value
    requests = plan_recovery(quality, document)
    assert requests
    formula = [r for r in requests if r.required_capability == Capability.FORMULA_RECOGNITION]
    assert formula
    req = formula[0]
    assert req.scope in {"page", "block"}
    assert req.page == 16 or any(i.startswith("b-") for i in req.block_ids)
    handle = resolve_recovery(req)
    if handle is not None:
        assert handle.descriptor.has_capability(Capability.FORMULA_RECOGNITION)


def test_missing_page_requests_vision_not_whole_parser():
    md = "PAGE 1\n\nhello\n"
    document = document_from_markdown(md, source="a.pdf", page_count=3)
    quality = run_unified_qa(md, document=document, page_count=3)
    requests = plan_recovery(quality, document)
    vision = [r for r in requests if r.required_capability == Capability.VISION_PAGE]
    assert {r.page for r in vision} >= {2, 3}
    assert all(r.required_capability != Capability.PARSE_STRUCTURE for r in requests)


def test_empty_failed_document_does_not_plan_recovery():
    quality = run_unified_qa("   ")
    assert quality.status == QualityVerdict.FAILED.value
    assert plan_recovery(quality) == []


def test_specialist_patch_then_reqa_is_local():
    md = """# Paper

PAGE 16

$$
formula-not-decoded
$$
"""
    document = document_from_markdown(md, source="a.pdf", page_count=16)
    quality = run_unified_qa(md, document=document, page_count=16)
    fail_blocks = [b for b in document.blocks if b.type == BLOCK_FORMULA]
    assert fail_blocks
    target = fail_blocks[0]

    def formula_exec(request, doc, _markdown, _handle):
        patched = BlockIR(
            id=target.id,
            type=BLOCK_FORMULA,
            content="E=mc^2\\tag{1}",
            page=target.page,
            reading_order=target.reading_order,
        )
        return RecoveryPatch(
            request_id=request.id,
            provider_id="formula.test",
            blocks=[patched],
            rebuild_markdown=True,
        )

    outcome = run_recovery(
        quality=quality,
        document=document,
        markdown=md,
        page_count=16,
        executors={Capability.FORMULA_RECOGNITION: formula_exec},
    )
    assert outcome.changed
    assert any(r.status == RecoveryStatus.RESOLVED for r in outcome.requests)
    assert "formula-not-decoded" not in outcome.markdown
    assert outcome.quality.status != QualityVerdict.INCOMPLETE.value
    patched = next(b for b in outcome.document.blocks if b.id == target.id)
    assert patched.provider == "formula.test"
    assert patched.provenance.stage == "recover"


def test_apply_patch_keeps_figure_table_blank_line():
    md = "| a | b |\n| --- | --- |\n| 1 | 2 |\n![Fig](images/x.png)\n"
    document = document_from_markdown(md, source="a.pdf")
    table = next(b for b in document.blocks if b.type == "table")
    patch = RecoveryPatch(
        request_id="t1",
        provider_id="table.test",
        markdown_replacements={table.content: table.content},
        rebuild_markdown=True,
    )
    _doc, out = apply_patch(document, md, patch)
    fig_at = out.index("![Fig]")
    table_at = out.index("|")
    assert table_at < fig_at
    assert "\n\n" in out[table_at:fig_at]


def test_router_and_recovery_have_no_paddle_branch():
    for rel in (
        "app/core/routing/router.py",
        "app/core/routing/recovery.py",
        "app/core/routing/profiler.py",
    ):
        text = Path(rel).read_text(encoding="utf-8")
        imported = _imported(Path(rel))
        assert "if paddle" not in text
        assert "if provider ==" not in text
        for forbidden in ("paddle", "paddleocr", "marker", "app.engines"):
            assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported), rel


def test_qa_does_not_import_recovery_planner():
    forbidden = "app.core.routing.recovery"
    for rel in (
        "app/core/qa/engine.py",
        "app/core/qa/gold.py",
        "app/core/qa/checks.py",
        "app/core/domain/document.py",
    ):
        imported = _imported(Path(rel))
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported), rel


def test_conversion_recover_stage_is_wired():
    text = Path("app/core/service/conversion.py").read_text(encoding="utf-8")
    assert "run_recovery" in text
    assert "_stage_recover" in text
    assert "recovery_requests" in text
    plan = plan_for_request(
        ConversionRequest(
            source_path=Path("dummy.pdf"),
            output_dir=Path("."),
            workflow="快速自动",
        )
    )
    assert plan.stages[-2:] == ["recover", "export"]
