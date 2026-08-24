"""FormulaRecoveryManager：预算制 OCR，不是 6 次暴力重试。

硬规则：
- OCR 是昂贵 optional operation（Budget）
- OCR confidence ≠ validity；syntax-valid ≠ recovery-success（Gain）
- Recognizer 忽略 context；禁止猜写标准公式
- 上下文只用于否决明显无关 OCR（TokenConsistency）
- PyMuPDF Document 文档级复用
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from app.formula.config import FormulaConfig
from app.formula.gain import evaluate_recovery_gain
from app.formula.preprocess import formula_image_variants, to_pil_image
from app.formula.recognizer import (
    FormulaRecognizer,
    NullFormulaRecognizer,
    build_recognizer,
)
from app.formula.session import FormulaRecoverySession
from app.formula.types import DocumentContext, FormulaCandidate, FormulaLifecycle
from app.formula.validator import validate_latex


class FormulaRecoveryManager:
    def __init__(
        self,
        config: FormulaConfig | None = None,
        recognizer: FormulaRecognizer | None = None,
        session: FormulaRecoverySession | None = None,
    ) -> None:
        self.config = config or FormulaConfig()
        self.recognizer = recognizer or build_recognizer(self.config)
        self.session = session

    def bind_session(self, session: FormulaRecoverySession | None) -> None:
        self.session = session

    def recover(
        self,
        candidate: FormulaCandidate,
        document_context: DocumentContext | None = None,
        session: FormulaRecoverySession | None = None,
    ) -> FormulaCandidate:
        cfg = self.config
        doc = document_context or DocumentContext()
        sess = session or self.session
        own_session = False
        if sess is None:
            sess = FormulaRecoverySession(doc.pdf_path, cfg)
            sess.open()
            own_session = True
        tel = sess.telemetry
        tel.preset = cfg.recovery_preset

        cand = candidate
        cand.lifecycle = FormulaLifecycle.RECOVERY_PENDING
        cand.status = "recovery_pending"
        formula_t0 = time.perf_counter()
        formula_calls = 0

        try:
            if not cfg.recovery_enabled:
                cand.lifecycle = FormulaLifecycle.RECOVERY_FAILED
                cand.status = "recovery_failed"
                cand.issues = list(cand.issues) + ["recovery_disabled"]
                return cand

            pdf = Path(doc.pdf_path) if doc.pdf_path else None
            if pdf is None or not pdf.exists():
                cand.lifecycle = FormulaLifecycle.RECOVERY_FAILED
                cand.status = "recovery_failed"
                cand.issues = list(cand.issues) + ["no_pdf_for_recovery"]
                cand.recovery_log.append({"attempt": 0, "error": "no_pdf"})
                return cand

            if not sess.tracker.allow_ocr(0):
                tel.recovery_skipped_budget += 1
                cand.lifecycle = FormulaLifecycle.RECOVERY_FAILED
                cand.status = "recovery_failed"
                cand.issues = list(cand.issues) + ["ocr_skipped_budget"]
                cand.recovery_log.append(
                    {
                        "attempt": 0,
                        "error": "ocr_skipped_budget",
                        "preset": cfg.recovery_preset,
                    }
                )
                return cand

            if cand.bbox is None:
                t_bbox = time.perf_counter()
                found = self._locate_bbox(cand, sess)
                tel.bbox_seconds += time.perf_counter() - t_bbox
                if found:
                    cand.page, cand.bbox = found
                    cand.recovery_log.append(
                        {"attempt": 0, "action": "bbox_from_index", "page": cand.page}
                    )
            else:
                from app.formula.geometry import (
                    crop_bbox_suspicious,
                    refine_formula_crop_bbox,
                )

                if crop_bbox_suspicious(
                    sess.pdf_doc,
                    cand.page,
                    cand.bbox,
                    getattr(cand, "crop_class", "") or "",
                ):
                    t_bbox = time.perf_counter()
                    refined = refine_formula_crop_bbox(
                        sess.pdf_doc,
                        getattr(sess, "anchor_index", None),
                        page=cand.page,
                        bbox=cand.bbox,
                        context_before=cand.context_before or "",
                        context_after=cand.context_after or "",
                        equation_number=(cand.equation_number or "").strip(),
                        crop_class=getattr(cand, "crop_class", "") or "",
                        original_latex=cand.raw_text or cand.text or "",
                    )
                    if refined is None:
                        found = self._locate_bbox(cand, sess)
                        if found:
                            cand.page, cand.bbox = found
                            cand.recovery_log.append(
                                {
                                    "attempt": 0,
                                    "action": "bbox_relocated",
                                    "page": cand.page,
                                }
                            )
                    else:
                        cand.page, cand.bbox = refined[0], refined[1]
                        cand.crop_class, cand.geometry_source = refined[2], refined[3]
                        cand.recovery_log.append(
                            {
                                "attempt": 0,
                                "action": "bbox_refined",
                                "page": cand.page,
                                "source": refined[3],
                            }
                        )
                    tel.bbox_seconds += time.perf_counter() - t_bbox

            if cand.bbox is None or cand.page is None:
                cand.lifecycle = FormulaLifecycle.RECOVERY_FAILED
                cand.status = "recovery_failed"
                cand.issues = list(cand.issues) + ["no_bbox"]
                cand.recovery_log.append({"attempt": 0, "error": "no_bbox"})
                return cand

            promising = True
            attempt = 0
            while promising and sess.tracker.allow_ocr(
                formula_calls, time.perf_counter() - formula_t0
            ):
                attempt += 1
                pad_x = cfg.bbox_padding_x * (1.0 if attempt == 1 else 2.0)
                pad_y = cfg.bbox_padding_y * (1.0 if attempt == 1 else 2.5)
                cand.recovery_attempts = attempt
                try:
                    image = self._crop(sess, cand.page, cand.bbox, pad_x, pad_y, attempt=attempt)
                except Exception as e:
                    cand.recovery_log.append({"attempt": attempt, "error": f"crop:{e}"})
                    break

                variants = (
                    formula_image_variants(image, attempt=1)
                    if cfg.preprocess_variants
                    else [("original", image)]
                )
                # 默认只跑 original；variants 关闭时绝不超过 1 张
                if not cfg.preprocess_variants:
                    variants = variants[:1]
                else:
                    variants = variants[:1]  # 即使打开也不在默认路径连跑 3 次

                variant_name, variant_img = variants[0]
                t_ocr = time.perf_counter()
                result = self.recognizer.recognize(variant_img, context=None)
                ocr_sec = time.perf_counter() - t_ocr
                formula_calls += 1
                sess.tracker.record_ocr(ocr_sec)
                tel.ocr_calls += 1
                tel.ocr_inference_seconds += ocr_sec

                entry: dict[str, Any] = {
                    "attempt": attempt,
                    "variant": variant_name,
                    "recognizer": result.recognizer,
                    "confidence": result.confidence,
                    "success": result.success,
                    "error": result.error,
                    "issues": list(result.issues),
                    "has_latex": bool(result.latex),
                    "ocr_latex": (result.latex or "")[:300],
                    "device": (result.meta or {}).get("device"),
                    "ocr_seconds": round(ocr_sec, 3),
                }
                cand.recovery_log.append(entry)

                if not result.latex or not result.success:
                    promising = False
                    tel.recovery_rejected += 1
                    continue

                vr = validate_latex(
                    result.latex,
                    cfg,
                    context_before=cand.context_before,
                    context_after=cand.context_after,
                )
                gain = evaluate_recovery_gain(
                    before_quality=cand.quality,
                    after_quality=vr.quality,
                    before_latex=cand.raw_text or cand.text or "",
                    after_latex=result.latex,
                    context_before=cand.context_before,
                    context_after=cand.context_after,
                    after_valid=vr.valid,
                )
                entry["validation"] = "passed" if vr.valid else "failed"
                entry["validation_issues"] = list(vr.issues)
                entry["gain"] = round(gain.gain, 3)
                entry["token_overlap"] = round(gain.token_overlap, 3)
                entry["gain_reasons"] = list(gain.reasons)
                entry["gain_accept"] = gain.accept

                if gain.accept:
                    cand.text = result.latex
                    cand.raw_text = result.raw or cand.raw_text
                    cand.lifecycle = FormulaLifecycle.RECOVERY_SUCCESS
                    cand.status = "recovery_success"
                    cand.issues = []
                    cand.quality = vr.quality
                    cand.confidence = result.confidence
                    tel.recovery_success += 1
                    tel.true_formula_recovery += 1
                    return cand

                tel.recovery_rejected += 1
                # Quality：仅当第一次“接近可信”（截断）才允许第二次
                promising = bool(gain.promising) and attempt < cfg.budget.max_ocr_calls_per_formula
                if not promising:
                    cand.issues = list(cand.issues) + list(gain.reasons)

            extra = ["recovery_exhausted"]
            if isinstance(self.recognizer, NullFormulaRecognizer):
                err = getattr(self.recognizer, "_error", None) or ""
                if "unimernet" in err.lower():
                    extra.append("unimernet_unavailable")
                elif "pix2tex" in err.lower():
                    extra.append("pix2tex_unavailable")
                else:
                    extra.append("recognizer_unavailable")
            if formula_calls == 0:
                extra = ["ocr_skipped_budget"]
                tel.recovery_skipped_budget += 1
            cand.lifecycle = FormulaLifecycle.RECOVERY_FAILED
            cand.status = "recovery_failed"
            cand.issues = list(cand.issues) + extra
            return cand
        finally:
            if own_session:
                sess.close()

    def _locate_bbox(
        self, cand: FormulaCandidate, sess: FormulaRecoverySession
    ) -> tuple[int, tuple[float, float, float, float]] | None:
        from app.formula.geometry import FormulaGeometryResolver, prose_bridge_locator

        numbers = self._equation_numbers(cand)
        eq_hint = (getattr(cand, "equation_number", None) or "").strip()
        if not eq_hint and numbers:
            eq_hint = numbers[0]

        if sess.pdf_doc is not None:
            resolver = FormulaGeometryResolver(sess.pdf_doc, sess.anchor_index)
            dec = resolver.resolve(
                context_before=cand.context_before or "",
                context_after=cand.context_after or "",
                equation_number=eq_hint,
                hint_page=cand.page,
            )
            if dec.page is not None and dec.bbox is not None:
                return int(dec.page), tuple(dec.bbox)

            bridge = prose_bridge_locator(
                sess.pdf_doc,
                context_before=cand.context_before or "",
                context_after=cand.context_after or "",
                hint_page=None,
                original_latex=cand.raw_text or cand.text or "",
            )
            if bridge.bbox is not None and bridge.page is not None:
                return int(bridge.page), tuple(bridge.bbox)

        from app.formula.geometry import _bbox_suspicious

        from app.formula.session import column_bounds

        pdf_doc = sess.pdf_doc
        if pdf_doc is None:
            return None
        queries: list[str] = []
        for n in numbers:
            queries.extend([f"Eq. ({n})", f"Eq.({n})", f"({n})"])
        needle = re.sub(r"\s+", " ", (cand.context_before or "")[-160:]).strip()
        needle = re.sub(r"[^\w\s.=()/-]", "", needle)
        words = [w for w in needle.split() if len(w) >= 4][-4:]
        if words:
            queries.append(" ".join(words[-3:]))
            queries.append(words[-1])
        try:
            for page_index in range(len(pdf_doc)):
                page = pdf_doc[page_index]
                page_w = float(page.rect.width)
                page_h = float(page.rect.height)
                for query in queries:
                    hits = page.search_for(query) or []
                    if not hits:
                        continue
                    hits = sorted(hits, key=lambda r: (r.x0, r.y0))
                    r = hits[-1]
                    if re.search(r"Eq\.?\s*\(\s*\d+", query, re.I) or re.fullmatch(
                        r"\(\d+\)", query.strip()
                    ):
                        band = max(42.0, (r.y1 - r.y0) * 5.0)
                        if re.fullmatch(r"\(\d+\)", query.strip()):
                            y0 = max(0.0, r.y0 - band * 0.55)
                            y1 = min(page_h, r.y1 + band * 0.45)
                            x0, x1 = column_bounds(page_w, r.x0, r.x1)
                        else:
                            y0 = r.y1
                            y1 = min(page_h, r.y1 + band)
                            x0, x1 = column_bounds(
                                page_w, r.x0, max(r.x1, page_w * 0.85)
                            )
                        bbox = (float(x0), float(y0), float(x1), float(y1))
                        if not _bbox_suspicious(page_w, bbox):
                            return page_index, bbox
                        continue
                    y0 = r.y1
                    y1 = min(page_h, r.y1 + max(36.0, (r.y1 - r.y0) * 4.5))
                    x0, x1 = column_bounds(page_w, r.x0, r.x1)
                    bbox = (float(x0), float(y0), float(x1), float(y1))
                    if not _bbox_suspicious(page_w, bbox):
                        return page_index, bbox
        except Exception:
            return None
        return None

    def _equation_numbers(self, cand: FormulaCandidate) -> list[str]:
        """从上下文与公式残片提取 Eq. 编号；前文最后出现的优先。"""
        bound = (getattr(cand, "equation_number", None) or "").strip()
        if bound:
            return [bound]

        def _context_nums(blob: str) -> list[str]:
            out: list[str] = []
            for m in re.finditer(
                r"(?:Eq(?:uation)?\.?\s*\(\s*(\d+)\s*\)|"
                r"公式\s*[（(]\s*(\d+)\s*[）)])",
                blob,
                re.I,
            ):
                n = m.group(1) or m.group(2)
                if n and n not in out:
                    out.append(n)
            return out

        def _display_tail_nums(blob: str) -> list[str]:
            """仅 display 尾标 (n)，避免 p(0) 等函数参数误匹配。"""
            out: list[str] = []
            for m in re.finditer(
                r"(?<![\w\\])\(\s*((?:\d\s*)+)\)\s*(?:&|\\\\|$)",
                blob,
            ):
                n = re.sub(r"\s+", "", m.group(1))
                if n and n not in out:
                    out.append(n)
            return out

        before_nums = _context_nums(cand.context_before or "")
        if before_nums:
            last = before_nums[-1]
            return [last] + [n for n in _context_nums(cand.context_after or "") if n != last]

        found: list[str] = []
        for blob in (cand.context_before or "", cand.context_after or ""):
            found.extend(n for n in _context_nums(blob) if n not in found)
        for blob in (cand.raw_text or "", cand.text or ""):
            found.extend(n for n in _display_tail_nums(blob) if n not in found)
        return found

    def _adaptive_scale(self, bbox: tuple[float, float, float, float]) -> float:
        cfg = self.config
        base = float(cfg.crop_render_scale or 2.0)
        h = max(0.0, bbox[3] - bbox[1])
        if h > 0 and h < cfg.crop_small_height_pt * 0.7:
            return min(3.0, max(base, cfg.crop_tiny_scale))
        if h > 0 and h < cfg.crop_small_height_pt:
            return min(3.0, max(base, cfg.crop_small_scale))
        return max(1.5, min(base, 3.0))

    def _crop(
        self,
        sess: FormulaRecoverySession,
        page_index: int,
        bbox: tuple[float, float, float, float],
        pad_x: float,
        pad_y: float,
        *,
        attempt: int,
    ) -> Any:
        import pymupdf

        doc = sess.pdf_doc
        if doc is None:
            raise RuntimeError("pdf_session_closed")
        page = doc[page_index]
        x0, y0, x1, y1 = bbox
        w, h = x1 - x0, y1 - y0
        if attempt >= 2:
            x0 = max(0, x0 - w * pad_x)
            x1 = min(page.rect.width, x1 + w * pad_x)
        else:
            x0 = max(0, x0 - w * pad_x)
            x1 = min(page.rect.width, x1 + w * pad_x)
        y0 = max(0, y0 - h * pad_y)
        y1 = min(page.rect.height, y1 + h * pad_y)
        clip = pymupdf.Rect(x0, y0, x1, y1)
        scale = self._adaptive_scale((x0, y0, x1, y1))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
        # 立刻转 PIL，避免依赖 pixmap 生命周期
        pil = to_pil_image(pix)
        return pil if pil is not None else pix
