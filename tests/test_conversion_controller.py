"""R6 ConversionController：生命周期与配置快照，不跑真实 PDF。"""
from __future__ import annotations

import ast
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from app.core.domain.quality import QualityVerdict
from app.task_model import ConvertTask, TaskStatus
from app.ui.conversion_controller import (
    ConversionController,
    ConversionUiInputs,
    ConversionViewState,
    compile_options,
    present_result_status,
)


def _app() -> QApplication:
    inst = QApplication.instance()
    if inst is not None:
        return inst
    return QApplication([])


def _task(tmp_path: Path) -> ConvertTask:
    return ConvertTask(pdf_path=tmp_path / "paper.pdf")


def _inputs(tmp_path: Path, **kw) -> ConversionUiInputs:
    base = dict(
        output_root=tmp_path / "out",
        per_folder=True,
        ocr_mode="auto",
        keep_tables=True,
        formulas_checked=True,
        formula_recovery_preset="balanced",
        deepseek_lp_checked=False,
        export_md=True,
    )
    base.update(kw)
    return ConversionUiInputs(**base)


class FakeConversionWorker(QObject):
    task_status = Signal(str, str, str)
    task_finished = Signal(str, bool, str, str, str, float)
    quality_status = Signal(str, str)
    log_line = Signal(str)
    stage = Signal(str)
    pipeline_stage = Signal(str)
    deepseek_state = Signal(str)
    finished = Signal()

    def __init__(self, tasks, parent=None, *, script: str = "complete", **kwargs) -> None:
        super().__init__(parent)
        self.tasks = list(tasks)
        self.captured = dict(kwargs)
        self.script = script
        self._running = False
        self._cancel = False

    def isRunning(self) -> bool:
        return self._running

    def request_cancel(self) -> None:
        self._cancel = True

    def wait(self, _ms: int = 0) -> None:
        self._running = False

    def start(self) -> None:
        self._running = True
        QTimer.singleShot(0, self._tick)

    def _tick(self) -> None:
        task = self.tasks[0]
        if self.script == "hold" or (self.script == "complete" and self._cancel):
            if self._cancel:
                self.task_status.emit(task.id, TaskStatus.CANCELLED.value, "已取消")
                self._running = False
                self.finished.emit()
                return
            if self.script == "hold":
                QTimer.singleShot(0, self._tick)
                return
        self.task_status.emit(task.id, TaskStatus.RUNNING.value, "开始转换")
        self.stage.emit("解析中")
        self.pipeline_stage.emit("parse")
        if self._cancel:
            self.task_status.emit(task.id, TaskStatus.CANCELLED.value, "已取消")
            self._running = False
            self.finished.emit()
            return
        if self.script == "fail":
            self.quality_status.emit(task.id, QualityVerdict.FAILED.value)
            self.task_finished.emit(task.id, False, "", str(Path("out")), "boom", 0.1)
        else:
            self.quality_status.emit(task.id, QualityVerdict.VERIFIED.value)
            self.task_finished.emit(task.id, True, "a.md", str(Path("out")), "", 0.2)
        self.pipeline_stage.emit("idle")
        self._running = False
        self.finished.emit()


def _pump(app: QApplication, pred, rounds: int = 80) -> None:
    import time

    for _ in range(rounds):
        app.processEvents()
        if pred():
            return
        time.sleep(0.01)


def test_compile_options_lean_balanced(tmp_path: Path):
    opts = compile_options(
        _inputs(tmp_path, formulas_checked=True, deepseek_lp_checked=True)
    )
    assert opts.deepseek_limited_production is True
    assert opts.keep_formulas is False
    assert opts.docling_formula_enrich is False
    assert opts.repair_keep_formulas is True


def test_present_result_status_uses_quality_not_recompute():
    assert present_result_status(cancelled=True, ok=True, quality_status="FAILED") == "cancelled"
    assert (
        present_result_status(
            cancelled=False, ok=True, quality_status=QualityVerdict.WARNINGS.value
        )
        == QualityVerdict.WARNINGS.value
    )
    assert (
        present_result_status(cancelled=False, ok=True, quality_status=None)
        == QualityVerdict.VERIFIED.value
    )
    assert (
        present_result_status(cancelled=False, ok=False, quality_status=None)
        == QualityVerdict.FAILED.value
    )


