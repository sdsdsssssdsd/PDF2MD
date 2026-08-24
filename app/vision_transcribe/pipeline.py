"""VisionPipeline：调度渲染→分批→校验→合并→清理→Figure，不做网页 DOM。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.vision_transcribe.batch_ingest import (
    clear_batch_artifacts,
    ingest_raw_response,
    read_raw_response,
    write_accepted_response,
)
from app.vision_transcribe.batch_planner import plan_batches
from app.vision_transcribe.batch_validator import validate_and_write
from app.vision_transcribe.browser import create_adapter
from app.vision_transcribe.browser.base import AdapterResult, VisionWebAdapter
from app.vision_transcribe.cleaner import clean_and_write, clean_vision_markdown
from app.vision_transcribe.config import VisionConfig
from app.vision_transcribe.document_validator import validate_document
from app.vision_transcribe.figure_parser import parse_figure_markers
from app.vision_transcribe.figure_store import load_figures_json, save_figures_json
from app.vision_transcribe.figure_writeback import writeback_figures
from app.vision_transcribe.manifest import (
    VisionManifest,
    batch_dir,
    load_manifest,
    save_manifest,
    vision_dir,
)
from app.vision_transcribe.merger import merge_accepted_batches
from app.vision_transcribe.models import (
    BatchInfo,
    BatchStatus,
    FigureRecord,
    PipelineState,
    page_png_name,
)
from app.vision_transcribe.prompt_builder import write_batch_prompt
from app.vision_transcribe.prompts import PROMPT_VERSION
from app.vision_transcribe.renderer import render_pdf_to_bookfigures


LogFn = Callable[[str], None]
ProgressFn = Callable[[str, int, int], None]  # label, cur, total


@dataclass
class BatchPrep:
    batch: BatchInfo
    prompt: str
    images: list[Path]
    hint: str = ""


class VisionPipeline:
    def __init__(
        self,
        pdf_path: Path,
        output_dir: Path,
        config: VisionConfig | None = None,
        *,
        app_root: Path | None = None,
        log: LogFn | None = None,
    ) -> None:
        self.pdf_path = Path(pdf_path)
        self.output_dir = Path(output_dir)
        self.config = config or VisionConfig()
        self.app_root = app_root or Path(__file__).resolve().parents[2]
        self._log = log or (lambda _m: None)
        self.manifest: VisionManifest | None = load_manifest(self.output_dir)
        self._adapter: VisionWebAdapter | None = None

    # —— 准备 ——
    def prepare(self, *, progress: ProgressFn | None = None, cancelled=None) -> VisionManifest:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "bookfigures").mkdir(exist_ok=True)
        (self.output_dir / "images").mkdir(exist_ok=True)
        vision_dir(self.output_dir).mkdir(exist_ok=True)

        m = self.manifest or VisionManifest()
        m.pdf = self.pdf_path.name
        m.render_scale = self.config.render_scale
        m.batch_size = self.config.batch_size
        m.prompt_version = PROMPT_VERSION
        m.browser_mode = self.config.browser_mode
        m.state = PipelineState.RENDERING.value
        save_manifest(self.output_dir, m)
        self.manifest = m

        def _prog(cur: int, total: int) -> None:
            if progress:
                progress("render", cur, total)

        pages = render_pdf_to_bookfigures(
            self.pdf_path,
            self.output_dir / "bookfigures",
            scale=self.config.render_scale,
            banner_px=self.config.label_banner_px,
            force=self.config.force_rerender,
            progress=_prog,
            cancelled=cancelled,
        )
        m.set_pages(pages)
        if not m.batches:
            m.set_batches(plan_batches(len(pages), self.config.batch_size))
        elif self.config.force_rerun:
            n = m.reset_all_batches_for_rerun()
            self._clear_transcribe_artifacts(m)
            self._log(f"强制重跑：已重置全部 {n} 个批次（将重新跑视觉转录）")
        elif m.all_batches_accepted():
            self._log(
                "批次已全部 accepted，将跳过浏览器转录（直接合并/裁图）。"
                "若需完整重跑 DeepSeek，请勾选「强制重跑浏览器转录」"
            )
        else:
            # 断点续跑 / 重跑未完成：拉回 pending 并清旧回答，避免 resume 误读脏 raw
            incomplete_ids = [
                int(b["id"])
                for b in m.batches
                if str(b.get("status")) != BatchStatus.ACCEPTED.value
            ]
            reset_n = m.reset_incomplete_batches()
            if reset_n:
                for bid in incomplete_ids:
                    clear_batch_artifacts(self.output_dir, bid)
                self._log(
                    f"已重置 {reset_n} 个未完成批次为 pending（将自动重新提交浏览器）"
                )
        for b in m.get_batches():
            write_batch_prompt(batch_dir(self.output_dir, b.id), b.start_page, b.end_page)
        m.browser_mode = self.config.browser_mode
        m.state = PipelineState.READY_TO_TRANSCRIBE.value
        save_manifest(self.output_dir, m)
        self._log(f"渲染完成 {len(pages)} 页，{len(m.batches)} 个批次")
        return m

    def _ensure_manifest(self) -> VisionManifest:
        if self.manifest is None:
            self.manifest = load_manifest(self.output_dir)
        if self.manifest is None:
            raise RuntimeError("缺少 manifest，请先 prepare()")
        return self.manifest

    def get_adapter(self) -> VisionWebAdapter:
        if self._adapter is None:
            profile = self.config.resolve_profile_dir(self.app_root, self.output_dir)
            self._adapter = create_adapter(
                self.config.browser_mode,
                profile_dir=profile,
                url=self.config.deepseek_url,
                log=self._log,
            )
        return self._adapter

    def close(self) -> None:
        if self._adapter is not None:
            self._adapter.close()
            self._adapter = None

    def next_pending_batch(self) -> BatchInfo | None:
        return self._ensure_manifest().next_pending_batch()

    def prepare_batch(self, batch: BatchInfo | None = None) -> BatchPrep:
        m = self._ensure_manifest()
        b = batch or m.next_pending_batch()
        if b is None:
            raise RuntimeError("没有待处理批次")
        d = batch_dir(self.output_dir, b.id)
        prompt_path = d / "prompt.txt"
        if not prompt_path.exists():
            write_batch_prompt(d, b.start_page, b.end_page)
        prompt = prompt_path.read_text(encoding="utf-8")
        images = [
            self.output_dir / "bookfigures" / page_png_name(p)
            for p in range(b.start_page, b.end_page + 1)
        ]
        adapter = self.get_adapter()
        hint = adapter.prepare_manual_batch(
            images,
            prompt,
            bookfigures_dir=self.output_dir / "bookfigures",
        )
        m.state = PipelineState.TRANSCRIBING.value
        m.update_batch_status(b.id, BatchStatus.WAITING_RESPONSE.value)
        save_manifest(self.output_dir, m)
        return BatchPrep(batch=b, prompt=prompt, images=images, hint=hint)

    def try_auto_submit(self, batch: BatchInfo | None = None) -> AdapterResult | None:
        """Playwright 模式尝试自动提交；clipboard 模式返回 needs_user。"""
        prep = self.prepare_batch(batch)
        adapter = self.get_adapter()
        m = self._ensure_manifest()
        m.update_batch_status(prep.batch.id, BatchStatus.UPLOADING.value)
        save_manifest(self.output_dir, m)
        self._log(f"自动提交 batch {prep.batch.id}: PAGE {prep.batch.start_page}-{prep.batch.end_page}")
        result = adapter.submit_batch(prep.images, prep.prompt)
        if result.needs_user:
            m.state = PipelineState.NEEDS_USER.value
            m.update_batch_status(prep.batch.id, BatchStatus.WAITING_RESPONSE.value)
            save_manifest(self.output_dir, m)
            return result
        if not (result.markdown or "").strip() and result.message:
            raise RuntimeError(result.message)
        self.ingest_and_validate(
            prep.batch.id,
            result.markdown,
            extract_stats=result.extract_stats,
        )
        return result

    def resume_pending_submit(self) -> AdapterResult:
        """登录/验证后继续当前批次（子进程 resume）。"""
        adapter = self.get_adapter()
        resume_fn = getattr(adapter, "resume", None)
        m = self._ensure_manifest()
        waiting = next(
            (
                b
                for b in m.get_batches()
                if b.status
                in (
                    BatchStatus.WAITING_RESPONSE.value,
                    BatchStatus.UPLOADING.value,
                    BatchStatus.NEEDS_RETRY.value,
                )
            ),
            None,
        )
        if resume_fn is None:
            return self.try_auto_submit(waiting) or AdapterResult(
                markdown="", needs_user=True, message="无法 resume"
            )
        self._log("继续自动提交（resume）…")
        result = resume_fn()
        if result.needs_user:
            m.state = PipelineState.NEEDS_USER.value
            save_manifest(self.output_dir, m)
            return result
        if waiting is None:
            raise RuntimeError("resume 成功但找不到对应 batch")
        self.ingest_and_validate(
            waiting.id,
            result.markdown,
            extract_stats=result.extract_stats,
        )
        return result

    def ingest_and_validate(
        self,
        batch_id: int,
        text: str,
        *,
        extract_stats: dict[str, Any] | None = None,
    ) -> bool:
        m = self._ensure_manifest()
        batches = {b.id: b for b in m.get_batches()}
        b = batches.get(batch_id)
        if b is None:
            raise KeyError(batch_id)
        raw_path = ingest_raw_response(self.output_dir, batch_id, text)
        self._log(f"已保存 batch {batch_id} 回答 -> {raw_path}")
        if extract_stats is not None or text:
            from app.diagnostics.vision_fidelity_summary import write_batch_extract_stats

            raw = read_raw_response(self.output_dir, batch_id) or ""
            meta = dict(extract_stats or {})
            meta["chars_raw_saved"] = len(raw)
            if "chars_selected" not in meta:
                meta["chars_selected"] = len(text or "")
            write_batch_extract_stats(self.output_dir, batch_id, meta)
        m.update_batch_status(batch_id, BatchStatus.RECEIVED.value)
        m.state = PipelineState.VALIDATING_BATCH.value
        save_manifest(self.output_dir, m)

        raw = read_raw_response(self.output_dir, batch_id) or ""
        m.update_batch_status(batch_id, BatchStatus.VALIDATING.value)
        save_manifest(self.output_dir, m)
        result = validate_and_write(
            self.output_dir,
            batch_id,
            raw,
            start_page=b.start_page,
            end_page=b.end_page,
        )
        if result.ok:
            write_accepted_response(self.output_dir, batch_id, raw)
            m.update_batch_status(batch_id, BatchStatus.ACCEPTED.value)
            save_manifest(self.output_dir, m)
            self._log(f"batch {batch_id:04d} accepted ({b.start_page}-{b.end_page})")
            from app.diagnostics.vision_fidelity_summary import write_fidelity_stats

            write_fidelity_stats(self.output_dir, final_md=None)
            return True
        err = "; ".join(result.errors)
        m.update_batch_status(batch_id, BatchStatus.NEEDS_RETRY.value, error=err)
        save_manifest(self.output_dir, m)
        self._log(f"batch {batch_id:04d} needs_retry: {err}")
        return False

    def _clear_transcribe_artifacts(self, m: VisionManifest) -> None:
        """完整重跑时清批次回答与合并中间产物，保留 bookfigures / prompt。"""
        for b in m.get_batches():
            clear_batch_artifacts(self.output_dir, b.id)
        vdir = vision_dir(self.output_dir)
        for name in ("document.raw.md", "document.cleaned.md"):
            p = vdir / name
            if p.is_file():
                p.unlink()
        # Figure 裁图结果也重跑
        m.figures = [
            {**f, "status": "pending", "file": ""}
            if isinstance(f, dict)
            else f
            for f in (m.figures or [])
        ]
        fig_path = vdir / "figures.json"
        if fig_path.is_file():
            fig_path.unlink()

    def reset_batch_for_browser_retry(self, batch_id: int) -> None:
        """校验失败后清旧回答并重置为 pending，供 Playwright 自动重提。"""
        m = self._ensure_manifest()
        clear_batch_artifacts(self.output_dir, batch_id)
        m.update_batch_status(batch_id, BatchStatus.PENDING.value, error="")
        save_manifest(self.output_dir, m)

    def resume_received_batches(self) -> None:
        """崩溃恢复：已有 response.raw.md 的继续校验（完整重跑后跳过）。"""
        if self.config.force_rerun:
            return
        m = self._ensure_manifest()
        if m.all_batches_accepted():
            return
        for b in m.get_batches():
            raw = read_raw_response(self.output_dir, b.id)
            if raw is None:
                continue
            if b.status == BatchStatus.ACCEPTED.value:
                continue
            self.ingest_and_validate(b.id, raw)

    def merge_and_clean(self) -> Path:
        m = self._ensure_manifest()
        if not m.all_batches_accepted():
            pending = [b.id for b in m.get_batches() if b.status != BatchStatus.ACCEPTED.value]
            raise RuntimeError(f"仍有未通过批次: {pending}")
        m.state = PipelineState.MERGING.value
        save_manifest(self.output_dir, m)
        raw_path = merge_accepted_batches(self.output_dir, m)

        # 合并后、清理前：用带 PAGE 标记的原文做全文校验
        raw_md = raw_path.read_text(encoding="utf-8")
        m.state = PipelineState.VALIDATING_DOCUMENT.value
        save_manifest(self.output_dir, m)
        doc_v = validate_document(raw_md, m.page_count)
        if not doc_v.ok:
            m.state = PipelineState.FAILED.value
            save_manifest(self.output_dir, m)
            raise RuntimeError("全文校验失败: " + "; ".join(doc_v.errors))

        m.state = PipelineState.CLEANING.value
        save_manifest(self.output_dir, m)
        cleaned_path = clean_and_write(self.output_dir, raw_md)

        figures = parse_figure_markers(cleaned_path.read_text(encoding="utf-8"))
        existing = {f.marker: f for f in load_figures_json(self.output_dir)}
        images_dir = self.output_dir / "images"
        merged_figs: list[FigureRecord] = []
        for f in figures:
            if f.marker in existing and existing[f.marker].status == "done":
                rec = existing[f.marker]
                fname = Path(str(rec.file).replace("\\", "/")).name
                if fname and (images_dir / fname).is_file():
                    merged_figs.append(rec)
                else:
                    merged_figs.append(f)
            else:
                merged_figs.append(f)
        save_figures_json(self.output_dir, merged_figs)
        m.figures = [
            {"marker": f.marker, "page": f.page, "status": f.status, "file": f.file}
            for f in merged_figs
        ]
        pending = [f for f in merged_figs if f.status != "done"]
        if pending:
            m.state = PipelineState.WAITING_FIGURES.value
        else:
            m.state = PipelineState.FINALIZING.value
        save_manifest(self.output_dir, m)
        return cleaned_path

    def pending_figures(self) -> list[FigureRecord]:
        figs = load_figures_json(self.output_dir)
        if not figs:
            cleaned = vision_dir(self.output_dir) / "document.cleaned.md"
            if cleaned.exists():
                figs = parse_figure_markers(cleaned.read_text(encoding="utf-8"))
                save_figures_json(self.output_dir, figs)
        return [f for f in figs if f.status not in ("done", "skipped")]

    def auto_extract_figures(self) -> int:
        """Docling 自动裁图写入 images/（与快速自动一致）。"""
        pending = self.pending_figures()
        if not pending:
            return 0
        from app.vision_transcribe.figure_auto import auto_fill_figures_from_docling

        mode = self.config.image_path_mode
        if mode not in ("relative", "absolute"):
            mode = "relative"
        n = auto_fill_figures_from_docling(
            self.pdf_path,
            self.output_dir,
            pending,
            image_path_mode=mode,
            images_scale=float(self.config.images_scale),
            log=self._log,
        )
        m = self._ensure_manifest()
        if n > 0:
            m.state = PipelineState.FINALIZING.value
            save_manifest(self.output_dir, m)
        return n

    def rebuild_figures_and_finalize(self, *, stem: str | None = None) -> Path:
        """批次已 accepted 时：重合并 → Docling 裁图 → 写回最终 md（不重跑浏览器）。"""
        self.merge_and_clean()
        pending = self.pending_figures()
        if pending:
            self._log(f"Figure：待裁图 {len(pending)} 个占位符")
            self.auto_extract_figures()
        return self.finalize(stem=stem)

    def finalize(self, *, stem: str | None = None) -> Path:
        m = self._ensure_manifest()
        cleaned = vision_dir(self.output_dir) / "document.cleaned.md"
        if not cleaned.exists():
            raise FileNotFoundError(str(cleaned))
        md = cleaned.read_text(encoding="utf-8")
        figs = load_figures_json(self.output_dir)
        from app.vision_transcribe.figure_markers import figure_numbers_by_marker

        fig_labels = figure_numbers_by_marker(md)
        name = (stem or self.pdf_path.stem) + ".md"
        final_path = self.output_dir / name
        mode = self.config.image_path_mode
        if mode not in ("relative", "absolute"):
            mode = "relative"
        md = writeback_figures(
            md,
            figs,
            md_path=final_path,
            output_dir=self.output_dir,
            image_path_mode=mode,
            figure_labels=fig_labels,
        )
        # 最终再跑一次安全清理（不剥 FIGURE 已替换内容）
        md = clean_vision_markdown(
            # 写回后不应再有 PAGE；FIGURE 未完成的保留
            md,
            strip_page_markers=True,
        )
        if not md.strip():
            raise RuntimeError(
                "最终 Markdown 为空（document.cleaned 或写回异常），"
                f"请检查 {cleaned}"
            )
        name = (stem or self.pdf_path.stem) + ".md"
        final_path = self.output_dir / name
        final_path.write_text(md, encoding="utf-8")
        m.state = PipelineState.DONE.value
        save_manifest(self.output_dir, m)
        from app.diagnostics.vision_fidelity_summary import write_fidelity_stats

        stats = write_fidelity_stats(self.output_dir, final_md=final_path)
        self._log(
            "保真字数 "
            f"{stats.get('final_chars', 0)}/{stats.get('ds_chars_total', 0)}"
            f"（{int(round((stats.get('ratio_final_over_ds') or 0) * 100))}%）"
        )
        self.close()
        return final_path
