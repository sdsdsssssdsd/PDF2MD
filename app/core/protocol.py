"""1.0 公共协议：schema 版本与兼容策略。不提前做 REST 服务。"""
from __future__ import annotations

from typing import Any

PROTOCOL_VERSION = "1.0"
PROTOCOL_FAMILY = "1.x"

SCHEMAS = {
    "document_ir": "1.0",
    "qa": "1.0",
    "run": "1.0",
    "provider": "1.0",
}

COMPATIBILITY_POLICY = {
    "1.x": "additive changes only",
    "2.0": "breaking schema changes",
}

PUBLIC_COMMANDS = (
    "convert",
    "inspect",
    "providers",
    "doctor",
    "benchmark",
)


def protocol_manifest() -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "family": PROTOCOL_FAMILY,
        "schemas": dict(SCHEMAS),
        "compatibility": dict(COMPATIBILITY_POLICY),
        "commands": list(PUBLIC_COMMANDS),
        "service": "not_in_1.0",
    }


def compatible(schema: str, version: str) -> bool:
    expected = SCHEMAS.get(schema)
    if not expected:
        return False
    got = str(version or "").strip() or expected
    return got.split(".", 1)[0] == expected.split(".", 1)[0]


def assert_compatible(schema: str, version: str) -> None:
    if not compatible(schema, version):
        raise ValueError(f"incompatible {schema} schema {version!r}; 1.x additive only")
