# -*- coding: utf-8 -*-
"""k3 Round-1：16 篇 corpus geometry + formula 批跑（t0.md）。

用法:
  python scripts/run_k3_geometry_batch.py
  python scripts/run_k3_geometry_batch.py --geometry-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

from app.formula.config import formula_config_for_deepseek_limited_production
from app.formula.equation_identity import NOT_DECODED_RE, meaningful_context_window
from app.formula.geometry import FormulaGeometryResolver
from app.formula.pipeline import FormulaPipeline
from app.formula.session import FormulaRecoverySession
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

CORPUS_STEMS = [
    "O-027_Inoue2026_TNA",
    "以活动为中心的在线课程学习结果影响因素实证研究",
    "3785022.3785030",
    "Course-Level_Clustering_to_Enhance_Dropout_Prediction_Accuracy",
    "en_O-028_Almazroei2026_SHAP_LIME",
    "O-001_Kuzilek2017_DataPaper",
    "O-003_Peach2019_DataDrivenClustering",
    "O-009_Qiu2022_ScientificReports",
    "O-014_Cohausz2023_EDM",
    "O-016_Howard2025_ouladFormat",
    "O-018_Abdo2025_Stacking_SHAP",
    "O-020_Wu2026_PLOS",
    "O-020_Wu2026_PLOS_OA_XML_readable_snapshot",
    "O-024_Le2026_LEAP_arXiv",
    "O-025_daSilva2026_Survival_arXiv",
    "O-026_Lagun2026_DeadlineInitiation",
]


def _bench_root() -> Path:
    return Path(os.environ.get("PDF2MD_BENCH_ROOT") or (ROOT / "input"))


def _corpus_pdfs() -> list[Path]:
    root = _bench_root()
    pdfs: list[Path] = []
    for stem in CORPUS_STEMS:
        hits = sorted(root.rglob(f"{stem}.pdf"))
        if hits:
            pdfs.append(hits[0])
    return pdfs


def _find_raw_md(pdf: Path, cache_dir: Path | None = None) -> Path | None:
    stem = pdf.stem
    candidates = []
    if cache_dir is not None:
        candidates.append(cache_dir / stem / f"{stem}.raw.md")
    candidates.extend(
        [
            ROOT / "logs" / "experiment" / stem / f"{stem}.raw.md",
            _bench_root() / stem / f"{stem}.raw.md",
            pdf.parent / stem / f"{stem}.raw.md",
            pdf.with_suffix(".raw.md"),
        ]
    )
    for c in candidates:
        if c.is_file():
            return c
    return None


def _latest_benchmark_raw(stem: str, exclude: Path | None = None) -> Path | None:
    hits = [
        p
        for p in BENCHMARK_RUNS.glob(f"**/{stem}.raw.md")
        if p.is_file()
        and (exclude is None or exclude not in p.parents)
    ]
    if not hits:
        return None
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0]


def _mirror_raw_to_experiment(raw_md: Path, stem: str) -> None:
    exp = ROOT / "logs" / "experiment" / stem
    exp.mkdir(parents=True, exist_ok=True)
    dest = exp / f"{stem}.raw.md"
    if raw_md.resolve() == dest.resolve():
        return
    import shutil

    shutil.copy2(raw_md, dest)


def _ensure_raw_md(
    pdf: Path,
    cache_dir: Path,
    *,
    reuse_raw: bool = False,
    raw_path: Path | None = None,
) -> Path | None:
    if raw_path is not None and raw_path.is_file():
        print(f"  [reuse-raw] {raw_path}", flush=True)
        return raw_path
    if reuse_raw:
        found = _find_raw_md(pdf, cache_dir) or _latest_benchmark_raw(
            pdf.stem, exclude=cache_dir
        )
        if found is not None:
            print(f"  [reuse-raw] {found}", flush=True)
            return found
        print("  [reuse-raw] miss, converting", flush=True)
    local = cache_dir / pdf.stem / f"{pdf.stem}.raw.md"
    if local.is_file():
        return local
    try:
        from app.engines import docling_engine

        out = cache_dir / pdf.stem
        out.mkdir(parents=True, exist_ok=True)
        print(f"  [docling] {pdf.name}", flush=True)
        parsed = docling_engine.convert_pdf(
            pdf,
            out,
            keep_images=False,
            keep_tables=True,
            keep_formulas=True,
            ocr_mode="auto",
            images_scale=2.0,
            image_path_mode="relative",
            progress=lambda m: print(f"    {m}", flush=True),
        )
        if parsed.markdown_path.is_file():
            _mirror_raw_to_experiment(parsed.markdown_path, pdf.stem)
            return parsed.markdown_path
    except Exception as e:
        print(f"  [docling-fail] {pdf.name}: {e}", flush=True)
    return None


def geometry_only_metrics(pdf: Path, md: str) -> dict:
    slots = list(NOT_DECODED_RE.finditer(md))
    resolved = 0
    formula_crop = 0
    prose_crop = 0
    table_crop = 0
    details: list[dict] = []
    with FormulaRecoverySession(pdf) as sess:
        resolver = FormulaGeometryResolver(sess.pdf_doc, sess.anchor_index)
        for i, m in enumerate(slots):
            ctx_b = meaningful_context_window(md, m.start(), before=True)
            ctx_a = meaningful_context_window(md, m.end(), before=False)
            dec = resolver.resolve(context_before=ctx_b, context_after=ctx_a)
            if dec.page is not None and dec.bbox is not None:
                resolved += 1
                h = dec.bbox[3] - dec.bbox[1]
                if dec.crop_class == "likely_formula":
                    formula_crop += 1
                elif dec.crop_class == "likely_prose":
                    prose_crop += 1
                elif dec.crop_class == "likely_table":
                    table_crop += 1
            details.append(
                {
                    "slot": i,
                    "resolved": dec.page is not None,
                    "source": dec.source,
                    "crop_class": dec.crop_class,
                    "height_pt": round((dec.bbox[3] - dec.bbox[1]) if dec.bbox else 0, 1),
                    "confidence": dec.confidence,
                }
            )
    n = max(1, len(slots))
    return {
        "pdf": str(pdf),
        "not_decoded_slots": len(slots),
        "bbox_resolved_rate": round(resolved / n, 4) if slots else 1.0,
        "crop_formula_rate": round(formula_crop / n, 4) if slots else 1.0,
        "crop_prose_rate": round(prose_crop / n, 4),
        "crop_table_rate": round(table_crop / n, 4),
        "details": details,
    }


def run_one(
    pdf: Path,
    *,
    geometry_only: bool,
    out_dir: Path,
    reuse_raw: bool = False,
    raw_path: Path | None = None,
) -> dict:
    stem = pdf.stem
    raw_md = _ensure_raw_md(pdf, out_dir, reuse_raw=reuse_raw, raw_path=raw_path)
    row: dict = {"stem": stem, "pdf_exists": pdf.is_file(), "raw_md": str(raw_md) if raw_md else None}
    if not pdf.is_file():
        row["error"] = "pdf_missing"
        return row
    if raw_md is None:
        row["error"] = "raw_md_unavailable"
        return row

    md = raw_md.read_text(encoding="utf-8")
    t0 = time.perf_counter()
    row.update(geometry_only_metrics(pdf, md))
    if geometry_only:
        row["seconds"] = round(time.perf_counter() - t0, 3)
        return row

    from app.ocr.deepseek_worker_client import (
        get_deepseek_worker_client,
        prepare_document_worker_session,
    )

    client = get_deepseek_worker_client()
    prepare_document_worker_session(client)
    warm = client.warmup_async()
    warm_timeout = float(getattr(client, "load_timeout_seconds", 300) or 300)
    if warm.is_alive():
        warm.join(timeout=warm_timeout)
    cfg = formula_config_for_deepseek_limited_production(fallback_mode="clean")
    fres = FormulaPipeline(cfg).process_markdown(md, pdf_path=pdf)
    row["seconds"] = round(time.perf_counter() - t0, 3)
    rep = fres.report
    wb = rep.writeback or {}
    sh = rep.deepseek_shadow or {}
    sm = sh.get("summary") or {}
    row.update(
        {
            "corrupted": rep.corrupted_formula_count,
            "recovery_attempted": rep.recovery_attempted_count,
            "recovery_success": rep.recovery_success_count,
            "wb_applied": wb.get("applied_count"),
            "shadow_accepted": sm.get("accepted"),
            "shadow_rejected": sm.get("rejected"),
            "failure_classes": sm.get("failure_class_counts"),
            "geometry_qa_count": len(rep.geometry_qa or []),
        }
    )
    doc_out = out_dir / stem
    doc_out.mkdir(parents=True, exist_ok=True)
    qa_path = doc_out / f"{stem}.formula_qa.json"
    qa_path.write_text(
        json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 镜像到 logs/experiment 便于与 GUI 批对齐
    exp_dir = ROOT / "logs" / "experiment" / stem
    exp_dir.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy2(qa_path, exp_dir / qa_path.name)
    if raw_md is not None and Path(raw_md).is_file():
        _mirror_raw_to_experiment(Path(raw_md), stem)
    (doc_out / f"{stem}.md").write_text(fres.markdown, encoding="utf-8")
    return row


def _enrich_failure_context(
    fail: dict,
    md: str | None,
    shadow_by_page: dict[int, list[dict]],
) -> tuple[str, str, str]:
    """从 raw.md / shadow 补全 replay 用的 context_after 与 eq 编号。"""
    ctx_b = str(fail.get("context_before") or "")
    ctx_a = str(fail.get("context_after") or "")
    eq = str(fail.get("equation_number") or fail.get("eq_number") or "")
    page = fail.get("page")

    if md and ctx_b and not ctx_a:
        tail = ctx_b[-min(80, len(ctx_b)) :]
        pos = md.rfind(tail)
        if pos >= 0:
            anchor = pos + len(tail)
            m_nd = NOT_DECODED_RE.search(md, anchor)
            if m_nd and m_nd.start() - anchor < 120:
                anchor = m_nd.end()
            ctx_a = meaningful_context_window(md, anchor, before=False, window=300)

    if not eq and page is not None:
        bbox = fail.get("bbox")
        for row in shadow_by_page.get(int(page), []):
            if eq:
                break
            if row.get("eq_number"):
                if not bbox:
                    eq = str(row["eq_number"])
                    break
                row_bbox = row.get("bbox")
                if row_bbox and len(row_bbox) == 4 and len(bbox) == 4:
                    dy = abs(float(row_bbox[1]) - float(bbox[1]))
                    if dy < 8.0:
                        eq = str(row["eq_number"])
                        break
    return ctx_b, ctx_a, eq


def _shadow_rows_by_page(qa: dict) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    shadow = qa.get("deepseek_shadow") or {}
    for pg in shadow.get("pages") or []:
        pi = int(pg.get("page") or 0)
        rows = list(pg.get("candidates") or [])
        if rows:
            out[pi] = rows
    return out


def replay_from_formula_qa(pdf: Path, qa_path: Path, *, raw_md_path: Path | None = None) -> dict:
    import json

    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    md: str | None = None
    if raw_md_path and raw_md_path.is_file():
        md = raw_md_path.read_text(encoding="utf-8")
    else:
        stem = pdf.stem
        for cand in (
            ROOT / "logs" / "experiment" / stem / f"{stem}.raw.md",
            qa_path.parent / f"{stem}.raw.md",
        ):
            if cand.is_file():
                md = cand.read_text(encoding="utf-8")
                break
    shadow_by_page = _shadow_rows_by_page(qa)
    fails = qa.get("formula_failures") or []
    slots = [f for f in fails if f.get("raw") and "not-decoded" in str(f.get("raw"))]
    resolved = formula_crop = prose_crop = table_crop = 0
    heights_v1: list[float] = []
    heights_v2: list[float] = []
    details: list[dict] = []
    from app.formula.session import formula_band_from_number

    with FormulaRecoverySession(pdf) as sess:
        resolver = FormulaGeometryResolver(sess.pdf_doc, sess.anchor_index)
        for i, f in enumerate(slots):
            ctx_b, ctx_a, eq_hint = _enrich_failure_context(f, md, shadow_by_page)
            page_hint = f.get("page")
            old_bbox = f.get("bbox")
            dec = resolver.resolve(
                context_before=ctx_b,
                context_after=ctx_a,
                equation_number=eq_hint,
                hint_page=int(page_hint) if page_hint is not None else None,
            )
            if dec.page is not None and dec.bbox is not None:
                resolved += 1
                h2 = dec.bbox[3] - dec.bbox[1]
                heights_v2.append(h2)
                if dec.crop_class == "likely_formula":
                    formula_crop += 1
                elif dec.crop_class == "likely_prose":
                    prose_crop += 1
                elif dec.crop_class == "likely_table":
                    table_crop += 1
            h1 = 0.0
            if old_bbox and len(old_bbox) == 4:
                h1 = old_bbox[3] - old_bbox[1]
                heights_v1.append(h1)
            details.append(
                {
                    "slot": i,
                    "page": page_hint,
                    "resolved": dec.page is not None,
                    "source": dec.source,
                    "crop_class": dec.crop_class,
                    "height_v1_pt": round(h1, 1),
                    "height_v2_pt": round((dec.bbox[3] - dec.bbox[1]) if dec.bbox else 0, 1),
                }
            )
    n = max(1, len(slots))
    return {
        "stem": pdf.stem,
        "mode": "replay_formula_qa",
        "not_decoded_slots": len(slots),
        "bbox_resolved_rate": round(resolved / n, 4),
        "crop_formula_rate": round(formula_crop / n, 4),
        "crop_prose_rate": round(prose_crop / n, 4),
        "crop_table_rate": round(table_crop / n, 4),
        "avg_crop_height_v1": round(sum(heights_v1) / max(1, len(heights_v1)), 1),
        "avg_crop_height_v2": round(sum(heights_v2) / max(1, len(heights_v2)), 1),
        "details": details,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry-only", action="store_true", help="仅 geometry 预检，不跑 DeepSeek")
    ap.add_argument(
        "--replay-qa",
        action="store_true",
        help="用 logs/experiment 既有 formula_qa.formula_failures 回放 geometry",
    )
    ap.add_argument(
        "--reuse-raw",
        action="store_true",
        help="复用已有 raw.md（logs/experiment 或最近一次批跑），不重跑 Docling",
    )
    args = ap.parse_args()
    ensure_dirs()
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_dir = BENCHMARK_RUNS / f"k3_round1_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    corpus = _corpus_pdfs()
    for i, p in enumerate(corpus):
        pdf = Path(p)
        print(f"== {pdf.name} ==", flush=True)
        if args.replay_qa:
            qa = ROOT / "logs" / "experiment" / pdf.stem / f"{pdf.stem}.formula_qa.json"
            if qa.is_file() and pdf.is_file():
                rows.append(replay_from_formula_qa(pdf, qa))
            else:
                rows.append({"stem": pdf.stem, "error": "qa_or_pdf_missing"})
        else:
            rows.append(
                run_one(
                    pdf,
                    geometry_only=args.geometry_only,
                    out_dir=out_dir,
                    reuse_raw=args.reuse_raw,
                )
            )
        if (
            not args.geometry_only
            and not args.replay_qa
            and i + 1 < len(corpus)
        ):
            from app.ocr.deepseek_worker_client import cooldown_between_batch_documents

            cooldown_between_batch_documents()

    summary = {
        "run_id": run_id,
        "geometry_only": args.geometry_only,
        "docs": len(rows),
        "bbox_resolved_avg": round(
            sum(r.get("bbox_resolved_rate", 0) for r in rows) / max(1, len(rows)), 4
        ),
        "rows": rows,
    }
    out_path = out_dir / "k3_geometry_summary.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
