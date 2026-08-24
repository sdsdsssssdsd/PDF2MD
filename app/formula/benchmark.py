"""Formula Benchmark Lab：配置矩阵跑 OCR，不进日常转换主链路。

用于回答：2× vs 3×、padding、contrast 在你的论文 corpus 上有没有收益。
结果写入 debug/formula_benchmark/runs/。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Callable, Iterable

from app.formula.config import FormulaConfig
from app.formula.gain import evaluate_recovery_gain
from app.formula.preprocess import apply_named_preprocess, to_pil_image
from app.formula.recognizer import FormulaRecognizer, build_recognizer
from app.formula.session import FormulaRecoverySession
from app.formula.validator import validate_latex
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

ProgressCB = Callable[[str], None]

PADDING_PRESETS: dict[str, tuple[float, float]] = {
    "small": (0.06, 0.15),
    "medium": (0.12, 0.30),
    "large": (0.22, 0.55),
}

SCALE_CHOICES = (1.5, 2.0, 2.5, 3.0)
PREPROCESS_CHOICES = ("original", "contrast", "sharpen")
RECOGNIZER_CHOICES = ("unimernet", "pix2tex")


@dataclass
class BenchmarkConfig:
    scale: float = 2.0
    padding: str = "medium"
    preprocess: str = "original"
    recognizer: str = "unimernet"

    @property
    def label(self) -> str:
        return f"{self.scale:g}× {self.padding} {self.preprocess}"

    def pad_xy(self) -> tuple[float, float]:
        return PADDING_PRESETS.get(self.padding, PADDING_PRESETS["medium"])


@dataclass
class BenchmarkCase:
    pdf_path: str
    page: int = 0  # 0-based
    eq_number: str = ""
    bbox: tuple[float, float, float, float] | None = None
    parser_latex: str = ""
    context_before: str = ""
    context_after: str = ""
    gold_latex: str = ""


@dataclass
class BenchmarkRow:
    config_label: str
    scale: float
    padding: str
    preprocess: str
    recognizer: str
    ocr_seconds: float
    latex: str = ""
    error: str = ""
    validator_score: float = 0.0
    corruption_score: float = 1.0
    context_overlap: float = 0.0
    gain: float = 0.0
    decision: str = "reject"  # accept | reject
    reasons: list[str] = field(default_factory=list)
    gold_match: str = "—"  # yes | no | —

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def expand_matrix(
    *,
    scales: Iterable[float] | None = None,
    paddings: Iterable[str] | None = None,
    preprocesses: Iterable[str] | None = None,
    recognizers: Iterable[str] | None = None,
) -> list[BenchmarkConfig]:
    scales = tuple(scales) if scales is not None else (2.0, 2.5)
    paddings = tuple(paddings) if paddings is not None else ("medium",)
    preprocesses = tuple(preprocesses) if preprocesses is not None else ("original",)
    recognizers = tuple(recognizers) if recognizers is not None else ("unimernet",)
    out: list[BenchmarkConfig] = []
    for scale, pad, prep, rec in product(scales, paddings, preprocesses, recognizers):
        out.append(
            BenchmarkConfig(
                scale=float(scale),
                padding=str(pad),
                preprocess=str(prep),
                recognizer=str(rec),
            )
        )
    return out


def compact_latex(text: str) -> str:
    s = (text or "").strip()
    s = s.replace("$$", "").replace("$", "")
    s = re.sub(r"\s+", "", s)
    return s


def gold_match(ocr: str, gold: str) -> str:
    if not (gold or "").strip():
        return "—"
    a, b = compact_latex(ocr), compact_latex(gold)
    if not a or not b:
        return "no"
    if a == b:
        return "yes"
    # 宽松：去掉常见包装后仍包含核心
    if a in b or b in a:
        return "yes"
    return "no"


def crop_formula_image(
    session: FormulaRecoverySession,
    page_index: int,
    bbox: tuple[float, float, float, float],
    *,
    scale: float,
    pad_x: float,
    pad_y: float,
):
    import pymupdf

    doc = session.pdf_doc
    if doc is None:
        raise RuntimeError("pdf_not_open")
    page = doc[page_index]
    x0, y0, x1, y1 = bbox
    w, h = max(1.0, x1 - x0), max(1.0, y1 - y0)
    x0 = max(0.0, x0 - w * pad_x)
    x1 = min(float(page.rect.width), x1 + w * pad_x)
    y0 = max(0.0, y0 - h * pad_y)
    y1 = min(float(page.rect.height), y1 + h * pad_y)
    clip = pymupdf.Rect(x0, y0, x1, y1)
    s = max(1.0, min(float(scale), 4.0))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=clip, alpha=False)
    return to_pil_image(pix) or pix


def resolve_case_bbox(
    case: BenchmarkCase, session: FormulaRecoverySession
) -> tuple[int, tuple[float, float, float, float]]:
    if case.bbox is not None:
        return case.page, case.bbox
    if case.eq_number:
        hit = session.formula_bbox_from_eq(case.eq_number, page=case.page)
        if hit:
            return hit
        hit = session.formula_bbox_from_eq(case.eq_number)
        if hit:
            return hit
    raise RuntimeError("no_bbox")


def pareto_summary(rows: list[BenchmarkRow]) -> dict[str, Any]:
    n = len(rows)
    accepts = [r for r in rows if r.decision == "accept"]
    gold_yes = [r for r in rows if r.gold_match == "yes"]
    mean_t = (sum(r.ocr_seconds for r in rows) / n) if n else 0.0
    by_scale: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = f"{r.scale:g}"
        slot = by_scale.setdefault(
            key, {"n": 0, "accept": 0, "gold_yes": 0, "seconds": 0.0}
        )
        slot["n"] += 1
        slot["seconds"] += r.ocr_seconds
        if r.decision == "accept":
            slot["accept"] += 1
        if r.gold_match == "yes":
            slot["gold_yes"] += 1
    for slot in by_scale.values():
        nn = max(1, slot["n"])
        slot["accept_rate"] = round(slot["accept"] / nn, 3)
        slot["mean_seconds"] = round(slot["seconds"] / nn, 3)
        del slot["seconds"]
    fastest_accept = None
    if accepts:
        best = min(accepts, key=lambda r: r.ocr_seconds)
        fastest_accept = {"label": best.config_label, "ocr_seconds": best.ocr_seconds}
    return {
        "n": n,
        "accept_n": len(accepts),
        "accept_rate": round(len(accepts) / n, 3) if n else 0.0,
        "gold_match_n": len(gold_yes),
        "mean_ocr_seconds": round(mean_t, 3),
        "fastest_accept": fastest_accept,
        "by_scale": by_scale,
        "note": (
            "accept_rate 是 GainEvaluator 通过率，不是人工正确率；"
            "有 gold_latex 时看 gold_match_n。"
        ),
    }


def run_benchmark(
    case: BenchmarkCase,
    configs: list[BenchmarkConfig],
    *,
    recognizer: FormulaRecognizer | None = None,
    progress: ProgressCB | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """对同一公式区域跑配置矩阵。Recognizer 忽略 context。"""
    ensure_dirs()
    pdf = Path(case.pdf_path)
    if not pdf.exists():
        raise FileNotFoundError(str(pdf))
    cfg = FormulaConfig()
    rows: list[BenchmarkRow] = []
    rec_cache: dict[str, FormulaRecognizer] = {}

    def emit(msg: str) -> None:
        if progress:
            progress(msg)

    with FormulaRecoverySession(pdf, cfg) as session:
        page, bbox = resolve_case_bbox(case, session)
        emit(f"bbox page={page} {tuple(round(x, 1) for x in bbox)}")
        before_q = None
        if case.parser_latex.strip():
            vr0 = validate_latex(
                case.parser_latex,
                cfg,
                context_before=case.context_before,
                context_after=case.context_after,
            )
            before_q = vr0.quality

        for i, c in enumerate(configs, start=1):
            if should_cancel and should_cancel():
                emit("已取消")
                break
            emit(f"{i}/{len(configs)} {c.label}")
            pad_x, pad_y = c.pad_xy()
            try:
                image = crop_formula_image(
                    session, page, bbox, scale=c.scale, pad_x=pad_x, pad_y=pad_y
                )
                image = apply_named_preprocess(image, c.preprocess)
            except Exception as e:
                rows.append(
                    BenchmarkRow(
                        config_label=c.label,
                        scale=c.scale,
                        padding=c.padding,
                        preprocess=c.preprocess,
                        recognizer=c.recognizer,
                        ocr_seconds=0.0,
                        error=f"crop:{e}",
                    )
                )
                continue

            rec = recognizer
            if rec is None:
                rec = rec_cache.get(c.recognizer)
                if rec is None:
                    rec = build_recognizer(FormulaConfig(recognizer_primary=c.recognizer))
                    rec_cache[c.recognizer] = rec

            t0 = time.perf_counter()
            result = rec.recognize(image, context=None)
            ocr_sec = time.perf_counter() - t0
            latex = (result.latex or "") if result.success else ""
            err = result.error or ""
            if not latex:
                rows.append(
                    BenchmarkRow(
                        config_label=c.label,
                        scale=c.scale,
                        padding=c.padding,
                        preprocess=c.preprocess,
                        recognizer=getattr(rec, "name", c.recognizer),
                        ocr_seconds=round(ocr_sec, 3),
                        error=err or "empty_output",
                        gold_match=gold_match("", case.gold_latex),
                    )
                )
                continue
            vr = validate_latex(
                latex,
                cfg,
                context_before=case.context_before,
                context_after=case.context_after,
            )
            q = vr.quality
            gain = evaluate_recovery_gain(
                before_quality=before_q,
                after_quality=q,
                before_latex=case.parser_latex,
                after_latex=latex,
                context_before=case.context_before,
                context_after=case.context_after,
                after_valid=bool(latex) and vr.valid,
            )
            rows.append(
                BenchmarkRow(
                    config_label=c.label,
                    scale=c.scale,
                    padding=c.padding,
                    preprocess=c.preprocess,
                    recognizer=getattr(rec, "name", c.recognizer),
                    ocr_seconds=round(ocr_sec, 3),
                    latex=latex,
                    error=err,
                    validator_score=round(float(q.syntax_score) if q else 0.0, 3),
                    corruption_score=round(float(q.corruption_score) if q else 1.0, 3),
                    context_overlap=round(gain.token_overlap, 3),
                    gain=round(gain.gain, 3),
                    decision="accept" if gain.accept else "reject",
                    reasons=list(gain.reasons),
                    gold_match=gold_match(latex, case.gold_latex),
                )
            )

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "case": {
            "pdf_path": str(pdf),
            "page": page,
            "eq_number": case.eq_number,
            "bbox": list(bbox),
            "parser_latex": case.parser_latex,
            "context_before": case.context_before,
            "context_after": case.context_after,
            "gold_latex": case.gold_latex,
        },
        "rows": [r.to_dict() for r in rows],
        "pareto": pareto_summary(rows),
    }
    return payload


def save_benchmark_run(payload: dict[str, Any], dest_dir: Path | None = None) -> Path:
    ensure_dirs()
    out_dir = dest_dir or BENCHMARK_RUNS
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(str(payload.get("case", {}).get("pdf_path") or "run")).stem
    eq = str(payload.get("case", {}).get("eq_number") or "eq")
    path = out_dir / f"{ts}_{stem}_eq{eq}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_pdf_equations(pdf_path: str | Path) -> dict[str, Any]:
    """列出 PDF 页数与右侧 (n) 方程编号，供实验室左侧选择。"""
    pdf = Path(pdf_path)
    with FormulaRecoverySession(pdf, FormulaConfig()) as session:
        doc = session.pdf_doc
        if doc is None:
            raise RuntimeError("pdf_open_failed")
        by_page: dict[int, list[str]] = {}
        for i in range(len(doc)):
            nums = session.anchor_index.numbers_on_page(i)
            if nums:
                by_page[i] = nums
        return {
            "page_count": len(doc),
            "by_page": by_page,
            "all": session.anchor_index.all_numbers(),
        }


def preview_crop(case: BenchmarkCase, config: BenchmarkConfig | None = None):
    """只裁图、不 OCR，给预览用。"""
    cfg = config or BenchmarkConfig(scale=2.0, padding="medium", preprocess="original")
    pdf = Path(case.pdf_path)
    with FormulaRecoverySession(pdf, FormulaConfig()) as session:
        page, bbox = resolve_case_bbox(case, session)
        pad_x, pad_y = cfg.pad_xy()
        image = crop_formula_image(
            session, page, bbox, scale=cfg.scale, pad_x=pad_x, pad_y=pad_y
        )
        image = apply_named_preprocess(image, cfg.preprocess)
        return image, page, bbox
