"""Correction Pipeline 总调度（Phase A–E）。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.correction.deepseek_reviewer import TEXT_MODELS, edits_to_patches, review_issues
from app.correction.detector import detect_issues
from app.correction.local_fixer import apply_local_fixes
from app.correction.models import (
    CorrectionConfig,
    CorrectionContext,
    CorrectionIssue,
    CorrectionPatch,
    CorrectionResult,
)
from app.correction.patch_gate import apply_patch_once, apply_patches, try_apply_with_vision, validate_patch
from app.correction.validator import validate_corrected_markdown
from app.correction.vision_verifier import pick_verification_image
from app.format_repair.integrity import integrity_ok
from app.format_repair.models import RepairConfig as FormatRepairConfig
from app.format_repair.rules import repair_local
from app.vision_api.key_store import api_key_configured

ProgressCB = Callable[[str], None]


class CorrectionPipeline:
    def __init__(self, config: CorrectionConfig | None = None) -> None:
        self.config = config or CorrectionConfig()

    def run(
        self,
        text: str,
        *,
        context: CorrectionContext | None = None,
        progress: ProgressCB | None = None,
    ) -> CorrectionResult:
        cfg = self.config
        ctx = context or CorrectionContext()
        original = text or ""

        def emit(msg: str) -> None:
            if progress:
                progress(msg)

        emit("Correction：本地确定性修复")
        output = original
        applied: list[CorrectionPatch] = []
        rejected: list[CorrectionPatch] = []
        warnings: list[str] = []
        errors: list[str] = []
        api_summary: dict = {}
        vision_verified = 0

        if cfg.normalize_math:
            fmt_cfg = FormatRepairConfig(
                normalize_math=True,
                compact_display_math=cfg.compact_display_math,
                auto_inline_threshold=cfg.auto_inline_threshold,
                ambiguous_min_score=cfg.ambiguous_min_score,
            )
            local_fmt = repair_local(output, fmt_cfg)
            output = local_fmt.text
            for edit in local_fmt.edits:
                applied.append(
                    CorrectionPatch(
                        issue_id=f"FMT-{edit.kind}",
                        before=edit.before,
                        after=edit.after,
                        source="format_repair",
                        confidence=edit.confidence,
                        gate="accepted",
                        reason=edit.reason,
                    )
                )
            rejected.extend(
                CorrectionPatch(
                    issue_id=f"FMT-{edit.kind}",
                    before=edit.before,
                    after=edit.after,
                    source="format_repair",
                    confidence=edit.confidence,
                    gate="rejected",
                    reason=edit.reason,
                )
                for edit in local_fmt.rejected
            )

        output, local_patches = apply_local_fixes(output)
        output, local_applied, local_rejected = apply_patches(output, local_patches)
        applied.extend(local_applied)
        rejected.extend(local_rejected)

        issues = detect_issues(output)
        unresolved = [
            it
            for it in issues
            if not any(p.before == it.before and p.gate == "accepted" for p in applied)
        ]

        api_applied = 0
        api_checked = 0
        uncertain = 0
        if cfg.mode in {"auto", "strict"} and unresolved:
            if api_key_configured():
                model = cfg.text_model or TEXT_MODELS["fast"]
                if cfg.mode == "strict":
                    cfg.vision_verify = True
                emit(f"Correction：DeepSeek 审校 {len(unresolved)} 处（{model}）")
                try:
                    review = review_issues(
                        unresolved[: cfg.batch_size * 3],
                        model_name=model,
                        batch_size=cfg.batch_size,
                    )
                    api_summary = review
                    api_checked = int(review.get("checked") or 0)
                    uncertain = len(review.get("uncertain") or [])
                    api_patches = edits_to_patches(review)
                    verify_image = None
                    if cfg.vision_verify and (
                        ctx.source_images or ctx.pdf_path is not None
                    ):
                        verify_image = pick_verification_image(
                            pdf_path=ctx.pdf_path,
                            source_images=ctx.source_images,
                            needle=unresolved[0].before if unresolved else "",
                        )
                    for patch in api_patches:
                        ok, reason = validate_patch(patch.before, patch.after)
                        if ok:
                            output, result = apply_patch_once(output, patch)
                        elif (
                            cfg.vision_verify
                            and verify_image is not None
                            and reason in {"number_mismatch", "operator_mismatch"}
                        ):
                            emit("Correction：高风险 patch 源图核验…")
                            output, result = try_apply_with_vision(
                                output,
                                patch,
                                image_path=verify_image,
                                vision_model=cfg.vision_model,
                            )
                            if result.gate == "accepted" and result.source == "vision_verify":
                                vision_verified += 1
                        else:
                            output, result = apply_patch_once(output, patch)
                        if result.gate == "accepted":
                            applied.append(result)
                            if patch.source != "vision_verify":
                                api_applied += 1
                        else:
                            rejected.append(result)
                except Exception as exc:
                    warnings.append(f"DeepSeek 审校跳过：{exc}")
                    api_summary = {"error": str(exc)}
            else:
                warnings.append("API 审校未执行：未配置 DeepSeek API Key")

        if not integrity_ok(original, output):
            errors.append("原文完整性门失败，已回滚 Correction 修改")
            output = original
            applied.clear()

        warnings.extend(validate_corrected_markdown(output))

        stats = {
            "mode": cfg.mode,
            "model": api_summary.get("model"),
            "local_fixed": len(local_applied) + sum(
                1 for p in applied if p.source == "format_repair"
            ),
            "api_checked": api_checked,
            "api_applied": api_applied,
            "vision_verified": vision_verified,
            "uncertain": uncertain,
            "detected": len(issues),
        }

        result = CorrectionResult(
            input_text=original,
            output_text=output,
            issues_detected=issues,
            patches_applied=applied,
            patches_rejected=rejected,
            warnings=warnings,
            errors=errors,
            integrity_ok=not errors,
            api_summary=api_summary,
            stats=stats,
        )

        return result
