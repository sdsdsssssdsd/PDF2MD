"""严格按页码连续分批（默认 10 页）。"""
from __future__ import annotations

from app.vision_transcribe.models import BatchInfo, BatchStatus


def plan_batches(page_count: int, batch_size: int = 10) -> list[BatchInfo]:
    if page_count < 1:
        return []
    size = max(1, int(batch_size))
    batches: list[BatchInfo] = []
    bid = 1
    start = 1
    while start <= page_count:
        end = min(start + size - 1, page_count)
        batches.append(
            BatchInfo(
                id=bid,
                start_page=start,
                end_page=end,
                status=BatchStatus.PENDING.value,
            )
        )
        bid += 1
        start = end + 1
    return batches


def split_batch_for_retry(batch: BatchInfo) -> list[BatchInfo]:
    """10→5+5→单页 降级（异常恢复，不改变正常规划）。"""
    span = batch.end_page - batch.start_page + 1
    if span <= 1:
        return [batch]
    if span > 5:
        mid = batch.start_page + (span // 2) - 1
        return [
            BatchInfo(
                id=batch.id,
                start_page=batch.start_page,
                end_page=mid,
                status=BatchStatus.PENDING.value,
            ),
            BatchInfo(
                id=batch.id,
                start_page=mid + 1,
                end_page=batch.end_page,
                status=BatchStatus.PENDING.value,
            ),
        ]
    # 5 页以内 → 逐页
    return [
        BatchInfo(
            id=batch.id,
            start_page=p,
            end_page=p,
            status=BatchStatus.PENDING.value,
        )
        for p in range(batch.start_page, batch.end_page + 1)
    ]
