"""FormulaPipeline：Cheap QA → 按预算 Recovery → Fallback / ReleaseGate。

状态机：
  DETECTED → VALID | CORRUPTED → RECOVERY_PENDING → SUCCESS | FAILED
  OCR 不是错误公式的必经流程。
  仅 RECOVERY_FAILED 才 fallback；生产 Markdown 默认 clean。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.formula.config import FormulaConfig, normalize_preset
from app.formula.detector import detect_unwrapped
from app.formula.fallback import failure_record, fallback_markup
from app.formula.normalizer import normalize_validated_latex
from app.formula.recovery import FormulaRecoveryManager
from app.formula.recognizer import build_recognizer
from app.formula.release_gate import check_release
from app.formula.report_reconcile import reconcile_report_after_deepseek
from app.formula.session import FormulaRecoverySession
from app.formula.types import (
    DocumentContext,
    FormulaCandidate,
    FormulaLifecycle,
    FormulaQAReport,
    FormulaTelemetry,
)
from app.formula.validator import validate_latex

_DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE = re.compile(r"(?<!\$)\$(?!\$)((?:\\.|[^$\\])+?)(?<!\$)\$(?!\$)")
_R_CODE_CTX = re.compile(
    r"(?i)\b(require|library|tibble|<-|ouladformat|dataset_|case\d+|"
    r"data\.frame|mutate|select|rename|as\.data\.frame|randomforest|caret)\b|"
    r"# A tibble"
)


def _inside_markdown_code_fence(md: str, pos: int) -> bool:
    """`` ``` `` 围栏内（含 R 控制台 ``$ tibble`` 输出）不是公式。"""
    return len(re.findall(r"^```", md[:pos], re.M)) % 2 == 1


def _inline_r_accessor_false_positive(body: str, context_before: str) -> bool:
    """R 代码 ``obj $ col`` 被 Docling 误当行内公式（O-016）。"""
    b = body.strip()
    if not re.fullmatch(r"[A-Za-z_][\w.]*", b):
        return False
    if re.search(r"\\|[{}^=+\-*/]", body):
        return False
    return bool(_R_CODE_CTX.search(context_before[-400:]))


def _deepseek_balanced_enabled(
    cfg: FormulaConfig, doc: DocumentContext | None = None
) -> bool:
    if not cfg.deepseek_limited_production_enabled:
        return False
    if normalize_preset(cfg.recovery_preset) != "balanced":
        return False
    return doc is None or bool(doc.pdf_path)


def _can_enqueue_deepseek(
    cand: FormulaCandidate,
    cfg: FormulaConfig,
    doc: DocumentContext,
    *,
    wrap_dollars: bool = False,
) -> bool:
    if not _deepseek_balanced_enabled(cfg, doc):
        return False
    if wrap_dollars and cand.display_mode == "inline":
        return True
    if wrap_dollars:
        return False
    return cand.display_mode == "display"


@dataclass
class FormulaPipelineResult:
    markdown: str
    report: FormulaQAReport


