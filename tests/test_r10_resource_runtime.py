"""R10：Resource Runtime。CLI/GUI 同一运行时；cancel 释放；崩溃不杀进程。"""
from __future__ import annotations

import ast
import json
import threading
import time
from pathlib import Path

import pytest

from app.core.domain.job import ConversionRequest
from app.core.pipeline.runner import JobRunner
from app.core.pipeline.stage import CallableStage, StageResult
from app.core.runtime import (
    ResourceBusy,
    ResourceCancelled,
    ResourceKind,
    ResourceLimits,
    get_runtime,
    isolate_call,
    reset_runtime_for_tests,
)
from app.core.__main__ import main as core_main


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.fixture
def runtime():
    rt = reset_runtime_for_tests(
        ResourceLimits(
            gpu_slots=1,
            cpu_slots=2,
            browser_slots=1,
            api_slots=2,
            acquire_timeout_seconds=0.4,
        )
    )
    try:
        yield rt
    finally:
        reset_runtime_for_tests()


def test_cli_and_gui_share_same_runtime(runtime):
    assert get_runtime() is runtime
    assert get_runtime() is get_runtime()


def test_gpu_slots_are_bounded_and_reentrant(runtime):
    first = runtime.acquire(ResourceKind.GPU, job_id="job-a")
    nested = runtime.acquire(ResourceKind.GPU, job_id="job-a")
    assert nested is first
    assert first.refcount == 2
    assert runtime.health()["used"]["gpu"] == 1
    with pytest.raises(ResourceBusy) as exc:
        runtime.acquire(ResourceKind.GPU, job_id="job-b", timeout=0.15)
    assert "gpu" in str(exc.value)
    first.release()
    assert runtime.health()["used"]["gpu"] == 1
    nested.release()
    assert runtime.health()["used"]["gpu"] == 0
    second = runtime.acquire(ResourceKind.GPU, job_id="job-b", timeout=0.2)
    second.release()


def test_release_unblocks_waiter(runtime):
    held = runtime.acquire(ResourceKind.GPU, job_id="holder")
    got: dict[str, object] = {}

    def waiter() -> None:
        got["lease"] = runtime.acquire(ResourceKind.GPU, job_id="waiter", timeout=2.0)

    thread = threading.Thread(target=waiter, name="gpu-waiter")
    thread.start()
    time.sleep(0.05)
    held.release()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    lease = got["lease"]
    assert getattr(lease, "job_id", "") == "waiter"
    lease.release()
    assert runtime.health()["used"]["gpu"] == 0


def test_cancel_during_wait_raises(runtime):
    runtime.acquire(ResourceKind.GPU, job_id="holder")
    cancelled = {"v": False}

    def wait() -> None:
        time.sleep(0.05)
        cancelled["v"] = True

    threading.Thread(target=wait, daemon=True).start()
    with pytest.raises(ResourceCancelled):
        runtime.acquire(
            ResourceKind.GPU,
            job_id="other",
            timeout=1.0,
            cancelled=lambda: cancelled["v"],
        )


def test_end_job_releases_nested_leases_and_job_processes(runtime):
    stopped = {"n": 0}
    runtime.acquire(ResourceKind.GPU, job_id="job-a")
    runtime.acquire(ResourceKind.GPU, job_id="job-a")
    runtime.acquire(ResourceKind.BROWSER, job_id="job-a")
    runtime.register_process(
        424242,
        kind=ResourceKind.BROWSER,
        job_id="job-a",
        survive_shutdown=False,
        stop_fn=lambda: stopped.__setitem__("n", stopped["n"] + 1),
    )
    runtime.register_process(
        434343,
        kind=ResourceKind.DAEMON,
        owner="formula.deepseek_ocr2",
        survive_shutdown=True,
        stop_fn=lambda: stopped.__setitem__("n", stopped["n"] + 10),
    )
    runtime.end_job("job-a")
    health = runtime.health()
    assert health["used"]["gpu"] == 0
    assert health["used"]["browser"] == 0
    assert stopped["n"] == 1
    assert any(p["pid"] == 434343 for p in health["processes"])


