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
        text = postprocess_markdown(
            raw_text,
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
                "mode": cfg.mode,
            }
            report_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            emit(f"修复报告 → {report_path.name}")

        return RepairResult(
            markdown_path=final_md,
            raw_markdown_path=kept_raw if cfg.write_raw_md else None,
            report_path=report_path,
            issues_detected=len(issues),
            issues_repaired=repaired,
            methods=methods,
            quality_before=before,
            quality_after=after,
            metadata={"validator_warnings": warnings, "export_md": cfg.write_final_md},
        )
