"""日常识图服务：Qt 无关。算法仍在 DailyVisionPipeline。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.core.domain.artifact import MarkdownArtifact
from app.core.runtime import ResourceKind, get_runtime
from app.daily_vision.exporter import export_archive
from app.daily_vision.models import DailyVisionCancelled, ProgressFn
from app.daily_vision.pipeline import DailyVisionPipeline
from app.daily_vision.session import DailyVisionSession

# 部分结果回调：正文, 已识别张数, 本轮结束时将达到的张数
PartialFn = Callable[[str, int, int], None]


@dataclass
class DailyVisionOutcome:
    ok: bool
    markdown: str = ""
    archive_path: str = ""
    error: str = ""
    warning: str = ""
    artifact: MarkdownArtifact | None = None
    session: dict[str, Any] | None = None  # 会话快照，交给下一轮继续累加
    images: list[str] = field(default_factory=list)  # 本轮实际识别的图片


class DailyVisionService:
    """一次调用 = 一轮识别（可能只含 1 张图），或一次「只归档」。"""

    def run(
        self,
        image_paths: list[Path],
        *,
        archive: bool = False,
        archive_dir: Path | None = None,
        session: dict[str, Any] | None = None,
        log: Callable[[str], None] | None = None,
        progress: ProgressFn | None = None,
        cancelled: Callable[[], bool] | None = None,
        on_partial: PartialFn | None = None,
    ) -> DailyVisionOutcome:
        """识别 image_paths 并（可选）归档。

        session 为上一轮返回的快照：本轮结果会按已识别张数偏移并进同一篇正文。
        归档发生在识别之后，覆盖整个会话的图片与累积结果。
        """
        log_fn = log or (lambda _m: None)
        emit = progress or (lambda _text, _percent: None)
        paths = [Path(p) for p in image_paths]
        state = DailyVisionSession.from_payload(session)
        try:
            if paths:
                outcome = self.recognize(
                    paths,
                    session=state,
                    log=log_fn,
                    progress=emit,
                    cancelled=cancelled,
                    on_partial=on_partial,
                )
                if not outcome.ok:
                    return outcome
                state = DailyVisionSession.from_payload(outcome.session)
            elif not state.images:
                return DailyVisionOutcome(ok=False, error="没有有效图片")
            if archive and archive_dir:
                return self.archive_session(
                    state, archive_dir=archive_dir, progress=emit, log=log_fn
                )
            emit("识别完成", 100)
            return DailyVisionOutcome(
                ok=True,
                markdown=state.result.markdown,
                warning="；".join(state.result.warnings),
                artifact=self._artifact(state, paths),
                session=state.to_payload(),
                images=[str(p) for p in paths],
            )
        except DailyVisionCancelled:
            return DailyVisionOutcome(ok=False, error="已取消")
        except Exception as exc:  # noqa: BLE001
            return DailyVisionOutcome(ok=False, error=str(exc))

    def recognize(
        self,
        image_paths: list[Path],
        *,
        session: DailyVisionSession | dict[str, Any] | None = None,
        log: Callable[[str], None] | None = None,
        progress: ProgressFn | None = None,
        cancelled: Callable[[], bool] | None = None,
        on_partial: PartialFn | None = None,
    ) -> DailyVisionOutcome:
        """只做识别：结果并入会话（不落盘、不归档）。"""
        log_fn = log or (lambda _m: None)
        emit = progress or (lambda _text, _percent: None)
        paths = [Path(p) for p in image_paths]
        base_payload = session.to_payload() if isinstance(session, DailyVisionSession) else session
        state = DailyVisionSession.from_payload(session)
        state.add_images(paths)

        def _partial(run_result: Any, run_done: int) -> None:
            if on_partial is None:
                return
            # 每批都从「本轮开始前」的快照重建，避免重复累加已识别张数
            snap = DailyVisionSession.from_payload(base_payload)
            snap.merge_run(paths[:run_done], run_result)
            on_partial(snap.result.markdown, snap.done, snap.done + (len(paths) - run_done))

        job_id = uuid4().hex[:12]
        try:
            with get_runtime().job_scope(job_id, kinds=(ResourceKind.API,)):
                pipe = DailyVisionPipeline(log=log_fn)
                result = pipe.transcribe(
                    paths, progress=emit, cancelled=cancelled, on_partial=_partial
                )
            state.merge_run(paths, result)
            return DailyVisionOutcome(
                ok=True,
                markdown=state.result.markdown,
                warning="；".join(state.result.warnings),
                artifact=self._artifact(state, paths),
                session=state.to_payload(),
                images=[str(p) for p in paths],
            )
        except DailyVisionCancelled:
            return DailyVisionOutcome(ok=False, error="已取消")
        except Exception as exc:  # noqa: BLE001
            return DailyVisionOutcome(ok=False, error=str(exc))

    def archive_session(
        self,
        session: DailyVisionSession | dict[str, Any] | None,
        *,
        archive_dir: Path,
        log: Callable[[str], None] | None = None,
        progress: ProgressFn | None = None,
    ) -> DailyVisionOutcome:
        """把整个会话的图片与累积结果导出为图文归档（不再调用 API）。"""
        emit = progress or (lambda _text, _percent: None)
        state = DailyVisionSession.from_payload(session)
        if not state.images:
            return DailyVisionOutcome(ok=False, error="没有可归档的图片")
        emit("导出图文归档…", 95)
        md_path = export_archive(list(state.images), state.result, Path(archive_dir))
        emit("归档完成", 100)
        return DailyVisionOutcome(
            ok=True,
            markdown=state.result.markdown,
            archive_path=str(md_path),
            warning="；".join(state.result.warnings),
            artifact=self._artifact(state, []),
            session=state.to_payload(),
        )

    def _artifact(
        self, state: DailyVisionSession, run_images: list[Path]
    ) -> MarkdownArtifact:
        source = run_images[0] if run_images else (state.images[0] if state.images else "")
        return MarkdownArtifact(
            workflow="日常识图",
            source=str(source),
            text=state.result.markdown,
        )
