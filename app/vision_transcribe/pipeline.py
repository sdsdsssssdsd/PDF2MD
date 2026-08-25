"""VisionPipeline：调度渲染→分批→校验→合并→清理→Figure，不做网页 DOM。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.vision_transcribe.batch_ingest import (
    clear_batch_artifacts,
    clear_batch_response_only,
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
        try:
            from app.vision_transcribe.integrity.source_guard import build_all_source_guards

            n_guard = build_all_source_guards(self.pdf_path, self.output_dir)
            if n_guard:
                self._log(f"SourceGuard：已为 {n_guard} 页建立文本层锚点")
        except Exception as exc:
            self._log(f"SourceGuard 跳过（{exc}）")
        if not m.batches:
            m.set_batches(plan_batches(len(pages), self.config.batch_size))
        elif self.config.force_rerun:
            self._restart_all_batches(
                m,
                reason="强制重跑",
            )
        else:
            n_bad = self._revalidate_accepted_batches(m)
            if n_bad:
                self._log(
                    f"完成检查未通过：已重置 {n_bad} 个批次，将重新提交浏览器"
                )
                self._continue_incomplete_batches(m)
            elif m.all_batches_accepted():
                # 已全部 accepted 且完成检查通过：保留，直接走合并/裁图
                self._log(
                    "输出目录已有全部 accepted 批次（完成检查通过），跳过浏览器重跑"
                    "（已完成任务点「转换」会默认整篇重跑；"
                    "仅合并/裁图可用右键「仅重合并与裁图」）"
                )
            else:
                self._continue_incomplete_batches(m)
        for b in m.get_batches():
            write_batch_prompt(
                batch_dir(self.output_dir, b.id),
                b.start_page,
                b.end_page,
                batch_id=b.id,
            )
        m.browser_mode = self.config.browser_mode
        m.state = PipelineState.READY_TO_TRANSCRIBE.value
        save_manifest(self.output_dir, m)
        self._log(f"渲染完成 {len(pages)} 页，{len(m.batches)} 个批次")
        return m

    def _restart_all_batches(self, m: VisionManifest, *, reason: str) -> None:
        """全部批次重新跑视觉转录（保留 attempts/ 诊断证据）。"""
        n = m.reset_all_batches_for_rerun()
        self._clear_transcribe_artifacts(m)
        self._log(f"{reason}：已重置 {n} 个批次")

    def _continue_incomplete_batches(self, m: VisionManifest) -> None:
        """未完成批次沿断点续跑：保留 raw/attempts；仅恢复真正中断的上传/等待态。"""
        keep_n = 0
        reset_n = 0
        for b in m.batches:
            st = str(b.get("status"))
            if st == BatchStatus.ACCEPTED.value:
                continue
            bid = int(b["id"])
            raw = read_raw_response(self.output_dir, bid)
            if raw and st in (
                BatchStatus.RECEIVED.value,
                BatchStatus.VALIDATING.value,
                BatchStatus.NEEDS_RETRY.value,
            ):
                keep_n += 1
                continue
            if st in (
                BatchStatus.WAITING_RESPONSE.value,
                BatchStatus.UPLOADING.value,
                BatchStatus.FAILED.value,
            ):
                b["status"] = BatchStatus.PENDING.value
                b["error"] = ""
                reset_n += 1
                continue
            if st == BatchStatus.PENDING.value and not raw:
                reset_n += 1
        if keep_n:
            self._log(
                f"断点续跑：保留 {keep_n} 个未完成批次的状态与 raw（沿未完成路径继续）"
            )
        if reset_n:
            self._log(
                f"续跑：{reset_n} 个批次待提交浏览器"
                + ("（已保留 attempts/ 证据）" if keep_n else "")
            )

    def _revalidate_accepted_batches(self, m: VisionManifest) -> int:
        """对已 accepted 批次再跑完成检查；未通过则打回 pending，禁止假 DONE。"""
        from app.vision_transcribe.batch_validator import validate_batch_markdown

        n_bad = 0
        for b in m.get_batches():
            if b.status != BatchStatus.ACCEPTED.value:
                continue
            raw = read_raw_response(self.output_dir, b.id)
            if not (raw or "").strip():
                clear_batch_response_only(self.output_dir, b.id)
                m.update_batch_status(
                    b.id,
                    BatchStatus.PENDING.value,
                    error="完成检查：accepted 但缺少 response.raw.md",
                )
                n_bad += 1
                continue
            result = validate_batch_markdown(
                raw,
                start_page=b.start_page,
                end_page=b.end_page,
                batch_id=b.id,
                output_dir=self.output_dir,
                prompt_version=m.prompt_version or "",
            )
            if result.ok:
                continue
            err = "; ".join(result.errors)
            clear_batch_response_only(self.output_dir, b.id)
            m.update_batch_status(
                b.id,
                BatchStatus.PENDING.value,
                error=f"完成检查失败: {err}",
            )
            n_bad += 1
        if n_bad:
            m.state = PipelineState.READY_TO_TRANSCRIBE.value
            save_manifest(self.output_dir, m)
        return n_bad

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
        if hasattr(adapter, "set_capture_context"):
            adapter.set_capture_context(self.output_dir, prep.batch.id)
        m = self._ensure_manifest()
        bid = prep.batch.id
        m.update_batch_status(bid, BatchStatus.UPLOADING.value)
        save_manifest(self.output_dir, m)
        self._log(f"自动提交 batch {bid}: PAGE {prep.batch.start_page}-{prep.batch.end_page}")
        try:
            result = adapter.submit_batch(prep.images, prep.prompt)
        except Exception:
            m = self._ensure_manifest()
            stuck = next((b for b in m.get_batches() if b.id == bid), None)
            if stuck is not None and stuck.status == BatchStatus.UPLOADING.value:
                m.update_batch_status(bid, BatchStatus.PENDING.value, error="")
                save_manifest(self.output_dir, m)
                self._log(f"batch {bid} 上传中断，已重置为 pending 便于续跑")
            raise
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

    def try_recopy_batch(self, batch: BatchInfo) -> AdapterResult | None:
        """Level-0：浏览器回答仍在时，仅重新 Capture + 校验。"""
        adapter = self.get_adapter()
        recopy_fn = getattr(adapter, "recopy_batch", None)
        if recopy_fn is None:
            return None
        d = batch_dir(self.output_dir, batch.id)
        prompt_path = d / "prompt.txt"
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""
        if hasattr(adapter, "set_capture_context"):
            adapter.set_capture_context(self.output_dir, batch.id)
        self._log(
            f"Level-0 仅重新抽取 batch {batch.id}（PAGE {batch.start_page}-{batch.end_page}）"
        )
        clear_batch_response_only(self.output_dir, batch.id)
        m = self._ensure_manifest()
        m.update_batch_status(batch.id, BatchStatus.VALIDATING.value, error="")
        save_manifest(self.output_dir, m)
        result = recopy_fn(prompt)
        if result.needs_user:
            m.state = PipelineState.NEEDS_USER.value
            m.update_batch_status(batch.id, BatchStatus.WAITING_RESPONSE.value)
            save_manifest(self.output_dir, m)
            return result
        if not (result.markdown or "").strip():
            return result
        self.ingest_and_validate(
            batch.id,
            result.markdown,
            extract_stats=result.extract_stats,
        )
        return result

    def _submit_pages_for_retry(
        self, batch: BatchInfo, pages: list[int], prompt: str
    ) -> AdapterResult:
        adapter = self.get_adapter()
        if hasattr(adapter, "set_capture_context"):
            adapter.set_capture_context(self.output_dir, batch.id)
        images = [
            self.output_dir / "bookfigures" / page_png_name(p) for p in pages
        ]
        return adapter.submit_batch(images, prompt)

    def try_page_retry_batch(
        self, batch: BatchInfo, pages: list[int] | None = None
    ) -> AdapterResult | None:
        """Level-2：仅重跑失败页，替换 batch raw 中对应 PAGE 块。"""
        from app.vision_transcribe.capture.page_merge import replace_page_in_batch
        from app.vision_transcribe.prompts import build_single_page_prompt
        from app.vision_transcribe.recovery.failure_parse import (
            failed_pages_from_errors,
            load_batch_validation_errors,
        )

        pages = pages or failed_pages_from_errors(
            load_batch_validation_errors(self.output_dir, batch.id)
        )
        pages = [p for p in pages if batch.start_page <= p <= batch.end_page]
        if not pages:
            return None
        raw = read_raw_response(self.output_dir, batch.id) or ""
        if not raw.strip():
            return None

        merged = raw
        last_result: AdapterResult | None = None
        for p in pages:
            self._log(f"Level-2 单页重跑 PAGE {p:04d}（batch {batch.id}）")
            prompt = build_single_page_prompt(page=p)
            result = self._submit_pages_for_retry(batch, [p], prompt)
            last_result = result
            if result.needs_user:
                return result
            if not (result.markdown or "").strip():
                self._log(f"Level-2 PAGE {p:04d} 无内容，跳过")
                continue
            merged = replace_page_in_batch(merged, p, result.markdown)

        clear_batch_response_only(self.output_dir, batch.id)
        m = self._ensure_manifest()
        m.update_batch_status(batch.id, BatchStatus.VALIDATING.value, error="")
        save_manifest(self.output_dir, m)
        self.ingest_and_validate(
            batch.id,
            merged,
            extract_stats=last_result.extract_stats if last_result else None,
        )
        return AdapterResult(
            markdown=merged,
            needs_user=False,
            extract_stats=last_result.extract_stats if last_result else None,
        )

    def try_sub_batch_retry(
        self, batch: BatchInfo, pages: list[int]
    ) -> AdapterResult | None:
        """Level-3：连续多页一次重跑，替换对应 PAGE 块。"""
        from app.vision_transcribe.capture.page_merge import replace_page_in_batch
        from app.vision_transcribe.capture.page_split import split_pages
        from app.vision_transcribe.prompts import build_batch_prompt

        pages = sorted(
            {p for p in pages if batch.start_page <= p <= batch.end_page}
        )
        if len(pages) < 2:
            return self.try_page_retry_batch(batch, pages)

        raw = read_raw_response(self.output_dir, batch.id) or ""
        if not raw.strip():
            return None

        start_p, end_p = pages[0], pages[-1]
        self._log(
            f"Level-3 子批次重跑 PAGE {start_p:04d}–{end_p:04d}（batch {batch.id}）"
        )
        prompt = build_batch_prompt(
            start_page=start_p, end_page=end_p, batch_id=batch.id
        )
        result = self._submit_pages_for_retry(
            batch, list(range(start_p, end_p + 1)), prompt
        )
        if result.needs_user:
            return result
        if not (result.markdown or "").strip():
            return result

        merged = raw
        for p, sl in split_pages(result.markdown).items():
            if p in pages:
                merged = replace_page_in_batch(merged, p, sl.body)

        clear_batch_response_only(self.output_dir, batch.id)
        m = self._ensure_manifest()
        m.update_batch_status(batch.id, BatchStatus.VALIDATING.value, error="")
        save_manifest(self.output_dir, m)
        self.ingest_and_validate(
            batch.id,
            merged,
            extract_stats=result.extract_stats,
        )
        return AdapterResult(
            markdown=merged,
            needs_user=False,
            extract_stats=result.extract_stats,
        )

    def force_accept_batch(self, batch_id: int) -> bool:
        """仅有软告警时直接 accepted（不重新跑浏览器）。"""
        raw = read_raw_response(self.output_dir, batch_id)
        if not raw:
            return False
        m = self._ensure_manifest()
        write_accepted_response(self.output_dir, batch_id, raw)
        m.update_batch_status(batch_id, BatchStatus.ACCEPTED.value)
        save_manifest(self.output_dir, m)
        self._log(f"batch {batch_id:04d} 已接受（仅软告警）")
        return True

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
            prompt_version=m.prompt_version,
        )
        if result.ok:
            write_accepted_response(self.output_dir, batch_id, raw)
            m.record_batch_acceptance(
                batch_id,
                raw,
                self.output_dir,
                extract_stats=extract_stats,
            )
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
        """校验失败后重置为 pending；保留 attempts/ 证据供诊断。"""
        m = self._ensure_manifest()
        clear_batch_response_only(self.output_dir, batch_id)
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
        doc_v = validate_document(
            raw_md,
            m.page_count,
            output_dir=self.output_dir,
            prompt_version=m.prompt_version or "",
        )
        if not doc_v.ok:
            m.state = PipelineState.FAILED.value
            save_manifest(self.output_dir, m)
            raise RuntimeError("全文校验失败: " + "; ".join(doc_v.errors))

        m.state = PipelineState.CLEANING.value
        save_manifest(self.output_dir, m)
        cleaned_path = clean_and_write(self.output_dir, raw_md)
        try:
            from app.vision_transcribe.integrity.content_preservation import (
                content_preservation_check,
            )

            cleaned_text = cleaned_path.read_text(encoding="utf-8")
            ok_cp, cp_msg, cp_stats = content_preservation_check(raw_md, cleaned_text)
            if ok_cp:
                self._log(
                    f"ContentPreservation ✓（drop {cp_stats.get('drop_ratio', 0):.1%}）"
                )
            else:
                self._log(f"ContentPreservation 告警: {cp_msg}")
        except Exception as exc:
            self._log(f"ContentPreservation 跳过（{exc}）")

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
        from app.vision_transcribe.figure_markers import (
            figure_completion_errors,
            strip_orphan_figure_markers_after_images,
        )

        md = strip_orphan_figure_markers_after_images(md)
        # 最终再跑一次安全清理（不剥 FIGURE 已替换内容）
        md = clean_vision_markdown(
            # 写回后不应再有 PAGE；FIGURE 未完成的保留供门禁检出
            md,
            strip_page_markers=True,
        )
        fig_errs = figure_completion_errors(md)
        if fig_errs:
            m.state = PipelineState.WAITING_FIGURES.value
            save_manifest(self.output_dir, m)
            raise RuntimeError(
                "图片未全部插入，不能标记完成：" + "；".join(fig_errs)
            )
        from app.vision_transcribe.transcript_quality import model_degeneration_errors

        deg_errs = model_degeneration_errors(md)
        if deg_errs:
            m.state = PipelineState.FAILED.value
            save_manifest(self.output_dir, m)
            raise RuntimeError("终稿完成检查失败：" + "；".join(deg_errs))
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
