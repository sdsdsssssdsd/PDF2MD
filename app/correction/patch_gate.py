"""Patch 安全门（Phase C 核心）。"""
from __future__ import annotations

import re

from pathlib import Path

from app.format_repair.integrity import integrity_ok
from app.correction.models import CorrectionPatch

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_OPERATOR_CHARS = frozenset("<>≤≥=≠∈∉+-")
_EQ_REF_IN_PATCH = re.compile(r"(?:公式|式|Eq\.?)\s*\(\d+\)", re.I)


def _numbers(text: str) -> list[str]:
    return _NUMBER_RE.findall(text or "")


def _operators(text: str) -> set[str]:
    return {ch for ch in (text or "") if ch in _OPERATOR_CHARS}


def validate_patch(before: str, after: str, *, issue_kind: str = "") -> tuple[bool, str]:
    if not before or before == after:
        return False, "noop"
    if _numbers(before) != _numbers(after):
        return False, "number_mismatch"
    if _EQ_REF_IN_PATCH.search(before) or _EQ_REF_IN_PATCH.search(after):
        if before != after:
            return False, "equation_reference_protected"
    if _operators(before) != _operators(after):
        return False, "operator_mismatch"
    if not integrity_ok(before, after):
        return False, "integrity_fail"
    return True, "accepted"


def apply_patch_once(text: str, patch: CorrectionPatch) -> tuple[str, CorrectionPatch]:
    if patch.before not in text:
        rejected = CorrectionPatch(
            issue_id=patch.issue_id,
            before=patch.before,
            after=patch.after,
            source=patch.source,
            confidence=patch.confidence,
            gate="rejected",
            reason="stale_patch",
        )
        return text, rejected
    ok, reason = validate_patch(patch.before, patch.after)
    if not ok:
        rejected = CorrectionPatch(
            issue_id=patch.issue_id,
            before=patch.before,
            after=patch.after,
            source=patch.source,
            confidence=patch.confidence,
            gate="rejected",
            reason=reason,
        )
        return text, rejected
    new_text = text.replace(patch.before, patch.after, 1)
    if not integrity_ok(text, new_text):
        rejected = CorrectionPatch(
            issue_id=patch.issue_id,
            before=patch.before,
            after=patch.after,
            source=patch.source,
            confidence=patch.confidence,
            gate="rejected",
            reason="document_integrity_fail",
        )
        return text, rejected
    applied = CorrectionPatch(
        issue_id=patch.issue_id,
        before=patch.before,
        after=patch.after,
        source=patch.source,
        confidence=patch.confidence,
        gate="accepted",
        reason=patch.reason or "accepted",
    )
    return new_text, applied


def apply_patches(text: str, patches: list[CorrectionPatch]) -> tuple[str, list[CorrectionPatch], list[CorrectionPatch]]:
    applied: list[CorrectionPatch] = []
    rejected: list[CorrectionPatch] = []
    out = text
    for patch in patches:
        out, result = apply_patch_once(out, patch)
        if result.gate == "accepted":
            applied.append(result)
        else:
            rejected.append(result)
    return out, applied, rejected


def patch_needs_vision(before: str, after: str, *, gate_reason: str) -> bool:
    if gate_reason in {"number_mismatch", "operator_mismatch"}:
        return True
    if _numbers(before) != _numbers(after):
        return True
    if _operators(before) != _operators(after):
        return True
    return False


def try_apply_with_vision(
    text: str,
    patch: CorrectionPatch,
    *,
    image_path: Path,
    left_context: str = "",
    right_context: str = "",
    vision_model: str | None = None,
) -> tuple[str, CorrectionPatch]:
    """Gate 拒绝后，用源图 Vision 决定是否可应用 after。"""
    from app.correction.vision_verifier import verify_and_resolve

    ok, reason = validate_patch(patch.before, patch.after)
    if ok:
        return apply_patch_once(text, patch)

    if not patch_needs_vision(patch.before, patch.after, gate_reason=reason):
        rejected = CorrectionPatch(
            issue_id=patch.issue_id,
            before=patch.before,
            after=patch.after,
            source=patch.source,
            confidence=patch.confidence,
            gate="rejected",
            reason=reason,
        )
        return text, rejected

    choice = verify_and_resolve(
        image_path=Path(image_path),
        before=patch.before,
        after=patch.after,
        left_context=left_context,
        right_context=right_context,
        model=vision_model,
    )
    if choice != "after":
        return text, CorrectionPatch(
            issue_id=patch.issue_id,
            before=patch.before,
            after=patch.after,
            source=patch.source,
            confidence=patch.confidence,
            gate="rejected",
            reason=f"vision_{choice}",
        )
    return apply_patch_once(
        text,
        CorrectionPatch(
            issue_id=patch.issue_id,
            before=patch.before,
            after=patch.after,
            source="vision_verify",
            confidence=patch.confidence,
            reason="vision_verified",
        ),
    )
