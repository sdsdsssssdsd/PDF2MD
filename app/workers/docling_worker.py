"""后台转换 Worker（QThread）：Parser → AssetPipeline → RepairPipeline → 最终 Markdown。"""
from __future__ import annotations

import time
import traceback
from pathlib import Path

from PySide6.QtCore import QMutex, QThread, Signal

from app.assets import AssetConfig, AssetPipeline
from app.engines import docling_engine, mineru_engine
from app.engines.base import ConversionResult
from app.repair import RepairConfig, RepairPipeline
from app.task_model import ConvertTask, EngineChoice, TaskStatus
from app.utils.logger import get_logger, write_task_log
from app.utils.paths import task_output_dir


class ConversionWorker(QThread):
    task_status = Signal(str, str, str)  # task_id, status, message
    task_finished = Signal(str, bool, str, str, str, float)  # id, ok, md, out_dir, err, elapsed
    log_line = Signal(str)
    stage = Signal(str)

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
        images_scale: float = 2.0,
        image_path_mode: str = "relative",
        export_md: bool = True,
        export_raw_md: bool = False,
        export_repair_json: bool = False,
        export_conversion_log: bool = False,
        export_manifest: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tasks = list(tasks)
        self._output_root = output_root
        self._per_folder = per_folder
        self._ocr_mode = ocr_mode
        self._keep_images = True  # 图片为必要组件，始终导出
        self._keep_tables = keep_tables
        self._keep_formulas = keep_formulas
        self._images_scale = float(images_scale)
        self._image_path_mode = (
            image_path_mode if image_path_mode in ("relative", "absolute") else "relative"
        )
        self._export_md = bool(export_md)
        self._export_raw_md = bool(export_raw_md)
        self._export_repair_json = bool(export_repair_json)
        self._export_conversion_log = bool(export_conversion_log)
        self._export_manifest = bool(export_manifest)
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

    def _parse(self, task: ConvertTask, out_dir: Path, progress) -> ConversionResult:
        eng = task.engine
        if eng == EngineChoice.MINERU.value:
            return mineru_engine.convert_pdf(
                task.pdf_path,
                out_dir,
                ocr_mode=self._ocr_mode,
                keep_tables=self._keep_tables,
                keep_formulas=self._keep_formulas,
                progress=progress,
            )
        if eng == EngineChoice.DOCLING.value:
            return docling_engine.convert_pdf(
                task.pdf_path,
                out_dir,
                keep_images=self._keep_images,
                keep_tables=self._keep_tables,
                keep_formulas=self._keep_formulas,
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
                keep_formulas=self._keep_formulas,
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
                keep_formulas=self._keep_formulas,
                progress=progress,
            )

    def _cleanup_optional_exports(self, out_dir: Path, images_dir: Path | None) -> None:
        """按导出组件删除过程中产生的可选文件。"""
        if not self._export_conversion_log:
            log_path = out_dir / "conversion.log"
            try:
                if log_path.is_file():
                    log_path.unlink()
            except OSError:
                pass
        if not self._export_manifest:
            for base in (images_dir, out_dir / "images"):
                if base is None:
                    continue
                man = Path(base) / "manifest.json"
                try:
                    if man.is_file():
                        man.unlink()
                except OSError:
                    pass

    def run(self) -> None:
        log = get_logger()
        repair = RepairPipeline(
            RepairConfig(
                enabled=True,
                mode="safe",
                keep_formulas=self._keep_formulas,
                fix_bold=True,
                write_raw_md=self._export_raw_md,
                write_repair_json=self._export_repair_json,
                write_final_md=self._export_md,
                use_geometry=True,
            )
        )

        for task in self._tasks:
            if self._cancelled():
                self.task_status.emit(task.id, TaskStatus.CANCELLED.value, "已取消")
                continue

            self.task_status.emit(task.id, TaskStatus.RUNNING.value, "开始转换")
            self.stage.emit(f"正在转换：{task.name}")
            self.log_line.emit(f"开始转换 {task.name}（引擎 {task.engine}）")
            log.info("开始转换 %s 引擎=%s", task.name, task.engine)

            out_dir = task_output_dir(self._output_root, task.pdf_path, self._per_folder)
            out_dir.mkdir(parents=True, exist_ok=True)
            t0 = time.time()

            def progress(msg: str) -> None:
                self.stage.emit(msg)
                self.log_line.emit(msg)
                write_task_log(out_dir, msg)

            try:
                parsed = self._parse(task, out_dir, progress)
                progress(f"解析器：{parsed.parser} → {parsed.markdown_path.name}")

                # Figure AssetPipeline：语义命名 / caption / manifest（在 Repair 之前）
                images_dir = parsed.artifacts_dir or (out_dir / "images")
                if not images_dir.exists():
                    images_dir = out_dir / "images"
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
                for w in asset_result.warnings[:8]:
                    progress(f"Asset 提示：{w}")

                repaired = repair.run(
                    pdf_path=task.pdf_path,
                    raw_markdown_path=parsed.markdown_path,
                    out_dir=out_dir,
                    progress=progress,
                )
                if repaired.report_path and repaired.report_path.exists():
                    try:
                        import json

                        data = json.loads(repaired.report_path.read_text(encoding="utf-8"))
                        data["parser"] = parsed.parser
                        repaired.report_path.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass

                md_str = str(repaired.markdown_path) if self._export_md and repaired.markdown_path.exists() else ""
                elapsed = time.time() - t0
                if self._export_conversion_log:
                    write_task_log(
                        out_dir,
                        f"OK components md={self._export_md} raw={self._export_raw_md} "
                        f"json={self._export_repair_json} log={self._export_conversion_log} "
                        f"manifest={self._export_manifest}",
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
                write_task_log(out_dir, err)
                self._cleanup_optional_exports(out_dir, out_dir / "images")
                self.task_finished.emit(task.id, False, "", str(out_dir), str(e), elapsed)
                self.log_line.emit(f"失败 {task.name}: {e}")
                log.exception("失败 %s", task.name)

        self.stage.emit("空闲")
