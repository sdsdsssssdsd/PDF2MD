"""python -m app doctor|providers|benchmark|resources|inspect 不启动 Qt。

无子命令时走 GUI。
"""
from __future__ import annotations

import sys

CORE_COMMANDS = frozenset(
    {
        "doctor",
        "providers",
        "benchmark",
        "resources",
        "inspect",
        "convert",
        "protocol",
        "release-check",
        "lock",
        "sbom",
        "smoke",
    }
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in CORE_COMMANDS:
        from app.core.__main__ import main as core_main

        return core_main(argv)
    from app.main import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
