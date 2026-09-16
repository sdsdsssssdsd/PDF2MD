"""资源种类与错误。不含具体 Provider / 模型。"""
from __future__ import annotations


class ResourceKind:
    GPU = "gpu"
    CPU = "cpu"
    BROWSER = "browser"
    API = "api"
    DAEMON = "daemon"

    ALL = (GPU, CPU, BROWSER, API, DAEMON)


class ResourceError(Exception):
    """ResourceRuntime 可恢复错误。不杀进程。"""


class ResourceBusy(ResourceError):
    """槽位占满且等待超时。"""


class ResourceCancelled(ResourceError):
    """等待槽位时任务已取消。"""
