"""Provider 调用隔离：崩溃变成失败结果，不杀 GUI / CLI 进程。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class IsolateResult:
    ok: bool
    value: Any = None
    error: str = ""
    exception_type: str = ""


def isolate_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> IsolateResult:
    """执行 Provider / Stage。KeyboardInterrupt 仍向上走；其余 BaseException 收口。"""
    try:
        return IsolateResult(ok=True, value=fn(*args, **kwargs))
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        return IsolateResult(
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            exception_type=type(exc).__name__,
        )
