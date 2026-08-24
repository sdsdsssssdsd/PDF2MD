"""后台转换 Worker（QThread）：Parser → AssetPipeline → RepairPipeline → 最终 Markdown。"""
from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QMutex, QThread, Signal

from app.assets import AssetConfig, AssetPipeline
from app.engines import docling_engine, mineru_engine
from app.engines.base import ConversionResult
from app.repair import RepairConfig, RepairPipeline
from app.task_model import ConvertTask, EngineChoice, TaskStatus
from app.utils.logger import get_logger, new_run_id, write_task_log
from app.ui.pipeline_classify import classify_deepseek_state, classify_pipeline_stage
from app.utils.paths import experiment_doc_dir, task_output_dir


class ConversionWorker(QThread):
    task_status = Signal(str, str, str)  # task_id, status, message
    task_finished = Signal(str, bool, str, str, str, float)  # id, ok, md, out_dir, err, elapsed
    log_line = Signal(str)
    stage = Signal(str)
    pipeline_stage = Signal(str)  # parse|assets|repair|mirror|idle · 只读 UI
    deepseek_state = Signal(str)  # cold|warming|warm|unavailable · 只读 UI

    def __init__(
        self,
        tasks: list[ConvertTask],
        *,
        output_root: Path,
        per_folder: bool,
        ocr_mode: str,
        keep_images: bool = True,
        keep_tables: bool = True,
        keep_formulas: bool = True,
        formula_recovery_preset: str = "balanced",
        deepseek_limited_production: bool = False,
        images_scale: float = 2.0,
        image_path_mode: str = "relative",
        export_md: bool = True,
        export_raw_md: bool = False,
        export_repair_json: bool = False,
        export_conversion_log: bool = False,
        export_manifest: bool = False,
        export_formula_qa: bool = False,
        export_timings: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tasks = list(tasks)
        self._output_root = output_root
        self._per_folder = per_folder
        self._ocr_mode = ocr_mode
        self._keep_images = True  # 图片为必要组件，始终导出
        self._keep_tables = keep_tables
        # Docling do_formula_enrichment（UI 勾选；Lean+DeepSeek 时解析阶段仍导出 LaTeX 种子）
        self._docling_formula_enrich = bool(keep_formulas)
        self._formula_recovery_preset = formula_recovery_preset or "balanced"
        self._deepseek_limited_production = bool(deepseek_limited_production)
        # Repair/FormulaPipeline 与 Docling enrich 解耦：
        # Lean 时 UI 可显示 enrich OFF，但解析仍导出损坏 LaTeX 供抢救；主修走 DeepSeek
        self._repair_keep_formulas = bool(
            self._deepseek_limited_production or keep_formulas
        )
        # 兼容旧字段名（部分日志/测试仍读 _keep_formulas）
        self._keep_formulas = self._docling_formula_enrich
        self._images_scale = float(images_scale)
        self._image_path_mode = (
            image_path_mode if image_path_mode in ("relative", "absolute") else "relative"
        )
        self._export_md = bool(export_md)
        self._export_raw_md = bool(export_raw_md)
        self._export_repair_json = bool(export_repair_json)
        self._export_conversion_log = bool(export_conversion_log)
        self._export_manifest = bool(export_manifest)
        self._export_formula_qa = bool(export_formula_qa)
        self._export_timings = bool(export_timings)
        self._cancel = False
        self._mutex = QMutex()

    def request_cancel(self) -> None:
        self._mutex.lock()
        self._cancel = True
        self._mutex.unlock()

    def _cancelled(self) -> bool:
        self._mutex.lock()
        v = self._cancel
        self._mutex.unlock()
        return v

    def _parse_keep_formulas(self) -> bool:
        """Docling 解析：Lean+DeepSeek 需要损坏 LaTeX 种子，不能只有 placeholder。"""
        if self._deepseek_limited_production:
            return True
        return self._docling_formula_enrich

    def _parse(self, task: ConvertTask, out_dir: Path, progress) -> ConversionResult:
        eng = task.engine
        if eng == EngineChoice.MINERU.value:
            return mineru_engine.convert_pdf(
                task.pdf_path,
                out_dir,
                ocr_mode=self._ocr_mode,
                keep_tables=self._keep_tables,
                keep_formulas=self._parse_keep_formulas(),
                progress=progress,
            )
        if eng == EngineChoice.DOCLING.value:
            return docling_engine.convert_pdf(
                task.pdf_path,
                out_dir,
                keep_images=self._keep_images,
                keep_tables=self._keep_tables,
                keep_formulas=self._parse_keep_formulas(),
                ocr_mode=self._ocr_mode,
                images_scale=self._images_scale,
                image_path_mode=self._image_path_mode,
                progress=progress,
            )
        # 自动：Docling 优先，失败则 MinerU
        try:
            return docling_engine.convert_pdf(
                task.pdf_path,
                out_dir,
                keep_images=self._keep_images,
                keep_tables=self._keep_tables,
                keep_formulas=self._parse_keep_formulas(),
                ocr_mode=self._ocr_mode,
                images_scale=self._images_scale,
                image_path_mode=self._image_path_mode,
                progress=progress,
            )
        except Exception as e:
            progress(f"Docling 失败，切换 MinerU：{e}")
            return mineru_engine.convert_pdf(
                task.pdf_path,
                out_dir,
                ocr_mode=self._ocr_mode,
                keep_tables=self._keep_tables,
                keep_formulas=self._parse_keep_formulas(),
                progress=progress,
            )

    def _cleanup_optional_exports(self, out_dir: Path, images_dir: Path | None) -> None:
        """按导出组件删除论文目录内的可选/中间产物（诊断镜像已另存）。"""
        def _unlink(path: Path) -> None:
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass

        if not self._export_conversion_log:
            _unlink(out_dir / "conversion.log")
            for p in out_dir.glob("conversion_*.log"):
                _unlink(p)
        if not self._export_manifest:
            for base in (images_dir, out_dir / "images"):
                if base is None:
                    continue
                _unlink(Path(base) / "manifest.json")
        if not self._export_formula_qa:
            for p in out_dir.glob("*.formula_qa.json"):
                _unlink(p)
        if not self._export_timings:
            for p in out_dir.glob("timings_*.json"):
                _unlink(p)

    def _mirror_experiment_artifacts(
        self,
        *,
        stem: str,
        out_dir: Path,
        run_id: str,
        timings: dict[str, Any],
        pdf_path: Path,
    ) -> None:
        """始终写入 logs/experiment，供「实验结果」读取；与导出组件勾选无关。"""
        import json
        import shutil

        exp = experiment_doc_dir(stem)
        payload = {
            "run_id": run_id,
            "batch_id": timings.get("batch_id") or "",
            "timings": timings,
            "pdf": str(pdf_path),
        }
        try:
            (exp / f"timings_{run_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        # 论文目录内若仍有 QA（清理前），镜像一份
        src_qa = out_dir / f"{stem}.formula_qa.json"
        if src_qa.is_file():
            try:
                shutil.copy2(src_qa, exp / src_qa.name)
            except OSError:
                pass
        # 导出组件开启时，论文目录也保留 timings
        if self._export_timings:
            try:
                (out_dir / f"timings_{run_id}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                pass

    def run(self) -> None:
        log = get_logger()
        repair = RepairPipeline(
            RepairConfig(
                enabled=True,
                mode="safe",
                keep_formulas=self._repair_keep_formulas,
                formula_recovery_preset=self._formula_recovery_preset,
                deepseek_limited_production=self._deepseek_limited_production,
                fix_bold=True,
                write_raw_md=self._export_raw_md,
                write_repair_json=self._export_repair_json,
                write_final_md=self._export_md,
                use_geometry=True,
            )
        )

        batch_id = new_run_id()
        batch_client = None
        if self._deepseek_limited_production:
            try:
                from app.ocr.deepseek_worker_client import get_deepseek_worker_client

                batch_client = get_deepseek_worker_client()
            except Exception:
                batch_client = None

        for batch_idx, task in enumerate(self._tasks):
            if self._cancelled():
                self.task_status.emit(task.id, TaskStatus.CANCELLED.value, "已取消")
                continue

            self.task_status.emit(task.id, TaskStatus.RUNNING.value, "开始转换")
            self.stage.emit(f"正在转换：{task.name}")
            self.pipeline_stage.emit("parse")
            self.log_line.emit(f"开始转换 {task.name}（引擎 {task.engine}）")
            log.info("开始转换 %s 引擎=%s", task.name, task.engine)

            out_dir = task_output_dir(self._output_root, task.pdf_path, self._per_folder)
            out_dir.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            run_id = new_run_id()
            timings: dict[str, Any] = {"batch_id": batch_id}
            warmup_thread = None
            docling_span: tuple[float, float] | None = None

            def progress(msg: str) -> None:
                self.stage.emit(msg)
                self.log_line.emit(msg)
                kind = classify_pipeline_stage(msg)
                if kind:
                    self.pipeline_stage.emit(kind)
                ds = classify_deepseek_state(msg)
                if ds:
                    self.deepseek_state.emit(ds)
                if self._export_conversion_log:
                    write_task_log(out_dir, msg, run_id=run_id)
                    # 兼容：同时追加最新 conversion.log 指针行（不抹掉历史 run 文件）
                    write_task_log(out_dir, f"[{run_id}] {msg}")

            try:
                # Phase 5C/5D：Limited Production 时并行预热（含 enrich OFF lean 路径）
                if self._deepseek_limited_production and batch_client is not None:
                    try:
                        if batch_idx > 0:
                            from app.ocr.deepseek_worker_client import (
                                prepare_document_worker_session,
                            )

                            prepare_document_worker_session(batch_client)
                        h = batch_client.health()
                        model_state = str(h.get("model_state") or "")
                        model_ready = bool(h.get("model_loaded")) and model_state == "MODEL_READY"
                        if model_ready:
                            progress("DeepSeek：模型已暖机，跳过重复加载")
                        else:
                            progress("DeepSeek：并行预热 Worker（与 Docling 重叠）…")
                            warmup_thread = batch_client.warmup_async()
                    except Exception as e:
                        progress(f"DeepSeek 预热跳过：{e}")

                t_doc = time.time()
                parsed = self._parse(task, out_dir, progress)
                timings["docling"] = round(time.time() - t_doc, 3)
                docling_span = (t_doc, time.time())
                if isinstance(getattr(parsed, "metadata", None), dict):
                    dmeta = parsed.metadata.get("docling") or {}
                    if dmeta:
                        timings["docling_detail"] = dmeta
                        progress(
                            f"Docling 遥测：reused={dmeta.get('converter_reused')} "
                            f"create={dmeta.get('converter_create_count')} "
                            f"init={dmeta.get('docling_init_seconds')}s "
                            f"convert={dmeta.get('docling_convert_seconds')}s "
                            f"export={dmeta.get('docling_export_seconds')}s"
                        )
                progress(f"解析器：{parsed.parser} → {parsed.markdown_path.name}")

                # 若预热已结束：写入 overlap/blocking（仅本 run 实际 load）
                if warmup_thread is not None:
                    try:
                        from app.ocr.deepseek_worker_client import get_deepseek_worker_client

                        client = get_deepseek_worker_client()
                        if not warmup_thread.is_alive() and docling_span:
                            ds, de = docling_span
                            rt = client.run_timings
                            ls, lf = rt.load_started_at, rt.load_finished_at
                            if ls and lf and rt.model_load_seconds > 0.05:
                                lo = max(ls, ds)
                                hi = min(lf, de)
                                overlap = max(0.0, hi - lo)
                                client.run_timings.load_overlap_seconds = overlap
                                client.run_timings.blocking_load_seconds = max(
                                    0.0, rt.model_load_seconds - overlap
                                )
                            timings["deepseek_load"] = float(rt.model_load_seconds or 0)
                            timings["deepseek_load_overlap"] = float(
                                rt.load_overlap_seconds or 0
                            )
                            timings["deepseek_blocking_load"] = float(
                                rt.blocking_load_seconds or 0
                            )
                            timings["deepseek_current_run"] = rt.to_dict()
                            timings["deepseek_worker_lifetime"] = (
                                client.worker_lifetime.to_dict()
                            )
                    except Exception:
                        pass

                self.pipeline_stage.emit("assets")
                # Figure AssetPipeline：语义命名 / caption / manifest（在 Repair 之前）
                images_dir = parsed.artifacts_dir or (out_dir / "images")
                if not images_dir.exists():
                    images_dir = out_dir / "images"
                t_asset = time.time()
                asset_result = AssetPipeline(
                    AssetConfig(
                        enabled=True,
                        enable_subfigure_split=True,  # 无 Vision 时 skipped，不硬切
                        image_path_mode=self._image_path_mode,
                        write_manifest=self._export_manifest,
                        cleanup_parser_files=True,
                    )
                ).run(
                    pdf_path=task.pdf_path,
                    markdown_path=parsed.markdown_path,
                    images_dir=images_dir,
                    parser_source=parsed.parser,
                    progress=progress,
                )
                timings["asset"] = round(time.time() - t_asset, 3)
                for w in asset_result.warnings[:8]:
                    progress(f"Asset 提示：{w}")

                # Phase 7.1：预检 + 并行暖机收尾——冷启动必须在 repair 前完成，不得落在 repair 内
                needs_ensure = False
                if self._deepseek_limited_production:
                    try:
                        from app.formula.deepseek_preflight import (
                            document_has_deepseek_recovery_work,
                            should_ensure_deepseek_before_repair,
                        )
                        from app.ocr.deepseek_batch_warmup import zero_deepseek_document_timings

                        raw_text = parsed.markdown_path.read_text(encoding="utf-8")
                        needs_ensure = should_ensure_deepseek_before_repair(
                            raw_text,
                            task.pdf_path,
                            warmup_in_flight=warmup_thread is not None,
                        )
                        has_recovery = document_has_deepseek_recovery_work(
                            raw_text, task.pdf_path
                        )
                        if not needs_ensure:
                            zero_deepseek_document_timings(
                                timings, needs_deepseek=has_recovery
                            )
                            progress(
                                "DeepSeek：本文无需批前加载（无公式恢复任务）"
                            )
                    except Exception as e:
                        needs_ensure = True
                        progress(f"DeepSeek 预检异常（保守阻塞）：{e}")

                if self._deepseek_limited_production and needs_ensure:
                    try:
                        from app.ocr.deepseek_batch_warmup import ensure_deepseek_before_repair
                        from app.ocr.deepseek_worker_client import get_deepseek_worker_client

                        client = get_deepseek_worker_client()
                        ensure_deepseek_before_repair(
                            client=client,
                            warmup_thread=warmup_thread,
                            docling_span=docling_span,
                            timings=timings,
                            progress=progress,
                        )
                    except Exception as e:
                        progress(f"DeepSeek 批前加载跳过：{e}")

                self.pipeline_stage.emit("repair")
                t_repair = time.time()
                repaired = repair.run(
                    pdf_path=task.pdf_path,
                    raw_markdown_path=parsed.markdown_path,
                    out_dir=out_dir,
                    progress=progress,
                )
                timings["repair_total"] = round(time.time() - t_repair, 3)
                # 从 formula_qa / shadow 回填分账（若有）
                try:
                    qa_path = out_dir / f"{task.pdf_path.stem}.formula_qa.json"
                    if qa_path.is_file():
                        import json as _json

                        qa = _json.loads(qa_path.read_text(encoding="utf-8"))
                        sm = (qa.get("deepseek_shadow") or {}).get("summary") or {}
                        cb = sm.get("cost_breakdown") or {}
                        if cb:
                            timings["recovery_cost_breakdown"] = cb
                        if sm.get("ocr_inference_seconds") is not None:
                            timings["ocr_inference_seconds"] = sm.get(
                                "ocr_inference_seconds"
                            )
                        if sm.get("cold_start_seconds") is not None:
                            # repair 内仍可能发生的冷启动（批前已暖则应为 0）
                            timings["recovery_cold_start_seconds"] = sm.get(
                                "cold_start_seconds"
                            )
                        if sm.get("document_recovery_profile"):
                            timings["document_recovery_profile"] = sm.get(
                                "document_recovery_profile"
                            )
                        # 统一 reporting：attempted/accepted/rejected
                        if sm.get("ocr_calls") is not None:
                            timings["recovery"] = {
                                "attempted": sm.get("attempted", sm.get("ocr_calls")),
                                "accepted": sm.get("accepted"),
                                "rejected": sm.get("rejected"),
                                "accept_rate": sm.get("accept_rate"),
                                "seconds_per_accept": sm.get("seconds_per_accept"),
                                "cost_per_recovered_formula": sm.get(
                                    "cost_per_recovered_formula"
                                ),
                                "profile": (
                                    (sm.get("document_recovery_profile") or {}).get(
                                        "profile"
                                    )
                                ),
                            }
                except Exception:
                    pass
                timings["total"] = round(time.time() - t0, 3)
                # 批级：cold vs steady（本篇）
                from app.ocr.deepseek_batch_warmup import deepseek_critical_path_seconds

                cold_batch = deepseek_critical_path_seconds(timings)
                if cold_batch <= 0.0:
                    cold_batch = float(
                        timings.get("model_cold_start")
                        or timings.get("deepseek_blocking_load")
                        or 0.0
                    )
                timings["deepseek_critical_path_seconds"] = round(cold_batch, 3)
                timings["batch_cold_start_seconds"] = round(cold_batch, 3)
                timings["batch_steady_state_seconds"] = round(
                    max(0.0, float(timings.get("total") or 0.0) - cold_batch), 3
                )
                # 收尾：若预热在 Repair 期间才完成，补算 overlap（预检跳过篇目不 join）
                if warmup_thread is not None and docling_span:
                    try:
                        from app.ocr.deepseek_batch_warmup import (
                            finalize_deepseek_timings_after_repair,
                        )
                        from app.ocr.deepseek_worker_client import get_deepseek_worker_client

                        client = get_deepseek_worker_client()
                        finalize_deepseek_timings_after_repair(
                            timings=timings,
                            warmup_thread=warmup_thread,
                            docling_span=docling_span,
                            client=client,
                        )
                    except Exception:
                        pass
                if repaired.report_path and repaired.report_path.exists():
                    try:
                        import json

                        data = json.loads(repaired.report_path.read_text(encoding="utf-8"))
                        data["parser"] = parsed.parser
                        data["run_id"] = run_id
                        data["timings"] = timings
                        repaired.report_path.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
                # 实验结果：始终镜像 timings / formula_qa → logs/experiment
                # 论文产物目录是否保留由导出组件决定（随后 cleanup）
                self.pipeline_stage.emit("mirror")
                self._mirror_experiment_artifacts(
                    stem=task.pdf_path.stem,
                    out_dir=out_dir,
                    run_id=run_id,
                    timings=timings,
                    pdf_path=task.pdf_path,
                )

                md_str = str(repaired.markdown_path) if self._export_md and repaired.markdown_path.exists() else ""
                elapsed = time.time() - t0
                if self._export_conversion_log:
                    write_task_log(
                        out_dir,
                        f"OK components md={self._export_md} raw={self._export_raw_md} "
                        f"json={self._export_repair_json} log={self._export_conversion_log} "
                        f"manifest={self._export_manifest} qa={self._export_formula_qa} "
                        f"timings={self._export_timings} run_id={run_id} "
                        f"timings_data={timings}",
                        run_id=run_id,
                    )
                self._cleanup_optional_exports(out_dir, images_dir)
                self.task_finished.emit(
                    task.id, True, md_str, str(out_dir), "", elapsed
                )
                self.log_line.emit(f"完成 {task.name}")
                log.info("完成 %s -> %s", task.name, out_dir)
            except Exception as e:
                elapsed = time.time() - t0
                err = f"{e}\n{traceback.format_exc()}"
                if self._export_conversion_log:
                    write_task_log(out_dir, err, run_id=run_id)
                    write_task_log(out_dir, f"[{run_id}] FAILED: {e}")
                self._cleanup_optional_exports(out_dir, out_dir / "images")
                self.task_finished.emit(task.id, False, "", str(out_dir), str(e), elapsed)
                self.log_line.emit(f"失败 {task.name}: {e}")
                log.exception("失败 %s", task.name)

        self.stage.emit("空闲")
        self.pipeline_stage.emit("idle")
