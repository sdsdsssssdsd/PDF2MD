"""RepairPipeline：解析之后的统一修复入口。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from app.repair.analyzer import analyze_markdown, risk_score
from app.repair.models import RepairConfig, RepairResult
from app.repair.validator import validate_markdown
from app.utils.md_postprocess import postprocess_markdown

ProgressCB = Callable[[str], None]


class RepairPipeline:
    def __init__(self, config: RepairConfig | None = None) -> None:
        self.config = config or RepairConfig()

    def run(
        self,
        *,
        pdf_path: Path,
        raw_markdown_path: Path,
        out_dir: Path | None = None,
        progress: ProgressCB | None = None,
    ) -> RepairResult:
        cfg = self.config
        out_dir = out_dir or raw_markdown_path.parent
        stem = raw_markdown_path.name.replace(".raw.md", "").removesuffix(".md")
        final_md = out_dir / f"{stem}.md"

        def emit(msg: str) -> None:
            if progress:
                progress(msg)

        raw_text = raw_markdown_path.read_text(encoding="utf-8")
        issues = analyze_markdown(raw_text)
        before = 1.0 - risk_score(issues)
        emit(f"质量分析：检测到 {len(issues)} 个潜在问题（粗分 {before:.2f}）")

        methods: dict[str, int] = {"safe": 0, "keep": 0}
        repaired = 0

        if not cfg.enabled:
            final_md.write_text(raw_text, encoding="utf-8")
            methods["keep"] = len(issues)
            kept_raw: Path | None = raw_markdown_path
            if not cfg.write_raw_md:
                try:
                    if raw_markdown_path.exists() and raw_markdown_path.name.endswith(".raw.md"):
                        raw_markdown_path.unlink()
                    kept_raw = None
                except OSError:
                    pass
            if not cfg.write_final_md:
                try:
                    if final_md.exists():
                        final_md.unlink()
                except OSError:
                    pass
            report_path = None
            if cfg.write_repair_json:
                report_path = out_dir / f"{stem}.repair.json"
                report_path.write_text(
                    json.dumps(
                        {
                            "parser": None,
                            "quality_before": round(before, 4),
                            "quality_after": round(before, 4),
                            "issues": {"detected": len(issues), "repaired": 0, "unresolved": len(issues)},
                            "methods": methods,
                            "mode": "disabled",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            return RepairResult(
                markdown_path=final_md,
                raw_markdown_path=kept_raw,
                report_path=report_path,
                issues_detected=len(issues),
                issues_repaired=0,
                methods=methods,
                quality_before=before,
                quality_after=before,
            )

        emit("Safe 修复：Unicode 归一 / 无歧义清理 / 粗体恢复")
        formula_report: dict | None = None
        formula_publishable = True
        text = raw_text
        if cfg.keep_formulas:
            from app.formula import FormulaPipeline, formula_config_for_preset
            from app.formula.config import formula_config_for_deepseek_limited_production

            preset = getattr(cfg, "formula_recovery_preset", None) or "balanced"
            if getattr(cfg, "deepseek_limited_production", False) and preset == "balanced":
                fcfg = formula_config_for_deepseek_limited_production(
                    fallback_mode="clean",
                    crop_render_scale=2.0,  # 公式 OCR 与图片导出 scale 解耦
                )
                emit("FormulaPipeline：Lean Balanced（Docling LaTeX 种子 + DeepSeek 主修）")
            else:
                fcfg = formula_config_for_preset(preset, fallback_mode="clean")
                emit(
                    f"FormulaPipeline：Cheap QA + 预算恢复（preset={fcfg.recovery_preset}）"
                )
            b = fcfg.budget
            lean = bool(getattr(fcfg, "lean_docling_balanced", False)) or (
                (fcfg.recognizer_primary or "").lower().strip() in {"", "null", "none"}
            )
            if lean:
                emit("公式 OCR：Lean Balanced — DeepSeek 主修（不调用 UniMERNet）")
            elif b.max_ocr_calls_per_formula <= 0:
                emit("公式 OCR：Fast — 隔离错误公式，不调用 UniMERNet")
            else:
                doc_cap = (
                    f"全文最多 {b.max_ocr_calls_per_document} 次、"
                    if b.max_ocr_calls_per_document > 0
                    else "全文不限次数、"
                )
                emit(
                    f"公式 OCR：UniMERNet/{fcfg.recovery_preset}，"
                    f"每式最多 {b.max_ocr_calls_per_formula} 次、"
                    f"{doc_cap}"
                    f"裁图 {fcfg.crop_render_scale:g}×（首次 GPU 加载可能稍慢）"
                )
            if fcfg.deepseek_limited_production_enabled:
                wb_cap = int(fcfg.deepseek_max_writebacks_per_document or 0)
                wb_msg = (
                    "不限制条数（高置信全量写回）"
                    if wb_cap <= 0
                    else f"最多写回 {wb_cap} 处（高置信）"
                )
                emit(f"DeepSeek Limited Production：display 式 {wb_msg}")
            fp = FormulaPipeline(fcfg)
            fres = fp.process_markdown(text, pdf_path=pdf_path)
            text = fres.markdown
            formula_report = fres.report.to_dict()
            tel = (formula_report or {}).get("telemetry") or {}
            if tel:
                emit(
                    f"公式耗时 {tel.get('total_seconds', 0)}s / "
                    f"OCR {tel.get('ocr_calls', 0)} 次 "
                    f"（真恢复 {tel.get('true_formula_recovery_rate_num', 0)}，"
                    f"否决 {tel.get('recovery_rejected', 0)}，"
                    f"跳过 {tel.get('recovery_skipped_budget', 0)}）"
                )
            dq = fres.report.document_quality
            if dq is not None:
                formula_publishable = bool(dq.publishable)
                if not dq.publishable:
                    emit(
                        f"公式质量检查未通过：status={dq.status}，"
                        f"failures={dq.formula_failures}（{', '.join(dq.reasons[:4])}）"
                    )
            if fres.report.corrupted_formula_count:
                emit(f"污染公式：{fres.report.corrupted_formula_count} 处 → 已尝试恢复")
            if fres.report.recovery_attempted_count:
                emit(
                    f"恢复尝试：{fres.report.recovery_attempted_count}，"
                    f"成功 {fres.report.recovery_success_count}，"
                    f"失败 {fres.report.recovery_failed_count}"
                )
            if fres.report.suspected_unwrapped:
                emit(f"疑似漏检公式：{fres.report.suspected_unwrapped} 处（仅报告）")
            wb = fres.report.writeback or {}
            if wb:
                emit(
                    f"DeepSeek 写回审计：applied={wb.get('applied_count', wb.get('applied', 0))}，"
                    f"dry_run={wb.get('dry_run')}"
                )

        text = postprocess_markdown(
            text,
            pdf_path=pdf_path,
            fix_inline_math=bool(cfg.keep_formulas),
            fix_bold=bool(cfg.fix_bold),
            mode="safe",
        )
        if text != raw_text:
            repaired = max(1, sum(1 for i in issues if i.type.value in {
                "unicode_math",
                "decimal_split",
                "hat_corruption",
            }))
            methods["safe"] = repaired
        methods["keep"] = max(0, len(issues) - repaired)

        # 确定性小数粘合：0 . 5 → 0.5（safe、无歧义）；多轮以处理表格残片
        import re

        n_dec_total = 0
        for _ in range(6):
            text2, n_dec = re.subn(r"(\d+)\s+\.\s+(\d+)", r"\1.\2", text)
            if not n_dec:
                break
            text = text2
            n_dec_total += n_dec
        if n_dec_total:
            methods["safe"] = methods.get("safe", 0) + n_dec_total
            repaired += n_dec_total

        # 表格行再规范化一次（防几何短语误伤后残留）
        from app.utils.md_postprocess import _is_md_table_line, _repair_table_line_math

        lines = text.splitlines(keepends=True)
        new_lines: list[str] = []
        n_tbl = 0
        for line in lines:
            core, nl = (line[:-1], "\n") if line.endswith("\n") else (line, "")
            if _is_md_table_line(core):
                fixed = _repair_table_line_math(core)
                if fixed != core:
                    n_tbl += 1
                new_lines.append(fixed + nl)
            else:
                new_lines.append(line)
        if n_tbl:
            text = "".join(new_lines)
            methods["safe"] = methods.get("safe", 0) + n_tbl
            repaired += n_tbl

        # Phase 几何：仅显式开启（Phase 0 误伤验收通过后再开）
        if cfg.use_geometry:
            try:
                from app.repair.pdf.geometry import apply_geometry_repair

                emit("Geometry 修复：上下标 / 拆散脚本（保守）")
                text3, n_geo = apply_geometry_repair(text, pdf_path)
                if n_geo:
                    text = text3
                    methods["geometry"] = methods.get("geometry", 0) + n_geo
                    repaired += n_geo
                # 几何后再扫表格，清掉误加的 $
                lines = text.splitlines(keepends=True)
                new_lines = []
                n_tbl = 0
                for line in lines:
                    core, nl = (line[:-1], "\n") if line.endswith("\n") else (line, "")
                    if _is_md_table_line(core):
                        fixed = _repair_table_line_math(core)
                        if fixed != core:
                            n_tbl += 1
                        new_lines.append(fixed + nl)
                    else:
                        new_lines.append(line)
                if n_tbl:
                    text = "".join(new_lines)
                    methods["geometry"] = methods.get("geometry", 0) + n_tbl
                    repaired += n_tbl
            except Exception as e:
                emit(f"Geometry 跳过：{e}")

        final_md.write_text(text, encoding="utf-8")

        # 按导出组件保留/删除产物（解析阶段总会生成 .raw.md 供修复）
        kept_raw = raw_markdown_path
        if not cfg.write_raw_md:
            try:
                if raw_markdown_path.exists() and raw_markdown_path.name.endswith(".raw.md"):
                    raw_markdown_path.unlink()
                    emit(f"已按设置删除 {raw_markdown_path.name}")
                kept_raw = None
            except OSError:
                pass

        if not cfg.write_final_md:
            try:
                if final_md.exists():
                    final_md.unlink()
                    emit(f"已按设置删除 {final_md.name}")
            except OSError:
                pass

        after_issues = analyze_markdown(text)
        after = 1.0 - risk_score(after_issues)
        warnings = validate_markdown(text)
        for w in warnings:
            emit(f"校验警告：{w}")

        from app.utils.typora_math_repair import lint_typora_math

        typora_issues = lint_typora_math(text)
        if typora_issues:
            emit(f"Typora 兼容：{len(typora_issues)} 处待关注（见 repair.json typora_compat）")

        report_path = None
        if cfg.write_repair_json:
            report_path = out_dir / f"{stem}.repair.json"
            payload = {
                "parser": None,
                "quality_before": round(before, 4),
                "quality_after": round(after, 4),
                "issues": {
                    "detected": len(issues),
                    "repaired": repaired,
                    "unresolved": max(0, len(after_issues)),
                },
                "methods": methods,
                "detected_detail": [
                    {
                        "type": i.type.value,
                        "severity": i.severity,
                        "message": i.message,
                        "original": i.original,
                    }
                    for i in issues[:200]
                ],
                "validator_warnings": warnings,
                "typora_compat": [
                    {"code": i.code, "message": i.message, "snippet": i.snippet}
                    for i in typora_issues[:50]
                ],
                "mode": cfg.mode,
                "formula": formula_report,
                "document_status": (
                    "ok" if formula_publishable else "formula_incomplete"
                ),
            }
            report_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            emit(f"修复报告 → {report_path.name}")

        # 旁路诊断 sidecar：每次跑 FormulaPipeline 都刷新，避免「全合法」时沿用旧 QA
        if formula_report is not None and cfg.keep_formulas:
            qa_path = out_dir / f"{stem}.formula_qa.json"
            qa_path.write_text(
                json.dumps(formula_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            emit(f"公式 QA → {qa_path.name}")

        return RepairResult(
            markdown_path=final_md,
            raw_markdown_path=kept_raw if cfg.write_raw_md else None,
            report_path=report_path,
            issues_detected=len(issues),
            issues_repaired=repaired,
            methods=methods,
            quality_before=before,
            quality_after=after,
            metadata={
                "validator_warnings": warnings,
                "export_md": cfg.write_final_md,
                "formula_publishable": formula_publishable,
                "document_status": "ok" if formula_publishable else "formula_incomplete",
            },
        )
