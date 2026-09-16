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
        self.task_finished.emit(task.id, True, "a.md", str(Path("out")), "", 0.2)
        self.pipeline_stage.emit("idle")
        self._running = False
        self.finished.emit()


class FakeDailyWorker(QObject):
    finished_ok = Signal(str, str)
    finished_archive = Signal(str, str)
    log_line = Signal(str)
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
        if self.archive:
            self.finished_archive.emit("out/document.md", "")
        else:
            self.finished_ok.emit("# hello", "")
        self._running = False
        self.finished.emit()


class FakeRepairWorker(QObject):
    finished_result = Signal(object)
    failed = Signal(str)
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


def test_daily_controller_snapshot(tmp_path: Path):
    app = _app()
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG")
    finished = []

    def factory(*args, **kwargs):
        return FakeDailyWorker(*args, **kwargs)

    ctrl = DailyVisionController(worker_factory=factory)
    ctrl.batch_finished.connect(lambda: finished.append(True))
    ok = ctrl.start(DailyVisionUiInputs(image_paths=(img,), archive=False))
    assert ok
    _pump(app, lambda: finished)
    assert finished
    snap = ctrl.inputs_snapshot
    assert snap is not None
    assert snap.image_paths == (img,)
    assert snap.archive is False


def test_repair_controller_fake_worker():
    app = _app()
    finished = []
    states: list[RepairViewState] = []

    def factory(*args, **kwargs):
        return FakeRepairWorker(*args, **kwargs)

    ctrl = RepairController(worker_factory=factory)
    ctrl.view_state_changed.connect(states.append)
    ctrl.batch_finished.connect(lambda: finished.append(True))
    assert ctrl.start(RepairUiInputs(text="# t\n", config=RepairConfig()))
    _pump(app, lambda: finished)
    assert finished
    assert states[-1].running is False
    assert ctrl.start(RepairUiInputs(text="   ", config=RepairConfig())) is False


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