class FormulaPipeline:
    def __init__(
        self,
        config: FormulaConfig | None = None,
        recovery: FormulaRecoveryManager | None = None,
    ) -> None:
        self.config = config or FormulaConfig()
        self.recovery = recovery or FormulaRecoveryManager(
            self.config, recognizer=build_recognizer(self.config)
        )

    def process_markdown(
        self,
        md: str,
        *,
        pdf_path: str | Path | None = None,
    ) -> FormulaPipelineResult:
        cfg = self.config
        report = FormulaQAReport()
        report.telemetry = FormulaTelemetry(preset=cfg.recovery_preset)
        if not cfg.enabled or not md:
            return FormulaPipelineResult(markdown=md, report=report)

        t0 = time.perf_counter()
        doc = DocumentContext(pdf_path=str(pdf_path) if pdf_path else None, markdown=md)
        with FormulaRecoverySession(doc.pdf_path, cfg) as session:
            session.telemetry.preset = cfg.recovery_preset
            self.recovery.bind_session(session)
            # Lean Balanced：不预热 UniMERNet；仅 DeepSeek Worker 由外层并行预热
            primary = (cfg.recognizer_primary or "").lower().strip()
            lean = bool(getattr(cfg, "lean_docling_balanced", False))
            if (
                cfg.budget.max_ocr_calls_per_formula > 0
                and primary not in {"null", "none", "off"}
                and not lean
            ):
                t_load = time.perf_counter()
                warm = getattr(self.recovery.recognizer, "_ensure_model", None)
                if callable(warm):
                    try:
                        warm()
                    except Exception:
                        pass
                session.telemetry.ocr_load_seconds += time.perf_counter() - t_load
            out = self._process_with_session(md, doc, report, session)

        tel = self.recovery.session.telemetry if self.recovery.session else report.telemetry
        if tel is None:
            tel = FormulaTelemetry(preset=cfg.recovery_preset)
        tel.total_seconds = time.perf_counter() - t0
        tel.corruption_suppressed = report.fallback
        tel.recovery_success = report.recovery_success_count
        report.telemetry = tel
        return FormulaPipelineResult(markdown=out, report=report)

    def _process_with_session(
        self,
        md: str,
        doc: DocumentContext,
        report: FormulaQAReport,
        session: FormulaRecoverySession,
    ) -> str:
        cfg = self.config
        t_det = time.perf_counter()
        out = md
        from app.formula.equation_identity import (
            NOT_DECODED_RE,
            bind_equation_identities,
            bind_equation_identities_v2,
            meaningful_context_window,
        )

        deepseek_pending: list[tuple[str, FormulaCandidate]] = []

        # Phase 5H：几何优先用 PDF 印刷编号锚点 / defining 序，禁止「上下文最后 Eq」误定位
        from app.formula.equation_identity import iter_equation_mentions

        not_decoded = list(NOT_DECODED_RE.finditer(out))
        defining_labels = [
            m.label for m in iter_equation_mentions(out) if m.kind == "defining"
        ]
        pending_meta: list[tuple[Any, FormulaCandidate]] = []
        slot_geometry: dict[int, tuple[int, tuple[float, float, float, float]]] = {}
        geometry_qa: list[dict[str, Any]] = []
        report.geometry_qa = geometry_qa
        sess = self.recovery.session
        prev_page: int | None = None

        from app.formula.geometry import FormulaGeometryResolver

        geo_resolver: FormulaGeometryResolver | None = None
        defer_heavy_geometry = _deepseek_balanced_enabled(cfg, doc)
        _ = defer_heavy_geometry  # 保留：telemetry / 未来分轨
        if sess is not None and getattr(sess, "pdf_doc", None) is not None:
            geo_resolver = FormulaGeometryResolver(sess.pdf_doc, sess.anchor_index)

        for slot_i, m in enumerate(not_decoded):
            ctx_b = meaningful_context_window(out, m.start(), before=True)
            ctx_a = meaningful_context_window(out, m.end(), before=False)
            cand = FormulaCandidate(
                text=r"\quad\quad\quad garbage",
                raw_text="<!-- formula-not-decoded -->",
                source_type="parser_math",
                display_mode="display",
                start=m.start(),
                end=m.end(),
                context_before=ctx_b,
                context_after=ctx_a,
                equation_number="",
                lifecycle=FormulaLifecycle.CORRUPTED,
                status="corrupted",
                issues=["docling_formula_not_decoded"],
            )
            report.formula_count += 1
            report.corrupted_formula_count += 1
            report.rejected += 1

            locate_hint = ""
            if slot_i < len(defining_labels):
                locate_hint = defining_labels[slot_i]
            if sess is not None and geo_resolver is not None:
                try:
                    found = None
                    geo_dec = None
                    if geo_resolver is not None:
                        geo_dec = geo_resolver.resolve(
                            context_before=ctx_b,
                            context_after=ctx_a,
                            equation_number=locate_hint,
                            hint_page=prev_page,
                        )
                        if geo_dec.page is not None and geo_dec.bbox is not None:
                            found = (int(geo_dec.page), tuple(geo_dec.bbox))
                            cand.crop_class = geo_dec.crop_class or ""
                            cand.geometry_source = geo_dec.source or ""
                            if geo_dec.evidence:
                                cand.failure_stage = geo_dec.evidence.failure_stage or ""
                            geometry_qa.append(
                                {
                                    "slot": slot_i,
                                    "offset": m.start(),
                                    **geo_dec.to_dict(),
                                }
                            )
                    elif locate_hint:
                        if prev_page is not None:
                            hit = sess.formula_bbox_from_eq(locate_hint, page=prev_page)
                            if hit:
                                found = hit
                        if found is None:
                            cand.equation_number = locate_hint
                            found = self.recovery._locate_bbox(cand, sess)
                            cand.equation_number = ""
                    if found is None:
                        found = self.recovery._locate_bbox(cand, sess)
                    if found:
                        cand.page, cand.bbox = found
                        prev_page = int(cand.page) if cand.page is not None else prev_page
                except Exception:
                    pass
            if cand.page is not None and cand.bbox is not None:
                slot_geometry[m.start()] = (int(cand.page), tuple(cand.bbox))  # type: ignore[arg-type]
            pending_meta.append((m, cand))

        pdf_doc = getattr(sess, "pdf_doc", None) if sess else None
        identities, id_qa = bind_equation_identities_v2(
            out, slot_geometry=slot_geometry, pdf_doc=pdf_doc
        )
        report.equation_identity = id_qa.to_dict()
        if geometry_qa:
            report.geometry_qa = geometry_qa

        # 倒序写回 pending 块，避免 offset 错位
        for m, cand in reversed(pending_meta):
            ident = identities.get(m.start())
            if ident and (ident.equation_number or "").strip():
                cand.equation_number = ident.equation_number
                cand.number_status = (
                    "numbered_confirmed"
                    if float(ident.confidence or 0) >= 0.75
                    else "number_unknown"
                )
            else:
                # Phase 6D：无编号 ≠ 不可写回；内容身份靠 bbox
                cand.equation_number = ""
                cand.number_status = "unnumbered_confirmed"
            if _can_enqueue_deepseek_display(cand, cfg, doc):
                from app.formula.deepseek_production_pass import (
                    make_pending_display_block,
                    stable_candidate_id,
                )

                report.recovery_attempted_count += 1
                seq = len(deepseek_pending) + 1
                cid = stable_candidate_id(cand, seq=seq)
                existing = {x for x, _ in deepseek_pending}
                if cid in existing:
                    cid = f"{cid}_{seq}"
                cand.candidate_id = cid
                cand.lifecycle = FormulaLifecycle.RECOVERY_FAILED
                cand.status = "recovery_failed"
                report.recovery_failed_count += 1
                report.fallback += 1
                report.formula_failures.append(failure_record(cand))
                deepseek_pending.append((cid, cand))
                out = (
                    out[: m.start()]
                    + make_pending_display_block(
                        cid, r"\quad\quad\quad garbage"
                    )
                    + out[m.end() :]
                )
                if ident:
                    report.details.append(
                        {
                            "mode": "equation_identity",
                            "equation_number": ident.equation_number,
                            "confidence": ident.confidence,
                            "source": ident.source,
                            "evidence": list(ident.evidence),
                            "candidate_id": cid,
                            "page": cand.page,
                        }
                    )
            else:
                report.details.append(
                    {
                        "mode": "not_decoded",
                        "status": "no_bbox_or_deepseek_off",
                        "equation_number": cand.equation_number,
                        "page": cand.page,
                    }
                )

        # 替换 not-decoded 后重新绑定剩余 $$ 槽编号（位置已变）
        identities = bind_equation_identities(out)
        displays = [
            m
            for m in _DISPLAY.finditer(out)
            if not _inside_markdown_code_fence(out, m.start())
        ]
        report.formula_count += len(displays)

        for m in reversed(displays):
            body = m.group(1)
            # 跳过已是 DeepSeek pending 标记的块
            if "%dsid:" in body:
                continue
            eq = ""
            ident = identities.get(m.start())
            if ident:
                eq = ident.equation_number
            cand = FormulaCandidate(
                text=body,
                raw_text=body,
                source_type="parser_math",
                display_mode="display",
                start=m.start(),
                end=m.end(),
                context_before=meaningful_context_window(out, m.start(), before=True),
                context_after=meaningful_context_window(out, m.end(), before=False),
                equation_number=eq,
                lifecycle=FormulaLifecycle.DETECTED,
                status="detected",
            )
            replacement, cand = self._resolve_candidate(
                cand, doc, report, deepseek_pending=deepseek_pending
            )
            out = out[: m.start()] + replacement + out[m.end() :]

        inlines = list(_INLINE.finditer(out))
        for m in reversed(inlines):
            if _inside_markdown_code_fence(out, m.start()):
                continue
            body = m.group(1)
            ctx_b = out[max(0, m.start() - 200) : m.start()]
            if _inline_r_accessor_false_positive(body, ctx_b):
                continue
            report.formula_count += 1
            vr = validate_latex(
                body,
                cfg,
                context_before=out[max(0, m.start() - 60) : m.start()],
                context_after=out[m.end() : m.end() + 60],
            )
            if vr.valid:
                report.validated += 1
                continue
            if vr.severity < 0.9:
                continue
            cand = FormulaCandidate(
                text=body,
                raw_text=body,
                source_type="parser_math",
                display_mode="inline",
                context_before=out[max(0, m.start() - 60) : m.start()],
                context_after=out[m.end() : m.end() + 60],
                lifecycle=FormulaLifecycle.DETECTED,
                status="detected",
                issues=list(vr.issues),
                quality=vr.quality,
            )
            replacement, cand = self._resolve_candidate(
                cand, doc, report, wrap_dollars=True, deepseek_pending=deepseek_pending
            )
            out = out[: m.start()] + replacement + out[m.end() :]

        suspects = detect_unwrapped(out, cfg)
        report.suspected_unwrapped = len(suspects)
        session.telemetry.formula_detection_seconds += time.perf_counter() - t_det
        for h in suspects[:50]:
            report.details.append(
                {
                    "mode": "unwrapped_suspect",
                    "status": "detected",
                    "score": round(h.score, 3),
                    "issues": h.reasons,
                    "preview": h.text[:120],
                }
            )

        if (
            deepseek_pending
            and cfg.deepseek_limited_production_enabled
            and normalize_preset(cfg.recovery_preset) == "balanced"
            and doc.pdf_path
        ):
            from app.formula.deepseek_production_pass import (
                apply_deepseek_limited_production_pass,
            )

            out, ds_meta = apply_deepseek_limited_production_pass(
                out,
                doc.pdf_path,
                deepseek_pending,
                config=cfg,
            )
            report.deepseek_shadow = ds_meta.get("shadow")
            report.writeback = ds_meta.get("writeback") or {
                "via": ds_meta.get("via"),
                "error": ds_meta.get("error"),
                "applied": ds_meta.get("applied", 0),
            }
            reconcile_report_after_deepseek(report, out, cfg)
            if report.geometry_qa and report.deepseek_shadow:
                report.deepseek_shadow.setdefault("summary", {})[
                    "geometry_qa"
                ] = list(report.geometry_qa)
            # Phase 7.1：顶层 telemetry 与 shadow 对齐（避免日志写 OCR 0 次）
            sm = (report.deepseek_shadow or {}).get("summary") or {}
            if sm:
                st = session.telemetry
                st.ocr_calls = int(sm.get("ocr_calls") or st.ocr_calls or 0)
                st.ocr_inference_seconds = float(
                    sm.get("ocr_inference_seconds") or st.ocr_inference_seconds or 0.0
                )
                st.ocr_load_seconds = float(
                    sm.get("model_load_seconds")
                    or sm.get("cold_start_seconds")
                    or st.ocr_load_seconds
                    or 0.0
                )
                st.recovery_success = int(sm.get("accepted") or st.recovery_success or 0)
                st.recovery_rejected = int(sm.get("rejected") or st.recovery_rejected or 0)

        out = re.sub(r"\n{3,}", "\n\n", out)
        out = re.sub(r"[ \t]+\n", "\n", out)

        if cfg.release_gate_enabled and report.document_quality is None:
            report.document_quality = check_release(out, report, cfg)

        return out

    def _resolve_candidate(
        self,
        cand: FormulaCandidate,
        doc: DocumentContext,
        report: FormulaQAReport,
        *,
        wrap_dollars: bool = False,
        deepseek_pending: list[tuple[str, FormulaCandidate]] | None = None,
    ) -> tuple[str, FormulaCandidate]:
        cfg = self.config
        vr = validate_latex(
            cand.text,
            cfg,
            context_before=cand.context_before,
            context_after=cand.context_after,
        )
        cand.quality = vr.quality
        cand.issues = list(vr.issues)

        if vr.valid:
            norm = normalize_validated_latex(cand.text, cfg)
            cand.text = norm
            cand.lifecycle = FormulaLifecycle.VALID
            cand.status = "valid"
            report.validated += 1
            if norm != (cand.raw_text or ""):
                report.normalized += 1
            report.details.append(_detail(cand, vr.severity))
            body = f"${norm}$" if wrap_dollars else f"$$\n{norm}\n$$"
            return body, cand

        # invalid → CORRUPTED（不是直接 fallback；OCR 仍可能被预算跳过）
        cand.lifecycle = FormulaLifecycle.CORRUPTED
        cand.status = "corrupted"
        report.corrupted_formula_count += 1
        report.rejected += 1

        from app.formula.backends import uses_deepseek_pending
        from app.formula.recovery_route import (
            is_abstain_route,
            is_vlm_route,
            route_corrupted_formula,
        )

        route = route_corrupted_formula(
            cand,
            deepseek_available=bool(cfg.deepseek_limited_production_enabled),
            prefer_deepseek_primary=bool(
                getattr(cfg, "deepseek_primary_for_severe", True)
            ),
            lean_deepseek_only=bool(getattr(cfg, "lean_docling_balanced", False)),
            backend_mode=str(getattr(cfg, "formula_backend_mode", "legacy_deepseek")),
            recovery_preset=str(cfg.recovery_preset or "balanced"),
            specialist_available=True,
            vlm_available=bool(cfg.deepseek_limited_production_enabled)
            or bool(getattr(cfg, "vlm_fallback_enabled", False)),
        )

        if is_abstain_route(route):
            cand.lifecycle = FormulaLifecycle.RECOVERY_FAILED
            cand.status = "recovery_failed"
            cand.issues = list(cand.issues) + ["route_abstain"]
            report.recovery_failed_count += 1
            report.fallback += 1
            report.formula_failures.append(failure_record(cand))
            report.details.append(_detail(cand, vr.severity))
            return fallback_markup(cand, cfg), cand

        # 严重损坏 + Limited Production：跳过 UniMERNet，直接进 DeepSeek pending
        direct_ds = (
            is_vlm_route(route)
            and uses_deepseek_pending(
                str(getattr(cfg, "formula_backend_mode", "legacy_deepseek")),
                str(getattr(cfg, "vlm_fallback_backend", "")),
            )
            and deepseek_pending is not None
            and _can_enqueue_deepseek(cand, cfg, doc, wrap_dollars=wrap_dollars)
        )
        if direct_ds:
            if self.recovery.session is not None:
                try:
                    self._ensure_ds_geometry(
                        cand, self.recovery.session, report, slot=cand.start
                    )
                except Exception:
                    pass
            from app.formula.deepseek_production_pass import (
                make_pending_display_block,
                stable_candidate_id,
            )

            report.recovery_attempted_count += 1
            seq = len(deepseek_pending) + 1
            cid = stable_candidate_id(cand, seq=seq)
            existing = {x for x, _ in deepseek_pending}
            if cid in existing:
                cid = f"{cid}_{seq}"
            cand.candidate_id = cid
            cand.lifecycle = FormulaLifecycle.RECOVERY_FAILED
            cand.status = "recovery_failed"
            cand.issues = list(cand.issues) + ["route_deepseek_direct"]
            report.recovery_failed_count += 1
            report.fallback += 1
            report.formula_failures.append(failure_record(cand))
            report.details.append(_detail(cand, vr.severity))
            deepseek_pending.append((cid, cand))
            return make_pending_display_block(
                cid, cand.raw_text or cand.text or ""
            ), cand

        report.recovery_attempted_count += 1
        cand = self.recovery.recover(cand, doc)

        if cand.lifecycle == FormulaLifecycle.RECOVERY_SUCCESS:
            report.recovery_success_count += 1
            report.validated += 1
            norm = normalize_validated_latex(cand.text, cfg)
            cand.text = norm
            report.details.append(_detail(cand, 0.0))
            body = f"${norm}$" if wrap_dollars else f"$$\n{norm}\n$$"
            return body, cand

        cand.lifecycle = FormulaLifecycle.RECOVERY_FAILED
        cand.status = "recovery_failed"
        report.recovery_failed_count += 1
        report.fallback += 1

        # Limited Production：display + 有 bbox → 暂留可写回标记，交给 DeepSeek
        use_ds = (
            deepseek_pending is not None
            and _can_enqueue_deepseek(cand, cfg, doc, wrap_dollars=wrap_dollars)
            and uses_deepseek_pending(
                str(getattr(cfg, "formula_backend_mode", "legacy_deepseek")),
                str(getattr(cfg, "vlm_fallback_backend", "")),
            )
        )
        if use_ds and self.recovery.session is not None:
            try:
                self._ensure_ds_geometry(
                    cand, self.recovery.session, report, slot=cand.start
                )
            except Exception:
                pass
        if use_ds:
            from app.formula.deepseek_production_pass import (
                make_pending_display_block,
                stable_candidate_id,
            )

            seq = len(deepseek_pending) + 1
            cid = stable_candidate_id(cand, seq=seq)
            existing = {x for x, _ in deepseek_pending}
            if cid in existing:
                cid = f"{cid}_{seq}"
            cand.candidate_id = cid
            report.formula_failures.append(failure_record(cand))
            report.details.append(_detail(cand, vr.severity))
            deepseek_pending.append((cid, cand))
            return make_pending_display_block(cid, cand.raw_text or cand.text or ""), cand

        report.formula_failures.append(failure_record(cand))
        report.details.append(_detail(cand, vr.severity))

        return fallback_markup(cand, cfg), cand

    def _ensure_ds_geometry(
        self,
        cand: FormulaCandidate,
        sess: FormulaRecoverySession,
        report: FormulaQAReport,
        *,
        slot: int | None = None,
    ) -> bool:
        """无 bbox 时做一次全量 refine；已有 bbox 留给 executor 处理可疑 crop。"""
        if sess.pdf_doc is None:
            return False
        from app.formula.equation_numbers import bind_equation_number_from_latex

        bind_equation_number_from_latex(cand)
        if cand.page is not None and cand.bbox is not None:
            setattr(cand, "_geometry_prefetched", True)
            return True
        eq = (cand.equation_number or "").strip()
        if eq:
            try:
                hit = sess.formula_bbox_from_eq(eq, page=cand.page)
                if hit is None:
                    hit = sess.formula_bbox_from_eq(eq)
                if hit is not None:
                    cand.page, cand.bbox = int(hit[0]), tuple(hit[1])
                    cand.geometry_source = cand.geometry_source or "eq_anchor_hint"
                    qa = report.geometry_qa
                    if qa is not None:
                        qa.append(
                            {
                                "slot": slot,
                                "offset": slot,
                                "page": cand.page,
                                "bbox": list(cand.bbox) if cand.bbox else None,
                                "source": cand.geometry_source,
                                "escalation": "eq_anchor_hint",
                            }
                        )
            except Exception:
                pass
        if cand.page is not None and cand.bbox is not None:
            setattr(cand, "_geometry_prefetched", True)
            return True
        try:
            from app.formula.geometry import refine_formula_crop_bbox

            refined = refine_formula_crop_bbox(
                sess.pdf_doc,
                getattr(sess, "anchor_index", None),
                page=cand.page,
                bbox=cand.bbox,
                context_before=cand.context_before or "",
                context_after=cand.context_after or "",
                equation_number=eq,
                crop_class=getattr(cand, "crop_class", "") or "",
                original_latex=cand.raw_text or cand.text or "",
            )
            if refined is not None:
                cand.page, cand.bbox, cand.crop_class, cand.geometry_source = (
                    refined[0],
                    refined[1],
                    refined[2],
                    refined[3],
                )
                setattr(cand, "_geometry_prefetched", True)
                qa = report.geometry_qa
                if qa is not None:
                    qa.append(
                        {
                            "slot": slot,
                            "offset": slot,
                            "page": cand.page,
                            "bbox": list(cand.bbox) if cand.bbox else None,
                            "source": cand.geometry_source,
                            "crop_class": cand.crop_class,
                            "escalation": "pipeline_prefetch",
                        }
                    )
        except Exception:
            pass
        if cand.page is None or cand.bbox is None:
            try:
                from app.formula.geometry import FormulaGeometryResolver

                dec = FormulaGeometryResolver(
                    sess.pdf_doc, getattr(sess, "anchor_index", None)
                ).resolve(
                    context_before=cand.context_before or "",
                    context_after=cand.context_after or "",
                    equation_number=eq,
                    hint_page=cand.page,
                    original_latex=cand.raw_text or cand.text or "",
                )
                if dec.page is not None and dec.bbox is not None:
                    cand.page, cand.bbox = int(dec.page), tuple(dec.bbox)
                    cand.crop_class = dec.crop_class or ""
                    cand.geometry_source = dec.source or "resolver_fallback"
                    setattr(cand, "_geometry_prefetched", True)
                    qa = report.geometry_qa
                    if qa is not None:
                        qa.append(
                            {
                                "slot": slot,
                                "offset": slot,
                                "page": cand.page,
                                "bbox": list(cand.bbox) if cand.bbox else None,
                                "source": cand.geometry_source,
                                "crop_class": cand.crop_class,
                                "escalation": "resolver_fallback",
                            }
                        )
            except Exception:
                pass
        return True

    def _geometry_locate(
        self,
        cand: FormulaCandidate,
        sess: FormulaRecoverySession,
        report: FormulaQAReport,
        *,
        slot: int | None = None,
    ) -> bool:
        from app.formula.geometry import FormulaGeometryResolver

        if sess.pdf_doc is None:
            return False
        resolver = FormulaGeometryResolver(sess.pdf_doc, sess.anchor_index)
        dec = resolver.resolve(
            context_before=cand.context_before or "",
            context_after=cand.context_after or "",
            equation_number=(cand.equation_number or "").strip(),
            hint_page=cand.page,
        )
        if dec.page is None or dec.bbox is None:
            return False
        cand.page, cand.bbox = int(dec.page), tuple(dec.bbox)
        cand.crop_class = dec.crop_class or ""
        cand.geometry_source = dec.source or ""
        if dec.evidence:
            cand.failure_stage = dec.evidence.failure_stage or ""
        qa = report.geometry_qa
        if qa is not None:
            qa.append(
                {
                    "slot": slot,
                    "offset": slot,
                    **dec.to_dict(),
                }
            )
        return True


def _detail(cand: FormulaCandidate, severity: float) -> dict:
    return {
        "mode": cand.display_mode,
        "status": cand.status,
        "lifecycle": cand.lifecycle.value,
        "issues": cand.issues,
        "severity": round(severity, 3),
        "attempts": cand.recovery_attempts,
        "preview": (cand.raw_text or cand.text)[:120].replace("\n", " "),
    }
