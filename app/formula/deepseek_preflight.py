"""批前判断：本文是否真的需要加载 DeepSeek（避免无裁图 PDF 白等冷启动）。"""
from __future__ import annotations

import re
from pathlib import Path

from app.formula.config import FormulaConfig
from app.formula.corruption import assess_corruption
from app.formula.equation_identity import NOT_DECODED_RE, meaningful_context_window
from app.formula.geometry import FormulaGeometryResolver
from app.formula.session import FormulaRecoverySession
from app.formula.validator import validate_latex

_DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)


def markdown_has_corrupt_display_math(md: str, cfg: FormulaConfig | None = None) -> bool:
    """Repair 内按需 OCR 的损坏 ``$$...$$`` 检测（**不**用于批前阻塞预检）。"""
    cfg = cfg or FormulaConfig()
    for m in _DISPLAY.finditer(md or ""):
        body = (m.group(1) or "").strip()
        if not body or "%dsid:" in body:
            continue
        vr = validate_latex(body, cfg)
        if not vr.valid:
            return True
        q = assess_corruption(body, cfg)
        if not q.valid or q.corruption_score >= 0.75:
            return True
    return False


def markdown_has_invalid_display_math(md: str, cfg: FormulaConfig | None = None) -> bool:
    """Lean Balanced 下无效 ``$$...$$`` 会进 DeepSeek pending（含 Docling 空格拆字）。"""
    cfg = cfg or FormulaConfig()
    for m in _DISPLAY.finditer(md or ""):
        body = (m.group(1) or "").strip()
        if not body:
            continue
        if "%dsid:" in body:
            return True
        if not validate_latex(body, cfg).valid:
            return True
    return False


def document_has_deepseek_recovery_work(
    md: str, pdf_path: str | Path | None
) -> bool:
    """本文 repair 是否会触发 DeepSeek OCR（批前必须收尾暖机）。"""
    if not md:
        return False
    if "%dsid:" in md:
        return True
    if document_needs_deepseek_ocr(md, pdf_path):
        return True
    return markdown_has_invalid_display_math(md)


def _display_corrupt_needs_deepseek_wait(
    md: str, cfg: FormulaConfig | None = None
) -> bool:
    """兼容旧名；与 ``markdown_has_invalid_display_math`` 等价。"""
    return markdown_has_invalid_display_math(md, cfg)


def should_ensure_deepseek_before_repair(
    md: str,
    pdf_path: str | Path | None,
    *,
    warmup_in_flight: bool = False,
    model_loaded: bool | None = None,
) -> bool:
    """批前是否阻塞等待 DeepSeek 就绪（把冷启动移出 repair critical path）。"""
    del model_loaded  # 已暖机时 ensure 几乎无成本，不再用 health 跳过
    if warmup_in_flight:
        return True
    return document_has_deepseek_recovery_work(md, pdf_path)


def document_needs_deepseek_ocr(md: str, pdf_path: str | Path | None) -> bool:
    """批前是否阻塞等待 DeepSeek（仅 not-decoded + 可定位裁图）。

    损坏 ``$$...$$`` 由 Repair/FormulaPipeline 按需 OCR，**不得**在此预检放行，
    否则 Docling 空格拆字公式会误触全文阻塞（冷启动回到 critical path）。
    """
    if not md:
        return False

    if not NOT_DECODED_RE.search(md):
        return False
    if pdf_path is None:
        return True
    path = Path(pdf_path)
    if not path.is_file():
        return True

    cfg: FormulaConfig | None = None
    try:
        from app.formula.config import formula_config_for_deepseek_limited_production

        cfg = formula_config_for_deepseek_limited_production()
    except Exception:
        cfg = FormulaConfig()

    try:
        with FormulaRecoverySession(path, cfg) as sess:
            resolver = FormulaGeometryResolver(sess.pdf_doc, sess.anchor_index)
            for m in NOT_DECODED_RE.finditer(md):
                ctx_b = meaningful_context_window(md, m.start(), before=True)
                ctx_a = meaningful_context_window(md, m.end(), before=False)
                dec = resolver.resolve(context_before=ctx_b, context_after=ctx_a)
                if dec.page is not None and dec.bbox is not None:
                    if dec.crop_class not in {"likely_prose", "likely_table"}:
                        return True
    except Exception:
        return True
    return False