def test_controller_start_progress_complete(tmp_path: Path):
    app = _app()
    captured: dict = {}

    def factory(tasks, parent=None, **kwargs):
        captured.update(kwargs)
        return FakeConversionWorker(tasks, parent=parent, script="complete", **kwargs)

    ctrl = ConversionController(worker_factory=factory)
    states: list[ConversionViewState] = []
    ctrl.view_state_changed.connect(states.append)
    finished = []
    ctrl.batch_finished.connect(lambda: finished.append(True))
    ok = ctrl.start([_task(tmp_path)], _inputs(tmp_path, formulas_checked=True))
    assert ok
    _pump(app, lambda: finished)
    assert finished
    assert any(s.running for s in states)
    assert states[-1].running is False
    assert states[-1].result_status == QualityVerdict.VERIFIED.value
    assert not ctrl.is_running()
    assert captured["keep_formulas"] is True


def test_controller_fail_maps_quality(tmp_path: Path):
    app = _app()

    def factory(tasks, parent=None, **kwargs):
        return FakeConversionWorker(tasks, parent=parent, script="fail", **kwargs)

    ctrl = ConversionController(worker_factory=factory)
    states: list[ConversionViewState] = []
    ctrl.view_state_changed.connect(states.append)
    finished = []
    ctrl.batch_finished.connect(lambda: finished.append(True))
    ctrl.start([_task(tmp_path)], _inputs(tmp_path))
    _pump(app, lambda: finished)
    assert states[-1].result_status == QualityVerdict.FAILED.value
    assert states[-1].running is False


def test_controller_cancel(tmp_path: Path):
    app = _app()

    def factory(tasks, parent=None, **kwargs):
        return FakeConversionWorker(tasks, parent=parent, script="hold", **kwargs)

    ctrl = ConversionController(worker_factory=factory)
    states: list[ConversionViewState] = []
    ctrl.view_state_changed.connect(states.append)
    finished = []
    ctrl.batch_finished.connect(lambda: finished.append(True))
    assert ctrl.start([_task(tmp_path)], _inputs(tmp_path))
    app.processEvents()
    assert ctrl.is_running()
    assert ctrl.start([_task(tmp_path)], _inputs(tmp_path)) is False
    ctrl.cancel()
    _pump(app, lambda: finished)
    assert finished
    assert any(s.result_status == "cancelled" for s in states)
    assert states[-1].running is False
    assert not ctrl.is_running()


def test_ui_param_change_after_start_does_not_mutate_snapshot(tmp_path: Path):
    app = _app()

    def factory(tasks, parent=None, **kwargs):
        return FakeConversionWorker(tasks, parent=parent, script="hold", **kwargs)

    ctrl = ConversionController(worker_factory=factory)
    finished = []
    ctrl.batch_finished.connect(lambda: finished.append(True))
    inputs = _inputs(tmp_path, formulas_checked=True, deepseek_lp_checked=False)
    assert ctrl.start([_task(tmp_path)], inputs)
    snap = ctrl.options_snapshot
    assert snap is not None
    assert snap.keep_formulas is True
    later = compile_options(_inputs(tmp_path, formulas_checked=False, deepseek_lp_checked=True))
    assert later.keep_formulas is False
    assert ctrl.options_snapshot is snap
    assert ctrl.options_snapshot.keep_formulas is True
    assert ctrl.options_snapshot.deepseek_limited_production is False
    ctrl.cancel()
    _pump(app, lambda: finished)


def test_controller_source_has_no_pipeline_imports():
    path = Path("app/ui/conversion_controller.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = (
        "app.core.providers",
        "app.core.pipeline",
        "app.repair",
        "app.formula",
        "app.engines",
        "app.assets",
        "app.ocr",
    )
    for name in imported:
        assert not any(name == p or name.startswith(p + ".") for p in forbidden), name
    text = path.read_text(encoding="utf-8")
    assert "scan_ratio" not in text
    assert "RepairPipeline" not in text
    assert "DoclingProvider" not in text
