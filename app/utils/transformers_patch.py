"""确保 transformers 5.x 仍提供 MinerU Unimernet 需要的旧 API。"""
from __future__ import annotations

from pathlib import Path


_PATCH = '''

def find_pruneable_heads_and_indices(
    heads: list[int], n_heads: int, head_size: int, already_pruned_heads: set[int]
):
    """Backport for MinerU Unimernet (removed in transformers 5.x)."""
    import torch

    mask = torch.ones(n_heads, head_size)
    heads = set(heads) - already_pruned_heads
    for head in heads:
        head = head - sum(1 if h < head else 0 for h in already_pruned_heads)
        mask[head] = 0
    mask = mask.view(-1).contiguous().eq(1)
    index = torch.arange(len(mask))[mask].long()
    return heads, index
'''


def ensure_transformers_prune_api() -> None:
    try:
        from transformers.pytorch_utils import find_pruneable_heads_and_indices  # noqa: F401

        return
    except Exception:
        pass

    import transformers

    path = Path(transformers.__file__).resolve().parent / "pytorch_utils.py"
    text = path.read_text(encoding="utf-8")
    if "def find_pruneable_heads_and_indices" in text:
        return
    path.write_text(text + _PATCH, encoding="utf-8")
