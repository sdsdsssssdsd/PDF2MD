"""R15 release-check + R16 1.0 public protocol / CLI / plugin SDK。"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.__main__ import main as core_main
from app.core.protocol import PROTOCOL_VERSION, assert_compatible, compatible, protocol_manifest
from app.core.providers.sdk import make_experimental_descriptor
from app.core.providers.registry import ProviderRegistry
from app.core.release import collect_release_check


def test_protocol_is_1x_additive():
    man = protocol_manifest()
    assert man["protocol_version"] == PROTOCOL_VERSION == "1.0"
    assert man["compatibility"]["1.x"] == "additive changes only"
    assert man["service"] == "not_in_1.0"
    for name in ("convert", "inspect", "providers", "doctor", "benchmark"):
        assert name in man["commands"]
    assert compatible("document_ir", "1.0") is True
    assert compatible("qa", "1.2") is True
    assert compatible("run", "2.0") is False
    assert_compatible("provider", "1.0")


def test_release_check_extras_and_no_qsettings():
    report = collect_release_check()
    assert report["extras_ok"] is True
    assert report["qsettings_in_core"] is False
    assert report["installer"] == "portable-script"
    assert report["lockfile"]["pdf2md.lock.json"] is True
    assert report["sbom"]["present"] is True
    assert report["protocol"]["protocol_version"] == "1.0"


def test_cli_convert_inspect_protocol(tmp_path: Path, capsys):
    md = tmp_path / "n.md"
    md.write_text("# t\n", encoding="utf-8")
    assert core_main(["inspect", "--json", str(md)]) == 0
    inspect_payload = json.loads(capsys.readouterr().out)
    assert "plan" in inspect_payload
    assert core_main(["convert", "--json", str(md)]) == 0
    convert_payload = json.loads(capsys.readouterr().out)
    assert convert_payload["executed"] is False
    assert convert_payload["plan"]["parser"] == "docling"
    assert core_main(["protocol"]) == 0
    proto = json.loads(capsys.readouterr().out)
    assert proto["protocol_version"] == "1.0"
    assert core_main(["release-check"]) == 0
    rel = json.loads(capsys.readouterr().out)
    assert rel["extras_ok"] is True
    assert core_main(["smoke"]) == 0
    smoke = json.loads(capsys.readouterr().out)
    assert smoke["ok"] is True


def test_plugin_sdk_registers_disabled():
    desc = make_experimental_descriptor(provider_id="parser.sample_plugin")
    registry = ProviderRegistry()
    registry.register(desc)
    status = registry.status("parser.sample_plugin")
    assert status is not None
    assert status.enabled is False
    assert status.descriptor.experimental is True
    assert status.descriptor.source == "plugin"
