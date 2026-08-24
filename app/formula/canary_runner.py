"""Phase 5A：对 manifest 中 PDF 批量跑 Limited Production（冻结识别参数）。"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.formula.canary import (
    CANARY_DIR,
    CANARY_MANIFEST,
    CanaryDocMetrics,
    aggregate_canary,
    ensure_canary_dirs,
    evaluate_canary_gates,
    human_review_template,
)
from app.formula.config import FormulaConfig, formula_config_for_deepseek_limited_production
from app.formula.session import FormulaRecoverySession
from app.formula.types import FormulaCandidate, FormulaLifecycle
from app.formula.versions import attach_versions
from app.formula.writeback import (
    FormulaWritebackManager,
    RecoveryWritebackItem,
    register_display_formulas_by_order,
)
from app.ocr.cost_model import RecoveryCostModel, default_profile_path
from app.ocr.deepseek_ocr2 import DeepSeekOCR2Recognizer
from app.ocr.shadow import ShadowRecoveryRunner
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

ProgressCB = Callable[[str], None]


def _guess_coverage(session: FormulaRecoverySession, eq_count: int) -> dict[str, str]:
    """粗覆盖标签（启发式，供抽样多样性检查，非版面金标准）。"""
    layout = "unknown"
    source_type = "digital_pdf"
    try:
        doc = session.pdf_doc
        if doc is None or len(doc) == 0:
            return {"layout": layout, "source_type": source_type, "formula_density": "none"}
        page = doc[min(1, len(doc) - 1)]
        w = float(page.rect.width)
        # 双栏粗判：中缝附近词少、左右有字
        words = page.get_text("words") or []
        mid = w * 0.5
        left = sum(1 for x in words if len(x) >= 5 and x[2] < mid - 20)
        right = sum(1 for x in words if len(x) >= 5 and x[0] > mid + 20)
        gutter = sum(1 for x in words if len(x) >= 5 and abs(((x[0] + x[2]) / 2) - mid) < 15)
        if left > 20 and right > 20 and gutter < max(5, (left + right) * 0.05):
            layout = "two_column"
        else:
            layout = "single_column"
        # 扫描件粗判：图片占页多且文字少
        imgs = page.get_images() or []
        if len(words) < 30 and len(imgs) >= 1:
            source_type = "scanned_or_image_heavy"
    except Exception:
        pass
    if eq_count <= 0:
        density = "none"
    elif eq_count <= 3:
        density = "few_formulas"
    elif eq_count <= 10:
        density = "moderate_formulas"
    else:
        density = "many_formulas"
    return {"layout": layout, "source_type": source_type, "formula_density": density}


def _build_candidates(
    session: FormulaRecoverySession, *, max_n: int
) -> list[FormulaCandidate]:
    idx = session.anchor_index
    nums = idx.all_numbers() if idx else []
    out: list[FormulaCandidate] = []
    for n in nums:
        if len(out) >= max_n:
            break
        hit = session.formula_bbox_from_eq(n)
        if not hit:
            continue
        page, bbox = hit
        out.append(
            FormulaCandidate(
                text=r"\quad\quad\quad\quad garbage",
                raw_text=r"\quad\quad\quad\quad garbage",
                page=page,
                bbox=bbox,
                context_before=f"Eq. ({n}):",
                source_type="parser_math",
                display_mode="display",
                lifecycle=FormulaLifecycle.CORRUPTED,
                status="corrupted",
                issues=["canary_anchor_recovery"],
            )
        )
    return out


def run_one_document(
    pdf: Path,
    *,
    recognizer: DeepSeekOCR2Recognizer,
    cost: RecoveryCostModel,
    cfg: FormulaConfig,
    max_formulas: int = 8,
) -> tuple[CanaryDocMetrics, dict[str, Any]]:
    ensure_canary_dirs()
    doc_id = pdf.stem
    t0 = time.perf_counter()
    load0 = DeepSeekOCR2Recognizer.model_load_count()

    writebacks_for_review: list[dict[str, Any]] = []
    metrics = CanaryDocMetrics(doc_id=doc_id, source=str(pdf))

    with FormulaRecoverySession(pdf, cfg) as session:
        cands = _build_candidates(session, max_n=max_formulas)
        metrics.coverage = _guess_coverage(session, len(cands))
        metrics.formula_candidates = len(cands)
        metrics.corrupted_detected = len(cands)

        if not cands:
            metrics.total_document_seconds = time.perf_counter() - t0
            metrics.notes = "no_equation_anchors"
            return metrics, {"writebacks": [], "shadow": None, "writeback": None}

        runner = ShadowRecoveryRunner(
            config=cfg,
            recognizer=recognizer,
            cost_model=cost,
        )
        # limited production 配置里 shadow 已开
        shadow = runner.run(cands, session=session, pdf_path=pdf)
        sh = shadow.summary or {}
        metrics.deepseek_recovery_attempted = int(sh.get("ocr_calls") or 0)
        metrics.recovery_accepted = int(sh.get("accepted") or 0)
        metrics.recovery_rejected = int(sh.get("rejected") or 0)
        metrics.ocr_calls = int(sh.get("ocr_calls") or 0)
        metrics.ocr_seconds = float(sh.get("ocr_inference_seconds") or 0)
        metrics.total_recovery_seconds = float(sh.get("actual_seconds") or 0)
        metrics.mode_counts = dict(sh.get("mode_counts") or {})
        metrics.unresolved_formulas = max(
            0, len(cands) - metrics.recovery_accepted
        )

        # 写回：合成 MD + candidate_id 精确替换（审计/可复核，不碰用户产出目录）
        ids: list[str] = []
        items: list[RecoveryWritebackItem] = []
        for row in sh.get("would_replace") or []:
            eq = str(row.get("eq_number") or "x")
            page = row.get("page")
            cid = f"page{page}_eq{eq}"
            ids.append(cid)
            items.append(
                RecoveryWritebackItem(
                    candidate_id=cid,
                    recovered_latex=str(row.get("recovered") or ""),
                    gate_accepted=bool(row.get("gate_accepted")),
                    would_replace=bool(row.get("would_replace")),
                    gate_reason=str(row.get("gate_reason") or "gain_accept"),
                    original=str(row.get("original") or ""),
                    scheduler_mode=str(row.get("scheduler_mode") or "formula_batch"),
                    page=int(page) if page is not None else None,
                )
            )
            writebacks_for_review.append(
                {
                    "doc_id": doc_id,
                    "candidate_id": cid,
                    "page": page,
                    "eq_number": eq,
                    "scheduler_mode": row.get("scheduler_mode"),
                    "gate_accepted": row.get("gate_accepted"),
                    "would_replace": row.get("would_replace"),
                    "original": row.get("original"),
                    "recovered": row.get("recovered"),
                    "human_correct": None,  # 人工填写 true/false
                    "false_reject_sample": None,
                }
            )

        wb_report = None
        if ids:
            parts = [f"# canary {doc_id}\n"]
            for cid in ids:
                parts.append(f"\n{cid}\n\n$$\\quad\\quad garbage$$\n")
            md = "".join(parts)
            from app.formula.writeback import register_display_formulas_by_order

            reg = register_display_formulas_by_order(md, ids)
            wb_report = FormulaWritebackManager(cfg).apply(
                md,
                items,
                reg,
                unresolved_formula_count=metrics.unresolved_formulas,
            )
            metrics.writeback_applied = int(wb_report.applied_count)
            metrics.writeback_rollback = int(wb_report.rolled_back_count)
            metrics.writeback_budget_exceeded = sum(
                1
                for e in wb_report.entries
                if e.skip_reason == "writeback_budget_exceeded"
            )
            metrics.formula_incomplete = wb_report.document_status == "formula_incomplete" or (
                metrics.unresolved_formulas > 0
            )
            # 写出可 diff 的 MD
            out_md = CANARY_DIR / "docs" / f"{doc_id}.writeback.md"
            out_md.write_text(wb_report.markdown_after, encoding="utf-8")

    load1 = DeepSeekOCR2Recognizer.model_load_count()
    metrics.model_load_count = max(0, load1 - load0)
    metrics.total_document_seconds = time.perf_counter() - t0
    # 未人工复核前不填 false_accept
    metrics.false_accept = None
    metrics.true_accept = None
    metrics.false_reject = None

    detail = {
        "shadow": shadow.to_dict() if cands else None,
        "writeback": wb_report.to_dict() if wb_report else None,
        "writebacks_for_review": writebacks_for_review,
        "coverage": metrics.coverage,
    }
    return metrics, detail


def run_canary_batch(
    *,
    manifest_path: Path | None = None,
    model_name: str,
    device: str = "cuda:0",
    max_formulas_per_doc: int = 8,
    progress: ProgressCB | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    ensure_canary_dirs()
    man_path = manifest_path or CANARY_MANIFEST
    man = json.loads(man_path.read_text(encoding="utf-8"))
    docs_spec = list(man.get("documents") or [])
    if limit is not None:
        docs_spec = docs_spec[: int(limit)]

    cfg = formula_config_for_deepseek_limited_production(
        deepseek_shadow_enabled=True,
        deepseek_max_writebacks_per_document=max_formulas_per_doc,
        deepseek_max_total_recovery_seconds=270.0,
    )
    # Shadow runner 要求 shadow enabled
    assert cfg.deepseek_shadow_enabled

    cost = RecoveryCostModel(
        profile_path=default_profile_path(),
        auto_load=True,
        auto_save=True,
        max_outlier_multiplier=3.0,
    )
    # 不 reset 模型：整批共享一次 load；每文档记录 delta load count
    recognizer = DeepSeekOCR2Recognizer(
        model_name=model_name,
        device=device,
        dtype="bf16",
        base_size=1024,
        image_size=640,
        crop_mode=True,
        allow_cpu=False,
    )

    metrics_list: list[CanaryDocMetrics] = []
    all_reviews: list[dict[str, Any]] = []
    coverage_hist: dict[str, int] = {}

    def emit(m: str) -> None:
        if progress:
            progress(m)

    for i, spec in enumerate(docs_spec):
        pdf = Path(spec.get("path") or "")
        doc_id = str(spec.get("doc_id") or pdf.stem)
        emit(f"[{i+1}/{len(docs_spec)}] {doc_id}")
        if not pdf.exists():
            m = CanaryDocMetrics(doc_id=doc_id, source=str(pdf), notes="pdf_missing")
            metrics_list.append(m)
            continue
        try:
            met, detail = run_one_document(
                pdf,
                recognizer=recognizer,
                cost=cost,
                cfg=cfg,
                max_formulas=max_formulas_per_doc,
            )
            # merge manifest coverage hints if present
            if spec.get("layout"):
                met.coverage["layout"] = str(spec["layout"])
            if spec.get("source_type"):
                met.coverage["source_type"] = str(spec["source_type"])
            metrics_list.append(met)
            all_reviews.extend(detail.get("writebacks_for_review") or [])
            for k, v in (met.coverage or {}).items():
                key = f"{k}:{v}"
                coverage_hist[key] = coverage_hist.get(key, 0) + 1
            # per-doc artifact
            (CANARY_DIR / "docs" / f"{doc_id}.json").write_text(
                json.dumps(
                    {"metrics": met.to_dict(), "detail": detail},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            emit(f"ERROR {doc_id}: {e}")
            metrics_list.append(
                CanaryDocMetrics(doc_id=doc_id, source=str(pdf), notes=f"error:{type(e).__name__}")
            )

    summary = aggregate_canary(metrics_list)
    gates = evaluate_canary_gates(summary)
    review = human_review_template(metrics_list)
    review["writeback_items"] = all_reviews
    review["instructions"] = [
        "100% 检查 writeback_items：将 human_correct 标为 true/false。",
        "抽样 recovery_rejected / unresolved：填写 false_reject_sample。",
        "汇总 false_accept 后写回 reviews/human_scores.json 再跑 finalize。",
    ]

    review_path = CANARY_DIR / "reviews" / "writebacks_pending.json"
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = attach_versions(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "phase": "5A_full_canary",
            "frozen": ["ocr_params", "bbox", "extractor", "gate", "scheduler"],
            "manifest": str(man_path),
            "coverage_histogram": coverage_hist,
            "summary": summary,
            "gates": gates,
            "documents": [m.to_dict() for m in metrics_list],
            "human_review_path": str(review_path),
            "policy": {
                "preset": "balanced_limited_production",
                "max_formulas_per_doc": max_formulas_per_doc,
                "default_balanced_enabled": False,
            },
        }
    )
    out = BENCHMARK_RUNS / "phase5a_canary_full.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(out)
    return payload


def finalize_canary_with_human_scores(
    scores_path: Path | None = None,
    *,
    canary_full_path: Path | None = None,
) -> dict[str, Any]:
    """读取人工评分，回填 false_accept / true_accept，重算 5B 门槛。"""
    ensure_canary_dirs()
    full_path = canary_full_path or (BENCHMARK_RUNS / "phase5a_canary_full.json")
    scores_path = scores_path or (CANARY_DIR / "reviews" / "human_scores.json")
    full = json.loads(full_path.read_text(encoding="utf-8"))
    if not scores_path.exists():
        raise FileNotFoundError(
            f"缺少人工评分文件：{scores_path}（请根据 writebacks_pending.json 填写）"
        )
    scores = json.loads(scores_path.read_text(encoding="utf-8"))
    # scores: {doc_id: {false_accept, true_accept, false_reject}} 或 items list
    by_doc: dict[str, dict[str, Any]] = {}
    if isinstance(scores.get("documents"), list):
        for d in scores["documents"]:
            by_doc[str(d["doc_id"])] = d
    elif isinstance(scores.get("by_doc"), dict):
        by_doc = {str(k): v for k, v in scores["by_doc"].items()}

    docs = []
    for raw in full.get("documents") or []:
        m = CanaryDocMetrics(**{k: raw[k] for k in CanaryDocMetrics.__dataclass_fields__ if k in raw})
        s = by_doc.get(m.doc_id)
        if s:
            if "false_accept" in s:
                m.false_accept = int(s["false_accept"])
            if "true_accept" in s:
                m.true_accept = int(s["true_accept"])
            if "false_reject" in s:
                m.false_reject = int(s["false_reject"])
        docs.append(m)

    # 也可从 writeback item 级 human_correct 汇总
    items = scores.get("writeback_items") or []
    if items:
        from collections import defaultdict

        fa = defaultdict(int)
        ta = defaultdict(int)
        for it in items:
            did = str(it.get("doc_id") or "")
            hc = it.get("human_correct")
            if hc is True:
                ta[did] += 1
            elif hc is False:
                fa[did] += 1
        for m in docs:
            if m.doc_id in ta or m.doc_id in fa:
                m.true_accept = ta.get(m.doc_id, 0)
                m.false_accept = fa.get(m.doc_id, 0)

    summary = aggregate_canary(docs)
    gates = evaluate_canary_gates(summary)
    payload = attach_versions(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "phase": "5A_finalized",
            "summary": summary,
            "gates": gates,
            "documents": [d.to_dict() for d in docs],
        }
    )
    out = BENCHMARK_RUNS / "phase5a_canary_final.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(out)
    return payload
