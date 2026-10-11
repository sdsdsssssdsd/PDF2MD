"""日常识图「陆续加图」会话：队列累加 / 跨轮偏移合并 / 链式续跑 / 会话级归档。"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from app.daily_vision.models import DailyVisionResult, FigureRegion
from app.daily_vision.session import DailyVisionSession
from app.ui.widgets.daily_vision_workspace import DailyVisionWorkspace, is_pasted_image

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _images(tmp_path: Path, count: int, prefix: str = "img") -> list[Path]:
    out = []
    for i in range(count):
        path = tmp_path / f"{prefix}{i:02d}.png"
        path.write_bytes(_TINY_PNG)
        out.append(path)
    return out


# —— 会话累加器 ——
def test_session_appends_dedupes_and_reports_pending(tmp_path: Path):
    a, b, c = _images(tmp_path, 3)
    session = DailyVisionSession()
    assert session.add_images([a, b]) == [a, b]
    assert session.add_images([b, c, a]) == [c]  # 重复图片不再收
    assert session.images == [a, b, c]
    assert session.pending() == [a, b, c]
    assert session.counts() == (0, 3)

    session.merge_run([a], DailyVisionResult(markdown="第一张"))
    assert session.done == 1
    assert session.pending() == [b, c]
    assert not session.is_drained()


def test_session_merge_shifts_markers_across_rounds(tmp_path: Path):
    a, b = _images(tmp_path, 2)
    session = DailyVisionSession()
    session.add_images([a])
    session.merge_run(
        [a],
        DailyVisionResult(
            markdown="<!-- PDF2MD:IMAGE:i0001:f01 -->\n\n第一张正文",
            regions=[FigureRegion(marker="i0001:f01", source_image=1, bbox=[0.1, 0.1, 0.9, 0.9])],
        ),
    )
    # 第二轮：模型又从 i0001 开始编号，必须平移成 i0002
    session.add_images([b])
    session.merge_run(
        [b],
        DailyVisionResult(
            markdown="<!-- PDF2MD:IMAGE:i0001:f02 -->\n\n第二张正文",
            regions=[FigureRegion(marker="i0001:f02", source_image=1, bbox=[0.2, 0.2, 0.8, 0.8])],
        ),
    )
    md = session.result.markdown
    assert "第一张正文" in md and "第二张正文" in md
    assert md.index("第一张正文") < md.index("第二张正文")  # 顺序按加图顺序
    assert "i0001:f01" in md and "i0002:f02" in md
    assert [r.source_image for r in session.result.regions] == [1, 2]
    assert session.counts() == (2, 2)


def test_session_payload_round_trip(tmp_path: Path):
    a, b = _images(tmp_path, 2)
    session = DailyVisionSession()
    session.add_images([a, b])
    session.merge_run(
        [a],
        DailyVisionResult(
            markdown="<!-- PDF2MD:IMAGE:i0001:f01 -->",
            regions=[FigureRegion(marker="i0001:f01", source_image=1, bbox=[0, 0, 1, 1])],
        ),
    )
    payload = session.to_payload()
    assert json.loads(json.dumps(payload))  # 必须可 JSON 序列化（跨线程/落盘）
    restored = DailyVisionSession.from_payload(payload)
    assert [str(p) for p in restored.images] == [str(a), str(b)]
    assert restored.done == 1
    assert restored.pending() == [b]
    assert restored.result.markdown == session.result.markdown
    assert restored.result.regions[0].marker == "i0001:f01"
    assert restored.result.regions[0].bbox == [0.0, 0.0, 1.0, 1.0]
    assert DailyVisionSession.from_payload(None).images == []


# —— 服务：多轮累加 + 部分结果 + 只归档 ——
class _StubPipeline:
    """每轮返回固定正文；记录调用次数。"""

    calls: list[list[Path]] = []
    partial_enabled = False

    def __init__(self, *args, **kwargs) -> None:
        pass

    def transcribe(self, paths, *, progress=None, cancelled=None, on_partial=None):
        type(self).calls.append([Path(p) for p in paths])
        emit = progress or (lambda _t, _p: None)
        emit(f"第 1/1 批 · 已完成 {len(paths)} 张", 90)
        result = DailyVisionResult(markdown=f"<!-- PDF2MD:IMAGE:i0001:f01 -->\n\n{paths[0].stem}")
        if on_partial is not None:
            on_partial(result, len(paths))
        return result


def test_service_accumulates_rounds_with_correct_offset(tmp_path: Path, monkeypatch):
    from app.core.service import daily_vision as service_mod

    a, b = _images(tmp_path, 2)
    _StubPipeline.calls = []
    monkeypatch.setattr(service_mod, "DailyVisionPipeline", _StubPipeline)
    service = service_mod.DailyVisionService()

    first = service.recognize([a])
    assert first.ok
    assert first.session is not None and first.session["images"] == [str(a)]
    second = service.recognize([b], session=first.session)
    assert second.ok
    md = second.markdown
    assert "img00" in md and "img01" in md
    assert "i0001:f01" in md and "i0002:f01" in md  # 第二轮 marker 已平移
    assert second.session is not None
    assert second.session["done"] == [str(a), str(b)]
    assert [c for c in _StubPipeline.calls] == [[a], [b]]  # 每次只发新图片


def test_service_partial_carries_previous_rounds(tmp_path: Path, monkeypatch):
    from app.core.service import daily_vision as service_mod

    a, b = _images(tmp_path, 2)
    monkeypatch.setattr(service_mod, "DailyVisionPipeline", _StubPipeline)
    service = service_mod.DailyVisionService()
    first = service.recognize([a])

    seen: list[tuple[str, int, int]] = []
    service.recognize(
        [b],
        session=first.session,
        on_partial=lambda md, done, total: seen.append((md, done, total)),
    )
    assert seen, "每批完成都要回传部分结果"
    md, done, total = seen[-1]
    assert "img00" in md and "img01" in md  # 部分结果也含上一轮正文
    assert "i0002:f01" in md
    assert (done, total) == (2, 2)


def test_service_archives_whole_session_without_api(tmp_path: Path, monkeypatch):
    from app.core.service import daily_vision as service_mod

    a, b, c = _images(tmp_path, 3)
    monkeypatch.setattr(service_mod, "DailyVisionPipeline", _StubPipeline)
    service = service_mod.DailyVisionService()
    first = service.recognize([a, b])
    _StubPipeline.calls = []

    out = tmp_path / "archive"
    outcome = service.run([], archive=True, archive_dir=out, session=first.session)
    assert outcome.ok and outcome.archive_path
    assert Path(outcome.archive_path).is_file()
    assert _StubPipeline.calls == []  # 只归档：不再调用模型
    sources = sorted((out / "sources").glob("source_*"))
    assert len(sources) == 2  # 归档覆盖整个会话的图片
    assert "img00" in Path(outcome.archive_path).read_text(encoding="utf-8")
    assert c not in [Path(p) for p in (outcome.session or {}).get("images", [])]


def test_service_run_with_session_and_new_images_merges(tmp_path: Path, monkeypatch):
    from app.core.service import daily_vision as service_mod

    a, b = _images(tmp_path, 2)
    monkeypatch.setattr(service_mod, "DailyVisionPipeline", _StubPipeline)
    service = service_mod.DailyVisionService()
    first = service.run([a])
    second = service.run([b], session=first.session)
    assert second.ok
    assert "img00" in second.markdown and "img01" in second.markdown
    assert second.session is not None and len(second.session["done"]) == 2


# —— 工作区队列 ——
def _app():
    from PySide6.QtWidgets import QApplication

    inst = QApplication.instance()
    return inst if inst is not None else QApplication([])


def test_qsettings_are_isolated_from_the_real_profile():
    """回归：测试不能写用户真实配置（曾把「导出目录」污染成 pytest 临时目录）。"""
    from app.dialogs.settings_dialog import settings

    assert "_qsettings" in settings().fileName().replace("\\", "/")
    settings().setValue("output_dir", "Z:/must/never/reach/the/real/profile")
    settings().sync()
    assert settings().value("output_dir") == "Z:/must/never/reach/the/real/profile"


def test_workspace_stream_mode_appends_and_keeps_drop_alive(tmp_path: Path):
    _app()
    ws = DailyVisionWorkspace()
    a, b = _images(tmp_path, 2)
    ws.set_stream_mode(True)

    added: list[list] = []
    requested: list[tuple[list, bool]] = []
    ws.images_added.connect(lambda paths: added.append(paths))
    ws.request_recognize.connect(lambda paths, archive: requested.append((paths, archive)))

    assert ws.add_image_paths([a]) == [a]
    assert ws.add_image_paths([b]) == [b]
    assert ws.add_image_paths([b]) == []  # 重复不重复收
    assert len(ws.image_paths()) == 2
    assert "已收 2 张" in ws.lbl_images.text()
    assert "队列 2 张" in ws.lbl_images.text()
    assert added and added[-1] == [str(b)]
    # 连续收图只发「加了图」，派发交给 MainWindow 防抖，避免同一张被识别两遍
    assert requested == []

    # 识别中仍然可以继续加图（这正是「陆续加图」）
    ws.set_busy(True)
    assert ws.drop.isEnabled()
    assert ws.btn_add.isEnabled()
    assert not ws.btn_finish.isHidden()
    assert not ws.btn_cancel.isHidden()
    assert not ws.btn_clear.isEnabled()
    ws.mark_done([a])
    assert ws.pending_paths() == [b]
    ws.mark_failed([b])
    assert "失败 1 张" in ws.lbl_images.text()
    ws.clear_failed()
    assert ws.failed_paths() == []
    ws.set_busy(False)
    assert ws.btn_finish.isHidden()


def test_workspace_retry_and_archive_request_recognition(tmp_path: Path):
    _app()
    ws = DailyVisionWorkspace()
    a, b = _images(tmp_path, 2)
    ws.set_stream_mode(True)
    requested: list[tuple[list, bool]] = []
    ws.request_recognize.connect(lambda paths, archive: requested.append((paths, archive)))
    ws.add_image_paths([a, b])
    ws.mark_done([a])
    ws.mark_failed([b])

    ws.btn_retry.click()  # 重新识别：把失败的重新排队
    assert requested[-1][0] == [b] and requested[-1][1] is False
    assert ws.failed_paths() == []

    ws.btn_save.click()  # 图文归档：连没识别的也一起归档
    assert requested[-1][1] is True


def test_workspace_single_shot_mode_replaces_queue(tmp_path: Path):
    _app()
    ws = DailyVisionWorkspace()
    a, b = _images(tmp_path, 2)
    ws.set_stream_mode(False)
    ws.add_image_paths([a])
    ws.set_busy(True)
    assert not ws.drop.isEnabled()  # 一次性模式：识别中不能加图
    assert ws.btn_finish.isHidden()
    ws.set_busy(False)
    ws.add_image_paths([b])  # 本次选择为准
    assert ws.image_paths() == [b]
    assert "已收 1 张" in ws.lbl_images.text()


def test_workspace_clear_emits_session_cleared(tmp_path: Path):
    _app()
    ws = DailyVisionWorkspace()
    a = _images(tmp_path, 1)[0]
    seen: list[bool] = []
    ws.session_cleared.connect(lambda: seen.append(True))
    ws.add_image_paths([a])
    ws.mark_done([a])
    ws.clear()
    assert seen == [True]
    assert ws.image_paths() == [] and ws.queue_counts() == (0, 0, 0)


def test_pasted_images_are_recognised_by_path():
    from app.ui.widgets.daily_vision_workspace import PASTE_DIR

    assert is_pasted_image(PASTE_DIR / "paste_x.png")
    assert not is_pasted_image(Path("D:/somewhere/else.png"))


# —— MainWindow 编排：链式续跑 / 会话进度 / 结束会话 / 归档 / 取消 ——
class _FakeDailyCtrl:
    """只记录被派发的输入，不真的起线程。"""

    def __init__(self) -> None:
        self.inputs: list = []
        self.running = False
        self.cancelled = False

    def is_running(self) -> bool:
        return self.running

    def start(self, inputs) -> bool:
        self.inputs.append(inputs)
        self.running = True
        return True

    def cancel(self) -> None:
        self.cancelled = True
        self.running = False

    def shutdown(self, _timeout_ms: int = 3000) -> None:
        self.running = False


def _window(monkeypatch, tmp_path: Path):
    from app.main_window import MainWindow
    from app.vision_api import key_store

    # 没配 Key 时会弹模态框（offscreen 下会卡住测试），这里直接当作已配置
    monkeypatch.setattr(key_store, "api_key_configured", lambda: True)
    _app()
    w = MainWindow()
    fake = _FakeDailyCtrl()
    w._daily = fake
    w.output_edit.setText(str(tmp_path))
    return w, fake


def _finish(w, fake, md: str) -> None:
    """模拟 Worker 跑完：先回传会话快照，再报完成。"""
    fake.running = False
    w._on_daily_finished_ok(md, "", "")


def test_daily_controller_keeps_new_worker_when_old_finished_is_late(tmp_path: Path):
    """回归：链式续跑时，旧 worker 迟到的 finished 不能把新 worker 的引用清掉。"""
    from PySide6.QtCore import QObject, Signal as QtSignal

    from app.ui.daily_vision_controller import DailyVisionController, DailyVisionUiInputs

    _app()
    created: list = []

    class _Worker(QObject):
        finished_ok = QtSignal(str, str, str)
        finished_archive = QtSignal(str, str, str)
        session_state = QtSignal(object)
        partial = QtSignal(str, int, int)
        log_line = QtSignal(str)
        progress = QtSignal(str, object)
        finished = QtSignal()

        def __init__(self, paths, parent=None, **_kwargs) -> None:
            super().__init__(parent)
            self.paths = list(paths)
            self._running = False
            created.append(self)

        def isRunning(self) -> bool:
            return self._running

        def request_cancel(self) -> None:
            self._running = False

        def wait(self, _ms: int = 0) -> None:
            return None

        def start(self) -> None:
            self._running = True

        def finish(self) -> None:
            self._running = False
            self.finished_ok.emit("# md", "", "")
            self.finished.emit()

    a, b = _images(tmp_path, 2)
    ctrl = DailyVisionController(worker_factory=lambda *args, **kw: _Worker(*args, **kw))
    chained: list[int] = []

    def _chain(*_args) -> None:
        chained.append(1)
        if len(created) == 1:
            ctrl.start(DailyVisionUiInputs(image_paths=(b,)))

    ctrl.finished_ok.connect(_chain)
    assert ctrl.start(DailyVisionUiInputs(image_paths=(a,)))
    first = created[0]
    first._running = False  # 线程已经结束，完成回调与 finished 一起送到
    first.finish()

    assert chained == [1]
    assert len(created) == 2
    assert ctrl._worker is created[1]  # 新 worker 不能被旧 finished 清掉
    assert ctrl.is_running() is True


def test_main_window_chains_new_images_into_one_session(monkeypatch, tmp_path: Path):
    w, fake = _window(monkeypatch, tmp_path)
    ws = w.daily_workspace
    ws.set_stream_mode(True)
    a, b = _images(tmp_path, 2)

    ws.add_image_paths([a])
    w._daily_debounce.stop()
    w._start_daily_pending()
    assert len(fake.inputs) == 1
    assert fake.inputs[0].image_paths == (a,)
    assert fake.inputs[0].session["images"] == [str(a)]

    # 识别中又粘贴一张：不打断当前轮，但必须进队列
    ws.add_image_paths([b])
    assert len(fake.inputs) == 1
    assert "已收 2 张" in ws.lbl_images.text()
    assert ws.pending_paths() == [a, b]  # 正在识别的那张也算未完成

    # 第一轮结束 → 自动接着识别新到的那张，仍然是同一个会话
    w._on_daily_session_state(
        {"images": [str(a)], "done": [str(a)], "markdown": "A", "regions": [], "warnings": []}
    )
    _finish(w, fake, "A")
    assert len(fake.inputs) == 2
    assert fake.inputs[1].image_paths == (b,)
    assert fake.inputs[1].session["images"] == [str(a), str(b)]  # 队列持续累加
    assert ws.is_busy()  # 续跑期间保持忙碌，进度条不重置

    # 第二轮结束 → 队列空，收工
    w._on_daily_session_state(
        {
            "images": [str(a), str(b)],
            "done": [str(a), str(b)],
            "markdown": "A\n\nB",
            "regions": [],
            "warnings": [],
        }
    )
    _finish(w, fake, "A\n\nB")
    assert len(fake.inputs) == 2
    assert not ws.is_busy()
    assert "已识别 2 张" in ws.lbl_images.text()
    assert ws.result.toPlainText().strip() == "A\n\nB"
    w.close()


def test_daily_session_progress_never_goes_backwards(monkeypatch, tmp_path: Path):
    w, fake = _window(monkeypatch, tmp_path)
    ws = w.daily_workspace
    ws.set_stream_mode(True)
    a, b, c = _images(tmp_path, 3)

    ws.add_image_paths([a])
    w._daily_debounce.stop()
    w._start_daily_pending()
    w._on_daily_progress("第 1/1 批 · 已接收 400 字", 50)
    assert ws.progress_row.bar.value() == 50  # 目前会话里只有 1 张

    # 跑动中又来了两张：分母变大，条也不能往回退
    ws.add_image_paths([b, c])
    w._on_daily_progress("第 1/1 批：识别中…", 0)
    assert ws.progress_row.bar.value() == 50
    w._on_daily_progress("已完成 1/1 张", 100)
    assert ws.progress_row.bar.value() == 50  # 1/3 = 33 → 夹在 50

    # 续跑第二批：从 50 继续涨到 100
    w._on_daily_session_state(
        {"images": [str(a)], "done": [str(a)], "markdown": "A", "regions": [], "warnings": []}
    )
    _finish(w, fake, "A")
    assert len(fake.inputs) == 2 and fake.inputs[1].image_paths == (b, c)
    w._on_daily_progress("第 1/1 批：识别中…", 0)
    assert ws.progress_row.bar.value() == 50
    w._on_daily_progress("已完成 2/2 张", 100)
    assert ws.progress_row.bar.value() == 100

    w._on_daily_session_state(
        {
            "images": [str(a), str(b), str(c)],
            "done": [str(a), str(b), str(c)],
            "markdown": "A\n\nBC",
            "regions": [],
            "warnings": [],
        }
    )
    _finish(w, fake, "A\n\nBC")
    assert ws.progress_row.bar.value() == 100
    w.close()


def test_daily_finish_request_drains_queue_then_stops(monkeypatch, tmp_path: Path):
    w, fake = _window(monkeypatch, tmp_path)
    ws = w.daily_workspace
    ws.set_stream_mode(True)
    a, b = _images(tmp_path, 2)

    ws.add_image_paths([a])
    w._daily_debounce.stop()
    w._start_daily_pending()
    ws.add_image_paths([b])  # 跑动中又来一张

    w._on_daily_finish_request()  # 用户点「结束会话」
    assert w._daily_chain is False and w._daily_drain is True

    w._on_daily_session_state(
        {"images": [str(a)], "done": [str(a)], "markdown": "A", "regions": [], "warnings": []}
    )
    _finish(w, fake, "A")
    # 兜最后一批：队列里的 b 仍然要识别
    assert len(fake.inputs) == 2 and fake.inputs[1].image_paths == (b,)
    assert w._daily_drain is False  # 只兜一次

    w._on_daily_session_state(
        {
            "images": [str(a), str(b)],
            "done": [str(a), str(b)],
            "markdown": "A\n\nB",
            "regions": [],
            "warnings": [],
        }
    )
    _finish(w, fake, "A\n\nB")
    assert len(fake.inputs) == 2  # 不再自动接着跑
    assert not ws.is_busy()
    w.close()


def test_daily_archive_after_drain_covers_whole_session(monkeypatch, tmp_path: Path):
    w, fake = _window(monkeypatch, tmp_path)
    ws = w.daily_workspace
    ws.set_stream_mode(True)
    a, b = _images(tmp_path, 2)

    ws.add_image_paths([a, b])
    w._daily_debounce.stop()
    w._start_daily_pending()
    w._on_daily_recognize([a, b], True)  # 识别中点「图文归档」
    assert w._daily_archive_wanted is True

    w._on_daily_session_state(
        {
            "images": [str(a), str(b)],
            "done": [str(a), str(b)],
            "markdown": "A\n\nB",
            "regions": [],
            "warnings": [],
        }
    )
    _finish(w, fake, "A\n\nB")

    assert len(fake.inputs) == 2
    archive_run = fake.inputs[-1]
    assert archive_run.archive is True
    assert archive_run.image_paths == ()  # 只归档：不再重复识别
    assert archive_run.session["images"] == [str(a), str(b)]
    assert archive_run.archive_dir is not None
    assert w._daily_archive_wanted is False
    w.close()


def test_daily_cancel_stops_chaining_and_keeps_results(monkeypatch, tmp_path: Path):
    w, fake = _window(monkeypatch, tmp_path)
    ws = w.daily_workspace
    ws.set_stream_mode(True)
    a, b = _images(tmp_path, 2)

    ws.add_image_paths([a])
    w._daily_debounce.stop()
    w._start_daily_pending()
    ws.add_image_paths([b])
    w._on_daily_recognize([a], True)  # 归档意图也要被取消掉
    w._cancel()
    assert fake.cancelled is True
    assert w._daily_chain is False and w._daily_drain is False
    assert w._daily_archive_wanted is False

    fake.running = False
    w._daily.cancelled = True
    w._on_daily_finished_ok("", "已取消", "")
    assert len(fake.inputs) == 1  # 取消后不再续跑
    assert not ws.is_busy()
    w.close()


def test_daily_no_duplicate_dispatch_between_finish_and_chain(monkeypatch, tmp_path: Path):
    """回归：Worker 线程已结束但完成回调还没派发时，新图片不能触发第二轮重复识别。"""
    w, fake = _window(monkeypatch, tmp_path)
    ws = w.daily_workspace
    ws.set_stream_mode(True)
    a, b = _images(tmp_path, 2)

    ws.add_image_paths([a])
    w._daily_debounce.stop()
    w._start_daily_pending()
    assert len(fake.inputs) == 1
    assert w._daily_inflight is True

    # 线程已经跑完（is_running False），但 finished_ok 还在事件队列里没送到
    fake.running = False
    ws.add_image_paths([b])
    w._start_daily_pending()  # 防抖/其它路径也不许重复派发
    assert len(fake.inputs) == 1

    # 完成回调到达：这才续跑，并且只跑一次 b
    w._on_daily_session_state(
        {"images": [str(a)], "done": [str(a)], "markdown": "A", "regions": [], "warnings": []}
    )
    _finish(w, fake, "A")
    assert [tuple(i.image_paths) for i in fake.inputs] == [(a,), (b,)]
    assert w._daily_inflight is True

    w._on_daily_session_state(
        {
            "images": [str(a), str(b)],
            "done": [str(a), str(b)],
            "markdown": "A\n\nB",
            "regions": [],
            "warnings": [],
        }
    )
    _finish(w, fake, "A\n\nB")
    assert [tuple(i.image_paths) for i in fake.inputs] == [(a,), (b,)]  # 没有第三轮
    assert w._daily_inflight is False
    w.close()


def test_daily_single_shot_mode_replaces_result(monkeypatch, tmp_path: Path):
    w, fake = _window(monkeypatch, tmp_path)
    ws = w.daily_workspace
    ws.set_stream_mode(False)
    a, b = _images(tmp_path, 2)

    ws.add_image_paths([a])
    assert fake.inputs[-1].session is None  # 一次性模式：不累加历史
    assert fake.inputs[-1].image_paths == (a,)
    _finish(w, fake, "第一次结果")
    assert ws.result.toPlainText().strip() == "第一次结果"

    ws.add_image_paths([b])  # 覆盖队列并重新识别
    assert fake.inputs[-1].image_paths == (b,)
    assert ws.image_paths() == [b]
    _finish(w, fake, "第二次结果")
    assert ws.result.toPlainText().strip() == "第二次结果"
    assert "已识别 1 张" in ws.lbl_images.text()
    w.close()