def test_shutdown_keeps_daemons_kills_browser(runtime):
    flags = {"browser": 0, "daemon": 0}
    runtime.register_process(
        515151,
        kind=ResourceKind.BROWSER,
        survive_shutdown=False,
        stop_fn=lambda: flags.__setitem__("browser", 1),
    )
    runtime.register_process(
        525252,
        kind=ResourceKind.DAEMON,
        survive_shutdown=True,
        stop_fn=lambda: flags.__setitem__("daemon", 1),
    )
    runtime.models.attach("formula.deepseek_ocr2", pid=525252, survive_gui_exit=True)
    runtime.shutdown(keep_daemons=True)
    assert flags["browser"] == 1
    assert flags["daemon"] == 0
    assert any(p["pid"] == 525252 for p in runtime.health()["processes"])


def test_job_runner_cancel_and_crash_release_gpu(runtime, tmp_path: Path):
    req = ConversionRequest(source_path=tmp_path / "a.pdf", output_dir=tmp_path, workflow="快速自动")
    cancelled = JobRunner().run(
        req,
        [CallableStage("parse", lambda _c: StageResult(name="parse", status="ok"))],
        cancelled=lambda: True,
        context={"resource_kinds": (ResourceKind.GPU, ResourceKind.CPU), "runtime": runtime},
    )
    assert not cancelled.ok
    assert cancelled.job.status == "cancelled"
    assert runtime.health()["used"]["gpu"] == 0
    assert runtime.health()["used"]["cpu"] == 0

    def boom(_ctx):
        raise SystemExit("cuda boom")

    crashed = JobRunner().run(
        req,
        [CallableStage("parse", boom)],
        context={"resource_kinds": (ResourceKind.GPU,), "runtime": runtime},
    )
    assert not crashed.ok
    assert "SystemExit" in crashed.error
    assert runtime.health()["used"]["gpu"] == 0
    nxt = runtime.acquire(ResourceKind.GPU, job_id="after", timeout=0.2)
    nxt.release()


def test_isolate_call_does_not_kill_process():
    boom = isolate_call(lambda: (_ for _ in ()).throw(RuntimeError("provider crashed")))
    assert boom.ok is False
    assert boom.exception_type == "RuntimeError"
    alive = isolate_call(lambda: 7)
    assert alive.ok is True
    assert alive.value == 7


def test_job_scope_sets_current_job_id(runtime):
    from app.core.runtime import current_job_id

    assert current_job_id() is None
    with runtime.job_scope("scope-1", kinds=(ResourceKind.CPU,)):
        assert current_job_id() == "scope-1"
        assert runtime.health()["used"]["cpu"] == 1
    assert current_job_id() is None
    assert runtime.health()["used"]["cpu"] == 0


def test_cli_resources_json(capsys, runtime):
    rc = core_main(["resources"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0"
    assert payload["used"]["gpu"] == 0
    assert "limits" in payload
    assert "models" in payload


def test_runtime_boundary_is_closed():
    forbidden = "app.core.runtime"
    for rel in (
        "app/core/domain/document.py",
        "app/core/domain/quality.py",
        "app/core/qa/engine.py",
        "app/core/qa/gold.py",
        "app/core/qa/checks.py",
        "app/core/routing/router.py",
        "app/core/providers/builtins.py",
        "app/core/benchmark/runner.py",
    ):
        imported = _imported(Path(rel))
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported), rel

    runner_imports = _imported(Path("app/core/pipeline/runner.py"))
    assert any(name == forbidden or name.startswith(forbidden + ".") for name in runner_imports)
    conversion = Path("app/core/service/conversion.py").read_text(encoding="utf-8")
    vision = Path("app/core/service/vision.py").read_text(encoding="utf-8")
    main_window = Path("app/main_window.py").read_text(encoding="utf-8")
    assert "resource_kinds" in conversion
    assert "job_scope" in vision
    assert "keep_daemons=True" in main_window
    assert "get_runtime" in main_window
    document = Path("app/core/domain/document.py").read_text(encoding="utf-8")
    assert "vram" not in document
    assert "ResourceLease" not in document
