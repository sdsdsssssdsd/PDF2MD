"""R7：Vision / Daily / Repair 收进 Application Layer。"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from app.core.compat.vision_manifest import (
    VISION_MANIFEST_REL,
    ensure_vision_run_compat,
    vision_manifest_path,
)
from app.core.domain.artifact import MarkdownArtifact
from app.core.domain.job import CancellationToken, JobStatus
from app.core.service.repair import RepairService
from app.format_repair.models import RepairConfig
from app.task_model import ConvertTask, TaskStatus
from app.ui.daily_vision_controller import DailyVisionController, DailyVisionUiInputs
from app.ui.repair_controller import RepairController, RepairUiInputs, RepairViewState
from app.ui.vision_controller import (
    VisionController,
    VisionUiInputs,
    VisionViewState,
    compile_vision_options,
)


def _app() -> QApplication:
    inst = QApplication.instance()
    if inst is not None:
        return inst
    return QApplication([])


def _pump(app: QApplication, pred, rounds: int = 80) -> None:
    import time

    for _ in range(rounds):
        app.processEvents()
        if pred():
            return
        time.sleep(0.01)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_cancellation_token_and_job_status():
    token = CancellationToken()
    assert not token.is_cancelled()
    token.cancel()
    assert token.is_cancelled()
    token.reset()
    assert not token.is_cancelled()
    assert JobStatus.FAILED == "failed"


def test_compile_vision_options_api_and_web(tmp_path: Path):
    api = compile_vision_options(
        VisionUiInputs(output_root=tmp_path, api=True, api_precision="precise")
    )
    cfg = api.to_config()
    assert cfg.effective_backend() == "api"
    assert cfg.effective_batch_size() == 2
    web = compile_vision_options(
        VisionUiInputs(output_root=tmp_path, api=False, browser_mode="playwright")
    )
    assert web.to_config().effective_backend() == "playwright"
    assert "config" in web.worker_kwargs()


def test_vision_manifest_compat_creates_run_json_without_deleting_legacy(tmp_path: Path):
    vis = tmp_path / ".vision"
    vis.mkdir()
    (vis / "manifest.json").write_text(
        json.dumps(
            {
                "version": 2,
                "pdf": "paper.pdf",
                "state": "done",
                "backend": "playwright",
                "model": "deepseek",
                "task_profile": "vision_web",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    path = ensure_vision_run_compat(tmp_path, markdown_path="paper.md")
    assert path is not None and path.is_file()
    assert vision_manifest_path(tmp_path).is_file()
    run = json.loads(path.read_text(encoding="utf-8"))
    assert run["compat"]["vision_manifest"] == VISION_MANIFEST_REL
    assert run["compat"]["backend"] == "playwright"
    assert "checks" not in run
    ensure_vision_run_compat(tmp_path)
    assert vision_manifest_path(tmp_path).is_file()
    again = json.loads(path.read_text(encoding="utf-8"))
    assert again["compat"]["vision_manifest"] == VISION_MANIFEST_REL


def test_write_run_sidecar_keeps_vision_compat_pointer(tmp_path: Path):
    from app.core.domain.document import document_from_markdown
    from app.core.domain.quality import quality_from_markdown
    from app.core.pipeline.checkpoint import write_run_sidecar

    ir = document_from_markdown("# T\n", source="a.pdf")
    qa = quality_from_markdown("# T\n")
    write_run_sidecar(
        tmp_path,
        workflow="网页高保真",
        profile="pdf_vision_web",
        extra={
            "vision_manifest": ".vision/manifest.json",
            "backend": "api",
            "score": 99,
        },
        document=ir,
        quality=qa,
    )
    run = json.loads((tmp_path / ".pdf2md" / "run.json").read_text(encoding="utf-8"))
    assert run["compat"]["vision_manifest"] == ".vision/manifest.json"
    assert run["compat"]["backend"] == "api"
    assert "score" not in run
    assert "extra" not in run
    assert "checks" not in run


def test_repair_service_returns_markdown_artifact_not_document_ir():
    src = "公式 (19) 中 n=12。\n"

    def chat(md: str, part: int, total: int) -> str:
        return "公式 (19) 中 n=13。\n"

    result, artifact = RepairService().run(src, RepairConfig(), chat_fn=chat)
    assert isinstance(artifact, MarkdownArtifact)
    assert artifact.workflow == "格式修正"
    assert "n=12" in artifact.text
    assert not result.ok


class FakeVisionWorker(QObject):
    task_status = Signal(str, str, str)
    task_finished = Signal(str, bool, str, str, str, float)
    log_line = Signal(str)
    stage = Signal(str)
    pipeline_stage = Signal(str)
    needs_clipboard = Signal(str, int, int, int, str)
    needs_user = Signal(str, str)
    needs_figures = Signal(str, str)
    progress = Signal(str, object)
    finished = Signal()

    def __init__(self, tasks, parent=None, *, script: str = "complete", **kwargs) -> None:
        super().__init__(parent)
        self.tasks = list(tasks)
        self.captured = dict(kwargs)
        self.script = script
        self._running = False
        self._cancel = False
        self.clipboard = ""

    def isRunning(self) -> bool:
        return self._running

    def request_cancel(self) -> None:
        self._cancel = True

    def submit_clipboard(self, text: str) -> None:
        self.clipboard = text

    def resume_after_user(self) -> None:
        return None

    def wait(self, _ms: int = 0) -> None:
        self._running = False

    def start(self) -> None:
        self._running = True
        QTimer.singleShot(0, self._tick)

    def _tick(self) -> None:
        task = self.tasks[0]
        if self.script == "hold":
            if self._cancel:
                self.task_status.emit(task.id, TaskStatus.CANCELLED.value, "已取消")
                self._running = False
                self.finished.emit()
                return
            QTimer.singleShot(0, self._tick)
            return
        self.task_status.emit(task.id, TaskStatus.RUNNING.value, "页面渲染")
        self.pipeline_stage.emit("render")
        self.progress.emit("视觉转录 6/30 页（第 2 批 0007–0012）", 40)
        self.task_finished.emit(task.id, True, "a.md", str(Path("out")), "", 0.2)
        self.pipeline_stage.emit("idle")
        self._running = False
        self.finished.emit()


class FakeDailyWorker(QObject):
    finished_ok = Signal(str, str, str)
    finished_archive = Signal(str, str, str)
    log_line = Signal(str)
    progress = Signal(str, object)
    finished = Signal()

    def __init__(self, paths, parent=None, *, archive=False, archive_dir=None, **kwargs) -> None:
        super().__init__(parent)
        self.paths = list(paths)
        self.archive = archive
        self.archive_dir = archive_dir
        self._running = False

    def isRunning(self) -> bool:
        return self._running

    def request_cancel(self) -> None:
        return None

    def wait(self, _ms: int = 0) -> None:
        self._running = False

    def start(self) -> None:
        self._running = True
        QTimer.singleShot(0, self._tick)

    def _tick(self) -> None:
        self.progress.emit("第 1/2 批 · 已接收 800 字", 46)
        self.progress.emit("识别完成", 100)
        if self.archive:
            self.finished_archive.emit("out/document.md", "", "")
        else:
            self.finished_ok.emit("# hello", "", "")
        self._running = False
        self.finished.emit()


class FakeRepairWorker(QObject):
    finished_result = Signal(object)
    failed = Signal(str)
    progress = Signal(str, object)
    finished = Signal()

    def __init__(self, text, config, parent=None, **kwargs) -> None:
        super().__init__(parent)
        self.text = text
        self.config = config
        self.captured = dict(kwargs)
        self._running = False

    def isRunning(self) -> bool:
        return self._running

    def request_cancel(self) -> None:
        return None

    def wait(self, _ms: int = 0) -> None:
        self._running = False

    def start(self) -> None:
        self._running = True
        QTimer.singleShot(0, self._tick)

    def _tick(self) -> None:
        self.finished_result.emit(type("R", (), {"ok": True, "output_text": self.text})())
        self._running = False
        self.finished.emit()


def test_vision_controller_start_and_cancel(tmp_path: Path):
    app = _app()
    captured: dict = {}

    def factory(tasks, parent=None, **kwargs):
        captured.update(kwargs)
        return FakeVisionWorker(tasks, parent=parent, script="complete", **kwargs)

    ctrl = VisionController(worker_factory=factory)
    states: list[VisionViewState] = []
    ctrl.view_state_changed.connect(states.append)
    finished = []
    events: list[tuple[str, object]] = []
    ctrl.progress.connect(lambda text, percent: events.append((text, percent)))
    ctrl.batch_finished.connect(lambda: finished.append(True))
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    ok = ctrl.start(
        [ConvertTask(pdf_path=pdf)],
        VisionUiInputs(output_root=tmp_path / "out", api=True, api_precision="standard"),
    )
    assert ok
    _pump(app, lambda: finished)
    assert finished
    assert states[-1].running is False
    assert captured["config"].effective_backend() == "api"
    snap = ctrl.options_snapshot
    assert snap is not None and snap.api is True
    # 页级进度必须转发到 UI
    assert events == [("视觉转录 6/30 页（第 2 批 0007–0012）", 40)]

    def hold(tasks, parent=None, **kwargs):
        return FakeVisionWorker(tasks, parent=parent, script="hold", **kwargs)

    ctrl2 = VisionController(worker_factory=hold)
    done = []
    ctrl2.batch_finished.connect(lambda: done.append(True))
    assert ctrl2.start([ConvertTask(pdf_path=pdf)], VisionUiInputs(output_root=tmp_path))
    app.processEvents()
    assert ctrl2.is_running()
    assert ctrl2.start([ConvertTask(pdf_path=pdf)], VisionUiInputs(output_root=tmp_path)) is False
    ctrl2.cancel()
    _pump(app, lambda: done)
    assert done
    assert not ctrl2.is_running()


def test_vision_stage_percent_maps_real_pages():
    from app.core.service.vision import (
        FIGURES_PERCENT,
        MERGE_PERCENT,
        RENDER_END,
        TRANSCRIBE_END,
        stage_percent,
    )

    assert stage_percent("render", 0, 30) == 0
    assert stage_percent("render", 30, 30) == RENDER_END
    assert stage_percent("transcribe", 0, 30) == RENDER_END
    assert stage_percent("transcribe", 30, 30) == TRANSCRIBE_END
    assert stage_percent("transcribe", 15, 30) == (RENDER_END + TRANSCRIBE_END) // 2
    # 页数越界不再增长
    assert stage_percent("transcribe", 99, 30) == TRANSCRIBE_END
    assert stage_percent("merge", 0, 0) == MERGE_PERCENT
    assert RENDER_END < TRANSCRIBE_END < MERGE_PERCENT < FIGURES_PERCENT <= 100


def test_vision_service_progress_scales_across_tasks(tmp_path: Path):
    from app.core.service import vision as vision_mod
    from app.vision_transcribe.config import VisionConfig

    def _service() -> tuple[vision_mod.VisionService, list[tuple[int, str]]]:
        events: list[tuple[int, str]] = []
        svc = vision_mod.VisionService(
            VisionConfig(vision_backend="api"),
            tmp_path,
            True,
            hooks=vision_mod.VisionHooks(on_progress=lambda p, t: events.append((p, t))),
        )
        return svc, events

    # 单篇任务：原样透传
    svc, events = _service()
    svc._emit_progress(50, "半程")
    assert events[-1] == (50, "半程")

    # 批次重试回到早期阶段：只前进，不倒退
    svc._emit_progress(20, "批次重试")
    assert events[-1] == (50, "批次重试")

    # 多篇任务：单篇完成度折算到整批区间（第 2/4 篇完成 = 50%）
    svc2, events2 = _service()
    svc2._task_index = 1
    svc2._task_total = 4
    svc2._emit_progress(0, "第 2 篇开始")
    assert events2[-1] == (25, "第 2 篇开始")
    svc2._emit_progress(100, "第 2 篇完成")
    assert events2[-1] == (50, "第 2 篇完成")


def test_vision_service_batch_progress_callback_order():
    """流式回调顺序回归：StreamProgress 传 (文本, 百分比)，服务收 (百分比, 文本)。"""
    from app.core.service import vision as vision_mod
    from app.utils.progress import StreamProgress
    from app.vision_transcribe.config import VisionConfig

    events: list[tuple[int, str]] = []
    svc = vision_mod.VisionService(
        VisionConfig(vision_backend="api"),
        Path("."),
        True,
        hooks=vision_mod.VisionHooks(on_progress=lambda p, t: events.append((p, t))),
    )
    adapter = type(
        "FakeAdapter",
        (),
        {"set_progress_callback": lambda self, cb: setattr(self, "cb", cb)},
    )()
    pipe = type("FakePipe", (), {"get_adapter": lambda self: adapter})()

    reporter = StreamProgress(
        lambda text, percent: svc._emit_progress(percent, text),
        base=25,
        span=60,
        label="第 1 批 PAGE 0001–0003",
    )
    svc._attach_batch_progress(pipe, reporter)
    adapter.cb(500)  # 网关回调：已接收 500 字
    adapter.cb(2400)

    assert len(events) == 2
    assert all(25 <= percent < 85 for percent, _t in events)
    assert "已接收 500 字" in events[0][1]
    assert events[1][0] > events[0][0]


def test_vision_worker_bridges_progress_hook():
    app = _app()
    from app.workers.vision_worker import VisionConversionWorker

    worker = VisionConversionWorker([], output_root=Path("out"), per_folder=True)
    events: list[tuple[str, object]] = []
    worker.progress.connect(lambda text, percent: events.append((text, percent)))
    hooks = worker._make_hooks()
    hooks.on_progress(42, "视觉转录 6/30 页")
    app.processEvents()
    assert events == [("视觉转录 6/30 页", 42)]


def test_command_bar_progress_determinate_and_indeterminate():
    _app()
    from app.ui.widgets.command_bar import CommandBar

    bar = CommandBar()
    bar.set_running(True)
    bar.set_progress(None)
    assert bar.progress.maximum() == 0  # 不确定：结构化引擎无页级进度

    bar.set_progress(42)
    assert bar.progress.maximum() == 100
    assert bar.progress.value() == 42

    bar.set_progress(240)  # 越界夹紧
    assert bar.progress.value() == 100
    bar.set_running(False)
    assert bar.progress.isHidden()


def test_daily_controller_snapshot(tmp_path: Path):
    app = _app()
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG")
    finished = []
    events: list[tuple[str, object]] = []

    def factory(*args, **kwargs):
        return FakeDailyWorker(*args, **kwargs)

    ctrl = DailyVisionController(worker_factory=factory)
    ctrl.batch_finished.connect(lambda: finished.append(True))
    ctrl.progress.connect(lambda text, percent: events.append((text, percent)))
    ok = ctrl.start(DailyVisionUiInputs(image_paths=(img,), archive=False))
    assert ok
    _pump(app, lambda: finished)
    assert finished
    snap = ctrl.inputs_snapshot
    assert snap is not None
    assert snap.image_paths == (img,)
    assert snap.archive is False
    # 日常识图进度必须转发到 UI（阶段文本 + 真实百分比）
    assert [p for _t, p in events] == [46, 100]
    assert "已接收" in events[0][0]


def test_daily_pipeline_reports_stage_progress(tmp_path: Path, monkeypatch):
    from app.daily_vision import pipeline as daily_pipeline

    images = []
    for i in range(3):
        img = tmp_path / f"a{i}.png"
        img.write_bytes(b"\x89PNG")
        images.append(img)
    events: list[tuple[str, object]] = []
    prompts: list[str] = []

    class StubClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def vision_json(self, batch, prompt, **kwargs) -> dict:
            assert kwargs.get("on_delta") is not None  # 必须走流式进度
            kwargs["on_delta"](600)  # 模拟流式已接收字数
            kwargs["on_delta"](2400)
            prompts.append(prompt)
            return {
                "markdown": "<!-- PDF2MD:IMAGE:i0001:f01 -->\n\n文字。",
                "regions": [
                    {
                        "marker": "i0001:f01",
                        "source_image": 1,
                        "type": "figure",
                        "bbox": [0.1, 0.1, 0.9, 0.9],
                    }
                ],
            }

    monkeypatch.setattr(daily_pipeline, "DeepSeekClient", StubClient)
    pipe = daily_pipeline.DailyVisionPipeline()
    result = pipe.transcribe(
        images, progress=lambda text, percent: events.append((text, percent))
    )

    assert result.markdown.startswith("<!-- PDF2MD:IMAGE:i0001:f01 -->")
    percents = [p for _t, p in events]
    assert percents == sorted(percents)  # 进度只能前进
    assert percents[-1] == daily_pipeline.MODEL_PERCENT  # 单批走完模型阶段
    assert any("已接收" in t for t, _p in events)
    assert "本次共 3 张图片" in prompts[0]
    assert len(result.regions) == 1 and result.regions[0].source_image == 1
    assert result.warnings == []


def test_daily_pipeline_batches_and_renumbers(tmp_path: Path, monkeypatch):
    from app.daily_vision import pipeline as daily_pipeline

    images = []
    for i in range(13):
        img = tmp_path / f"p{i:02d}.png"
        img.write_bytes(b"\x89PNG")
        images.append(img)

    prompts: list[str] = []
    batches_seen: list[int] = []

    class StubClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def vision_json(self, batch, prompt, **kwargs) -> dict:
            batches_seen.append(len(batch))
            prompts.append(prompt)
            return {
                "markdown": "<!-- PDF2MD:IMAGE:i0001:f01 -->",
                "regions": [
                    {
                        "marker": "i0001:f01",
                        "source_image": 1,
                        "type": "figure",
                        "bbox": [0.0, 0.0, 1.0, 1.0],
                    }
                ],
            }

    monkeypatch.setattr(daily_pipeline, "DeepSeekClient", StubClient)
    pipe = daily_pipeline.DailyVisionPipeline()
    result = pipe.transcribe(images)

    assert batches_seen == [6, 6, 1]  # 39 张也不会再一次塞满
    assert "本次共 6 张图片" in prompts[0]
    assert "本次共 1 张图片" in prompts[2]
    assert "i0001:f01" in result.markdown
    assert "i0007:f01" in result.markdown
    assert "i0013:f01" in result.markdown
    assert [r.source_image for r in result.regions] == [1, 7, 13]
    assert [r.marker for r in result.regions] == ["i0001:f01", "i0007:f01", "i0013:f01"]


def test_daily_pipeline_keeps_going_when_one_batch_fails(tmp_path: Path, monkeypatch):
    from app.daily_vision import pipeline as daily_pipeline
    from app.deepseek_api.errors import ModelError

    images = []
    for i in range(13):
        img = tmp_path / f"q{i:02d}.png"
        img.write_bytes(b"\x89PNG")
        images.append(img)

    calls = {"n": 0}

    class StubClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def vision_json(self, batch, prompt, **kwargs) -> dict:
            calls["n"] += 1
            if calls["n"] == 2:
                raise ModelError("HTTP 500: boom")
            return {"markdown": "<!-- PDF2MD:IMAGE:i0001:f01 -->", "regions": []}

    monkeypatch.setattr(daily_pipeline, "DeepSeekClient", StubClient)
    pipe = daily_pipeline.DailyVisionPipeline()
    result = pipe.transcribe(images)

    assert "i0001:f01" in result.markdown
    assert result.warnings and "第 2/3 批失败" in result.warnings[0]


def test_daily_pipeline_fails_when_all_batches_fail(tmp_path: Path, monkeypatch):
    from app.daily_vision import pipeline as daily_pipeline
    from app.deepseek_api.errors import ModelError

    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG")

    class StubClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def vision_json(self, batch, prompt, **kwargs) -> dict:
            raise ModelError("HTTP 500: boom")

    monkeypatch.setattr(daily_pipeline, "DeepSeekClient", StubClient)
    pipe = daily_pipeline.DailyVisionPipeline()
    try:
        pipe.transcribe([img])
    except ValueError as exc:
        assert "第 1/1 批失败" in str(exc)
    else:  # pragma: no cover - 必须抛错
        raise AssertionError("全部批次失败时必须报错")


def test_daily_pipeline_cancels_between_batches_and_midstream(tmp_path: Path, monkeypatch):
    from app.daily_vision import pipeline as daily_pipeline
    from app.daily_vision.models import DailyVisionCancelled

    images = []
    for i in range(13):
        img = tmp_path / f"c{i:02d}.png"
        img.write_bytes(b"\x89PNG")
        images.append(img)

    class StubClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def vision_json(self, batch, prompt, **kwargs) -> dict:
            return {"markdown": "文字", "regions": []}

    monkeypatch.setattr(daily_pipeline, "DeepSeekClient", StubClient)
    pipe = daily_pipeline.DailyVisionPipeline()

    calls = {"n": 0}

    def cancelled_between() -> bool:
        calls["n"] += 1
        return calls["n"] > 2  # 前两批正常跑，第三批之前取消

    try:
        pipe.transcribe(images, cancelled=cancelled_between)
    except DailyVisionCancelled:
        pass
    else:  # pragma: no cover - 必须在批次之间停下
        raise AssertionError("批次之间必须响应取消")

    # 流式接收中取消：回调里立刻抛
    class StreamingClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def vision_json(self, batch, prompt, **kwargs) -> dict:
            kwargs["on_delta"](100)
            return {"markdown": "文字", "regions": []}

    monkeypatch.setattr(daily_pipeline, "DeepSeekClient", StreamingClient)
    pipe2 = daily_pipeline.DailyVisionPipeline()
    state = {"flag": False}

    def on_progress(_text, _percent):
        state["flag"] = True  # 收到第一段进度后，下一次回调即取消

    try:
        pipe2.transcribe([images[0]], progress=on_progress, cancelled=lambda: state["flag"])
    except DailyVisionCancelled:
        pass
    else:  # pragma: no cover - 流式回调必须响应取消
        raise AssertionError("流式接收中必须响应取消")


def test_daily_worker_threads_progress_to_controller(tmp_path: Path, monkeypatch):
    """真 Worker（QThread）+ 桩 Pipeline：进度必须跨线程回到控制器。"""
    from app.core.service import daily_vision as daily_service
    from app.daily_vision.models import DailyVisionResult

    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG")

    class StubPipeline:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def transcribe(self, paths, *, progress=None, cancelled=None) -> DailyVisionResult:
            emit = progress or (lambda _t, _p: None)
            emit("第 1/2 批 · 已接收 800 字", 46)
            emit("已完成 6/13 张", 50)
            result = DailyVisionResult(markdown="# ok", regions=[])
            result.warnings.append("第 2/2 批失败：HTTP 500")
            return result

    monkeypatch.setattr(daily_service, "DailyVisionPipeline", StubPipeline)

    app = _app()
    events: list[tuple[str, object]] = []
    finished: list[bool] = []
    warnings: list[str] = []
    ctrl = DailyVisionController()
    ctrl.progress.connect(lambda text, percent: events.append((text, percent)))
    ctrl.finished_ok.connect(lambda _md, _err, warn: warnings.append(warn))
    ctrl.batch_finished.connect(lambda: finished.append(True))

    assert ctrl.start(DailyVisionUiInputs(image_paths=(img,), archive=False))
    _pump(app, lambda: finished)

    assert finished
    # 流式阶段 46 → 已完成 50 → 服务收尾 100
    assert [p for _t, p in events] == [46, 50, 100]
    assert any("已接收" in t for t, _p in events)
    assert warnings == ["第 2/2 批失败：HTTP 500"]  # 批次失败必须传到 UI
    assert ctrl.inputs_snapshot is not None


def test_repair_controller_fake_worker():
    app = _app()
    finished = []
    states: list[RepairViewState] = []
    events: list[tuple[str, object]] = []

    def factory(*args, **kwargs):
        return FakeRepairWorker(*args, **kwargs)

    ctrl = RepairController(worker_factory=factory)
    ctrl.view_state_changed.connect(states.append)
    ctrl.progress.connect(lambda text, percent: events.append((text, percent)))
    ctrl.batch_finished.connect(lambda: finished.append(True))
    assert ctrl.start(RepairUiInputs(text="# t\n", config=RepairConfig()))
    _pump(app, lambda: finished)
    assert finished
    assert states[-1].running is False
    assert ctrl.start(RepairUiInputs(text="   ", config=RepairConfig())) is False
    assert ctrl.cancelled is False


def test_format_repair_pipeline_reports_progress(tmp_path: Path, monkeypatch):
    """格式修正：按段推进 + 段内流式字数，进度只前进。"""
    from app.format_repair import pipeline as repair_pipeline
    from app.format_repair.chunker import split_markdown_chunks

    body = "\n\n".join(f"## 段{i}\n\n" + ("正文内容。\n" * 1600) for i in range(3))
    expected_chunks = len(split_markdown_chunks(body))
    assert expected_chunks >= 3  # 确认确实是多段
    events: list[tuple[str, object]] = []

    def fake_chat(md, part, total):
        return md  # 原样返回 → 通过完整性门

    result = repair_pipeline.repair_text(
        body,
        config=repair_pipeline.RepairConfig(),
        chat_fn=fake_chat,
        progress=lambda text, percent: events.append((text, percent)),
    )

    assert result.report["chunks"] == expected_chunks
    assert result.ok
    percents = [p for _t, p in events]
    assert percents == sorted(percents)
    assert percents[0] == 0 and percents[-1] == repair_pipeline.MODEL_PERCENT
    assert any(f"第 1/{expected_chunks} 段" in t for t, _p in events)
    assert any(f"已完成 {expected_chunks}/{expected_chunks} 段" in t for t, _p in events)


def test_format_repair_pipeline_streams_and_cancels(tmp_path: Path):
    from app.format_repair import pipeline as repair_pipeline
    from app.utils.progress import PipelineCancelled

    body = "## 标题\n\n" + ("正文。\n" * 2000)
    events: list[tuple[str, object]] = []

    def fake_chat(md, part, total):
        return md

    repair_pipeline.repair_text(
        body,
        config=repair_pipeline.RepairConfig(),
        chat_fn=fake_chat,
        progress=lambda text, percent: events.append((text, percent)),
    )
    assert events[-1][1] == repair_pipeline.MODEL_PERCENT

    # 取消：段间检查立即生效
    try:
        repair_pipeline.repair_text(
            body,
            config=repair_pipeline.RepairConfig(),
            chat_fn=fake_chat,
            cancelled=lambda: True,
        )
    except PipelineCancelled:
        pass
    else:  # pragma: no cover - 必须响应取消
        raise AssertionError("格式修正必须在段间响应取消")


def test_worker_sources_are_qt_bridges():
    vision = Path("app/workers/vision_worker.py").read_text(encoding="utf-8")
    assert "VisionService" in vision
    assert "VisionPipeline(" not in vision
    assert "plan_batch_recovery" not in vision
    daily = Path("app/workers/daily_vision_worker.py").read_text(encoding="utf-8")
    assert "DailyVisionService" in daily
    assert "DailyVisionPipeline(" not in daily
    repair = Path("app/workers/format_repair_worker.py").read_text(encoding="utf-8")
    assert "RepairService" in repair
    assert "repair_text(" not in repair


def test_controllers_do_not_import_pipelines():
    forbidden = (
        "app.vision_transcribe.pipeline",
        "app.vision_transcribe.recovery",
        "app.daily_vision.pipeline",
        "app.format_repair.pipeline",
        "app.core.providers",
        "app.core.pipeline",
    )
    for rel in (
        "app/ui/vision_controller.py",
        "app/ui/daily_vision_controller.py",
        "app/ui/repair_controller.py",
    ):
        imported = _imported_modules(Path(rel))
        text = Path(rel).read_text(encoding="utf-8")
        for name in imported:
            assert not any(name == p or name.startswith(p + ".") for p in forbidden), (rel, name)
        assert "scan_ratio" not in text
        assert "VisionPipeline" not in text
        assert "repair_text" not in text
