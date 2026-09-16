"""ResourceRuntime 公共入口。CLI 与 GUI 使用同一 get_runtime()。"""
from app.core.runtime.isolate import IsolateResult, isolate_call
from app.core.runtime.kinds import ResourceBusy, ResourceCancelled, ResourceError, ResourceKind
from app.core.runtime.lease import ResourceBag, ResourceLease
from app.core.runtime.manager import (
    ResourceLimits,
    ResourceRuntime,
    current_job_id,
    get_runtime,
    reset_runtime_for_tests,
)
from app.core.runtime.model import ModelHandle, ModelRuntime, ModelState

__all__ = [
    "IsolateResult",
    "ModelHandle",
    "ModelRuntime",
    "ModelState",
    "ResourceBag",
    "ResourceBusy",
    "ResourceCancelled",
    "ResourceError",
    "ResourceKind",
    "ResourceLease",
    "ResourceLimits",
    "ResourceRuntime",
    "current_job_id",
    "get_runtime",
    "isolate_call",
    "reset_runtime_for_tests",
]
