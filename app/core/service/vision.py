"""视觉转换服务：Qt 无关。算法仍在 VisionPipeline。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from app.core.domain.job import CancellationToken
from app.task_model import ConvertTask, TaskStatus, WorkflowChoice, normalize_workflow
from app.utils.paths import resolve_vision_output_dir
from app.vision_transcribe.config import VisionConfig
from app.vision_transcribe.manifest import vision_dir
from app.vision_transcribe.models import BatchStatus
from app.vision_transcribe.pipeline import VisionPipeline
from app.vision_transcribe.browser.manual_clipboard import ManualClipboardAdapter
from app.vision_transcribe.browser.base import ServerBusyCooldownError


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


@dataclass
class VisionHooks:
    """Worker 提供的线程桥：取消 / 人工等待 / 进度。不含业务规则。"""

    cancelled: Callable[[], bool] = field(default=lambda: False)
    wait_clipboard: Callable[[], str | None] = field(default=lambda: None)
    wait_resume: Callable[[], bool] = field(default=lambda: True)
    on_status: Callable[[str, str, str], None] = field(default=_noop)
    on_stage: Callable[[str], None] = field(default=_noop)
    on_pipeline_stage: Callable[[str], None] = field(default=_noop)
    on_log: Callable[[str], None] = field(default=_noop)
    on_needs_clipboard: Callable[[str, int, int, int, str], None] = field(default=_noop)
    on_needs_user: Callable[[str, str], None] = field(default=_noop)
    on_needs_figures: Callable[[str, str], None] = field(default=_noop)


@dataclass(frozen=True)
class VisionOptions:
    output_root: Path
    per_folder: bool = True
    api: bool = False
    api_precision: str = "standard"
    browser_mode: str = "clipboard"
    images_scale: float = 2.0
    image_path_mode: str = "relative"

    def to_config(self) -> VisionConfig:
        if self.api:
            return VisionConfig(
                vision_backend="api",
                api_precision=str(self.api_precision or "standard"),
                images_scale=float(self.images_scale),
                image_path_mode=str(self.image_path_mode or "relative"),
            )
        mode = str(self.browser_mode or "clipboard")
        return VisionConfig(
            browser_mode=mode,
            vision_backend=mode,
            headless=False,
            images_scale=float(self.images_scale),
            image_path_mode=str(self.image_path_mode or "relative"),
        )

    def worker_kwargs(self) -> dict[str, Any]:
        return {
            "output_root": self.output_root,
            "per_folder": bool(self.per_folder),
            "config": self.to_config(),
        }


class VisionService:
    def __init__(
        self,
        config: VisionConfig,
        output_root: Path,
        per_folder: bool = True,
        hooks: VisionHooks | None = None,
    ) -> None:
        self._config = config
        self._output_root = Path(output_root)
        self._per_folder = bool(per_folder)
        self._hooks = hooks or VisionHooks()
        self._cancel = CancellationToken()
        self._current_pipeline: VisionPipeline | None = None
        self._batch_auto_retries: dict[int, int] = {}
        self._batch_recopy_tried: dict[int, bool] = {}
        self._batch_format_tried: dict[int, bool] = {}
        self._batch_page_retry_tried: dict[int, bool] = {}
        self._batch_page_retry_pages: dict[int, set[int]] = {}
        self._batch_sub_batch_tried: dict[int, bool] = {}
        self._batch_server_busy_waits: dict[int, int] = {}

    def request_cancel(self) -> None:
        self._cancel.cancel()
        self.close()

    def close(self) -> None:
        pipe = self._current_pipeline
        self._current_pipeline = None
        if pipe is not None:
            try:
                pipe.close()
            except Exception:
                pass

    def _resource_kinds(self) -> tuple[str, ...]:
        from app.core.runtime import ResourceKind

        if self.is_api_mode():
            return (ResourceKind.API,)
        if self.is_auto_browser():
            return (ResourceKind.BROWSER,)
        return (ResourceKind.CPU,)

    def is_api_mode(self) -> bool:
        return self._config.effective_backend() == "api"

    def is_auto_browser(self) -> bool:
        backend = self._config.effective_backend()
        return backend in ("playwright", "deepseek", "auto", "api")

    def _cancelled(self) -> bool:
        return self._cancel.is_cancelled() or bool(self._hooks.cancelled())

    def _emit_log(self, msg: str) -> None:
        text = str(msg or "").rstrip()
        if not text:
            return
        self._hooks.on_log(text)
        try:
            from app.utils.paths import APP_ROOT

            log_path = Path(APP_ROOT) / "logs" / "vision_pw_status.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {text}\n")
        except Exception:
            pass

    def rebuild_figures(self, pdf_path: Path, output_dir: Path, *, stem: str) -> Path:
        pipe = VisionPipeline(
            Path(pdf_path),
            Path(output_dir),
            self._config,
            log=self._emit_log,
        )
        return pipe.rebuild_figures_and_finalize(stem=stem)

    def run_task(self, task: ConvertTask) -> Path:
        wf = normalize_workflow(task.workflow or WorkflowChoice.VISION_WEB.value)
        task.workflow = wf
        out = resolve_vision_output_dir(self._output_root, task.pdf_path, wf)
        task.output_dir = out
        tid = task.id
        self._hooks.on_status(tid, TaskStatus.RUNNING.value, "页面渲染")
        self._hooks.on_pipeline_stage("render")
        self._hooks.on_stage("页面渲染")

        from app.core.runtime import get_runtime

        try:
            with get_runtime().job_scope(tid, kinds=self._resource_kinds(), cancelled=self._cancelled):
                return self._run_task_body(task, out, tid)
        finally:
            self.close()

    def _run_task_body(self, task: ConvertTask, out: Path, tid: str) -> Path:
        pipe = VisionPipeline(
            task.pdf_path,
            out,
            replace(self._config, force_rerun=bool(task.vision_force_rerun)),
            log=self._emit_log,
        )
        self._current_pipeline = pipe

        def _prog(label: str, cur: int, total: int) -> None:
            self._hooks.on_status(
                tid, TaskStatus.RUNNING.value, f"{label} {cur}/{total}"
            )

        pipe.prepare(progress=_prog, cancelled=self._cancelled)
        if self._cancelled():
            raise RuntimeError("cancelled")

        self._batch_auto_retries = {}
        self._batch_recopy_tried = {}
        self._batch_format_tried = {}
        self._batch_page_retry_tried = {}
        self._batch_page_retry_pages = {}
        self._batch_sub_batch_tried = {}
        self._batch_server_busy_waits = {}
        pipe.resume_received_batches()

        max_auto_retry = 3

        while True:
            if self._cancelled():
                raise RuntimeError("cancelled")
            batch = pipe.next_pending_batch()
            if batch is None:
                m = pipe._ensure_manifest()
                if not m.all_batches_accepted():
                    stuck = [
                        f"#{b.id}:{b.status}"
                        for b in m.get_batches()
                        if b.status != "accepted"
                    ]
                    raise RuntimeError(
                        "没有可继续的批次，但仍有未完成项: "
                        + ", ".join(stuck)
                        + "。请查看 manifest 与各 batch 目录状态。"
                    )
                break
            if batch.status == BatchStatus.RECEIVED.value:
                raw_path = (
                    out / ".vision" / "batches" / f"batch_{batch.id:04d}" / "response.raw.md"
                )
                if raw_path.exists():
                    pipe.ingest_and_validate(batch.id, raw_path.read_text(encoding="utf-8"))
                    continue

            self._hooks.on_pipeline_stage("transcribe")
            self._hooks.on_status(
                tid,
                TaskStatus.RUNNING.value,
                f"视觉转录 {batch.start_page}–{batch.end_page}",
            )

            if self.is_auto_browser():
                self._handle_auto_batch(tid, pipe, batch, out, max_auto_retry)
                continue

            prep = pipe.prepare_batch(batch)
            self._hooks.on_needs_clipboard(
                tid, batch.id, batch.start_page, batch.end_page, prep.hint
            )
            text = self._hooks.wait_clipboard()
            if text is None:
                raise RuntimeError("cancelled")
            if not text.strip():
                text = ManualClipboardAdapter.read_clipboard()
            self._hooks.on_pipeline_stage("validate")
            ok = pipe.ingest_and_validate(batch.id, text)
            if not ok:
                self._emit_log(
                    f"批次 {batch.start_page}–{batch.end_page} 校验失败，将重试（可缩小批次后重贴）"
                )
                continue

        self._hooks.on_pipeline_stage("merge")
        self._hooks.on_status(tid, TaskStatus.RUNNING.value, "合并与格式清理")
        pipe.merge_and_clean()
        pending = pipe.pending_figures()
        if not pending:
            from app.vision_transcribe.vision_structure_repair import (
                has_deepseek_placeholder_images,
            )

            cleaned_path = vision_dir(out) / "document.cleaned.md"
            if cleaned_path.is_file() and has_deepseek_placeholder_images(
                cleaned_path.read_text(encoding="utf-8")
            ):
                self._emit_log(
                    "警告：文中仍有 example.com 假图 URL，FIGURE 占位符未生成，"
                    "已跳过 Docling 裁图（请更新程序后重跑合并）"
                )
        if pending:
            self._hooks.on_pipeline_stage("figures")
            self._hooks.on_status(
                tid,
                TaskStatus.RUNNING.value,
                f"Docling 自动裁图 0/{len(pending)}",
            )
            filled = pipe.auto_extract_figures()
            still = pipe.pending_figures()
            if still:
                self._emit_log(f"仍有 {len(still)} 个 Figure 未匹配到 Docling 图片")
                raise RuntimeError(
                    f"图片未全部插入：{len(still)} 个 FIGURE 占位符无对应图片，"
                    "不能标记完成（可用右键「仅重合并与裁图」重试）"
                )
            if filled:
                self._emit_log(f"Figure 自动写入完成（{filled} 张）")
        final = pipe.finalize(stem=task.pdf_path.stem)
        task.output_md = final
        task.vision_force_rerun = False
        self._hooks.on_pipeline_stage("idle")
        self._hooks.on_status(tid, TaskStatus.RUNNING.value, "完成")
        self._emit_log(f"高保真完成: {final}")
        return Path(final)

    def _handle_auto_batch(
        self,
        tid: str,
        pipe: VisionPipeline,
        batch,
        out: Path,
        max_auto_retry: int,
    ) -> None:
        if batch.status == BatchStatus.NEEDS_RETRY.value:
            from app.vision_transcribe.recovery.failure_parse import (
                load_batch_validation_errors,
            )
            from app.vision_transcribe.recovery.planner import plan_batch_recovery

            tries = self._batch_auto_retries.get(batch.id, 0)
            if tries >= max_auto_retry:
                raise RuntimeError(
                    f"批次 PAGE {batch.start_page:04d}–{batch.end_page:04d} "
                    f"自动重试已达 {max_auto_retry} 次仍校验失败，"
                    "请查看 logs/vision_pw_status.log"
                )
            val_errs = load_batch_validation_errors(out, batch.id)
            action, target_pages = plan_batch_recovery(
                errors=val_errs,
                error_text=batch.error or "",
                recopy_tried=self._batch_recopy_tried.get(batch.id, False),
                page_retry_tried=self._batch_page_retry_tried.get(batch.id, False),
                page_retry_pages=self._batch_page_retry_pages.get(batch.id, set()),
                sub_batch_tried=self._batch_sub_batch_tried.get(batch.id, False),
                format_tried=self._batch_format_tried.get(batch.id, False),
                retry_count=tries,
            )

            if action == "accept_warnings":
                if pipe.force_accept_batch(batch.id):
                    return

            if action == "format_fix":
                self._batch_format_tried[batch.id] = True
                self._emit_log(
                    f"批次 {batch.start_page}–{batch.end_page} "
                    "Level-1 格式修复后二次验证…"
                )
                fr = pipe.try_format_fix_batch(batch)
                if fr and (fr.markdown or "").strip():
                    refreshed = {
                        b.id: b for b in pipe._ensure_manifest().get_batches()
                    }.get(batch.id)
                    if (
                        refreshed is not None
                        and refreshed.status == BatchStatus.ACCEPTED.value
                    ):
                        return

            if action == "full_batch" and any(
                "模型输出退化" in e for e in val_errs
            ) and not self.is_api_mode():
                self._emit_log("检测到模型输出退化，重启浏览器子进程后全量重提…")
                pipe.close()

            if (
                action == "recopy"
                and not self._batch_recopy_tried.get(batch.id)
                and not self.is_api_mode()
            ):
                self._batch_recopy_tried[batch.id] = True
                self._emit_log(
                    f"批次 {batch.start_page}–{batch.end_page} 校验未通过，"
                    "Level-0 仅重新抽取…"
                )
                recopy = pipe.try_recopy_batch(batch)
                if recopy and recopy.needs_user:
                    self._hooks.on_needs_user(
                        tid, recopy.message or "需要人工处理浏览器"
                    )
                    if not self._hooks.wait_resume():
                        raise RuntimeError("cancelled")
                elif recopy and (recopy.markdown or "").strip():
                    refreshed = {
                        b.id: b for b in pipe._ensure_manifest().get_batches()
                    }.get(batch.id)
                    if (
                        refreshed is not None
                        and refreshed.status == BatchStatus.ACCEPTED.value
                    ):
                        return

            elif action == "page_retry" and target_pages:
                self._batch_page_retry_tried[batch.id] = True
                self._batch_page_retry_pages.setdefault(batch.id, set()).update(
                    target_pages
                )
                self._emit_log(
                    f"批次 {batch.start_page}–{batch.end_page} "
                    f"Level-2 单页重跑: {target_pages}"
                )
                pr = pipe.try_page_retry_batch(batch, target_pages)
                if pr and pr.needs_user:
                    self._hooks.on_needs_user(tid, pr.message or "需要人工处理浏览器")
                    if not self._hooks.wait_resume():
                        raise RuntimeError("cancelled")
                elif pr and (pr.markdown or "").strip():
                    refreshed = {
                        b.id: b for b in pipe._ensure_manifest().get_batches()
                    }.get(batch.id)
                    if (
                        refreshed is not None
                        and refreshed.status == BatchStatus.ACCEPTED.value
                    ):
                        return

            elif action == "sub_batch" and target_pages:
                self._batch_sub_batch_tried[batch.id] = True
                self._emit_log(
                    f"批次 {batch.start_page}–{batch.end_page} "
                    f"Level-3 子批次重跑: {target_pages}"
                )
                sr = pipe.try_sub_batch_retry(batch, target_pages)
                if sr and sr.needs_user:
                    self._hooks.on_needs_user(tid, sr.message or "需要人工处理浏览器")
                    if not self._hooks.wait_resume():
                        raise RuntimeError("cancelled")
                elif sr and (sr.markdown or "").strip():
                    refreshed = {
                        b.id: b for b in pipe._ensure_manifest().get_batches()
                    }.get(batch.id)
                    if (
                        refreshed is not None
                        and refreshed.status == BatchStatus.ACCEPTED.value
                    ):
                        return

            self._batch_auto_retries[batch.id] = tries + 1
            retry_label = "API" if self.is_api_mode() else "浏览器"
            self._emit_log(
                f"批次 {batch.start_page}–{batch.end_page} 校验未通过，"
                f"Level-4 全量重提{retry_label}（{tries + 1}/{max_auto_retry}）…"
            )
            pipe.reset_batch_for_browser_retry(batch.id)
            refreshed = {b.id: b for b in pipe._ensure_manifest().get_batches()}.get(
                batch.id
            )
            if refreshed is not None:
                batch = refreshed

        if self.is_api_mode():
            self._hooks.on_status(tid, TaskStatus.RUNNING.value, "Vision API 转录…")
            result = pipe.try_auto_submit(batch)
        else:
            self._hooks.on_status(tid, TaskStatus.RUNNING.value, "启动浏览器（子进程）…")
            result = self._try_auto_submit_with_cooldown(tid, pipe, batch)
        if self.is_api_mode():
            if result and not (result.markdown or "").strip() and result.message:
                raise RuntimeError(result.message)
            still = pipe.next_pending_batch()
            if still and still.id == batch.id:
                err = still.error or "校验未通过"
                self._emit_log(f"API 批次校验失败：{err}；将自动重试")
            return
        while result and result.needs_user:
            hint = result.message or "需要人工处理浏览器"
            if any(k in hint for k in ("登录", "验证", "验证码")):
                self._emit_log("等待人工登录/验证：请勿关闭 DeepSeek 浏览器窗口")
            else:
                self._emit_log(f"浏览器需处理：{hint}")
            self._hooks.on_needs_user(tid, result.message or "需要人工处理浏览器")
            self._hooks.on_pipeline_stage("transcribe")
            if not self._hooks.wait_resume():
                raise RuntimeError("cancelled")
            self._hooks.on_status(tid, TaskStatus.RUNNING.value, "继续自动识别…")
            result = pipe.resume_pending_submit()
        if result and not result.needs_user:
            still = pipe.next_pending_batch()
            if still and still.id == batch.id:
                err = still.error or "校验未通过"
                self._emit_log(f"自动批次校验失败：{err}；将自动重试浏览器")

    def _try_auto_submit_with_cooldown(self, task_id: str, pipe: VisionPipeline, batch):
        max_cooldowns = 5
        while True:
            try:
                return pipe.try_auto_submit(batch)
            except ServerBusyCooldownError as e:
                waits = self._batch_server_busy_waits.get(batch.id, 0)
                if waits >= max_cooldowns:
                    raise RuntimeError(
                        f"批次 PAGE {batch.start_page:04d}–{batch.end_page:04d} "
                        f"上传限流已冷却等待 {max_cooldowns} 次仍失败"
                    ) from e
                self._batch_server_busy_waits[batch.id] = waits + 1
                cooldown = int(getattr(pipe.config, "server_busy_cooldown_seconds", 600))
                if e.cooldown_seconds != cooldown:
                    e = ServerBusyCooldownError(str(e), cooldown_seconds=cooldown)
                self._wait_server_busy_cooldown(task_id, pipe, e)

    def _wait_server_busy_cooldown(
        self, task_id: str, pipe: VisionPipeline, exc: ServerBusyCooldownError
    ) -> None:
        seconds = max(60, int(exc.cooldown_seconds))
        wait_min = max(1, seconds // 60)
        self._emit_log(
            f"[UploadGuard] 上传限流「服务器繁忙」（账户级，刷新无效），"
            f"暂停约 {wait_min} 分钟后自动续跑…"
        )
        self._hooks.on_status(
            task_id, TaskStatus.RUNNING.value, f"上传限流，冷却约 {wait_min} 分钟"
        )
        pipe.close()
        deadline = time.monotonic() + seconds
        last_announced = -1
        while time.monotonic() < deadline:
            if self._cancelled():
                raise RuntimeError("cancelled")
            rem = int(deadline - time.monotonic())
            rem_min = max(0, rem // 60)
            if rem_min != last_announced and (rem_min % 2 == 0 or rem_min <= 1):
                self._hooks.on_status(
                    task_id,
                    TaskStatus.RUNNING.value,
                    f"上传限流冷却中，约 {rem_min} 分钟",
                )
                self._emit_log(f"[UploadGuard] 冷却剩余约 {rem_min} 分钟…")
                last_announced = rem_min
            time.sleep(min(15.0, max(1.0, rem)))
