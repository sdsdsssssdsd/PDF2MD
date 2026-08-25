"""`.vision/manifest.json` 持久化与断点恢复。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.vision_transcribe.models import BatchInfo, BatchStatus, PageInfo, PipelineState
from app.vision_transcribe.prompts import PROMPT_VERSION


MANIFEST_VERSION = 2


@dataclass
class VisionManifest:
    version: int = MANIFEST_VERSION
    pdf: str = ""
    page_count: int = 0
    render_scale: float = 3.0
    batch_size: int = 10
    workflow: str = "vision_fidelity"
    prompt_version: str = PROMPT_VERSION
    state: str = PipelineState.INIT.value
    pages: list[dict[str, Any]] = field(default_factory=list)
    batches: list[dict[str, Any]] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)
    browser_mode: str = "clipboard"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisionManifest:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)

    def set_pages(self, pages: list[PageInfo]) -> None:
        self.pages = [{"page": p.page, "file": p.file} for p in pages]
        self.page_count = len(pages)

    def set_batches(self, batches: list[BatchInfo]) -> None:
        self.batches = [
            {
                "id": b.id,
                "start_page": b.start_page,
                "end_page": b.end_page,
                "status": b.status,
                "error": b.error,
            }
            for b in batches
        ]

    def get_batches(self) -> list[BatchInfo]:
        out: list[BatchInfo] = []
        for b in self.batches:
            out.append(
                BatchInfo(
                    id=int(b["id"]),
                    start_page=int(b["start_page"]),
                    end_page=int(b["end_page"]),
                    status=str(b.get("status", BatchStatus.PENDING.value)),
                    error=str(b.get("error", "")),
                )
            )
        return out

    def update_batch_status(self, batch_id: int, status: str, error: str = "") -> None:
        for b in self.batches:
            if int(b["id"]) == batch_id:
                b["status"] = status
                if error:
                    b["error"] = error
                elif status == BatchStatus.ACCEPTED.value:
                    b["error"] = ""
                return

    def next_pending_batch(self) -> BatchInfo | None:
        """未成功的批次都算待处理（含卡在 waiting/uploading 的中断态）。"""
        priority = (
            BatchStatus.RECEIVED.value,
            BatchStatus.VALIDATING.value,
            BatchStatus.NEEDS_RETRY.value,
            BatchStatus.WAITING_RESPONSE.value,
            BatchStatus.UPLOADING.value,
            BatchStatus.PENDING.value,
            BatchStatus.FAILED.value,
        )
        batches = self.get_batches()
        for status in priority:
            for b in batches:
                if b.status == status:
                    return b
        return None

    def reset_incomplete_batches(self) -> int:
        """将未 accepted 的批次恢复为 pending，便于同一 PDF 断点续跑。"""
        n = 0
        for b in self.batches:
            if str(b.get("status")) != BatchStatus.ACCEPTED.value:
                b["status"] = BatchStatus.PENDING.value
                b["error"] = ""
                n += 1
        return n

    def reset_all_batches_for_rerun(self) -> int:
        """将全部批次恢复为 pending，用于同一输出目录完整重跑视觉转录。"""
        for b in self.batches:
            b["status"] = BatchStatus.PENDING.value
            b["error"] = ""
        self.state = PipelineState.READY_TO_TRANSCRIBE.value
        return len(self.batches)

    def all_batches_accepted(self) -> bool:
        batches = self.get_batches()
        return bool(batches) and all(b.status == BatchStatus.ACCEPTED.value for b in batches)

    def record_batch_acceptance(
        self,
        batch_id: int,
        raw_md: str,
        output_dir: Path,
        *,
        extract_stats: dict | None = None,
    ) -> None:
        """manifest v2：记录批次 accepted 元数据（逐页 chars / 来源 / 尝试次数）。"""
        from app.vision_transcribe.capture.page_split import split_pages

        stats = dict(extract_stats or {})
        attempts_dir = batch_dir(output_dir, batch_id) / "attempts"
        attempt_n = 0
        if attempts_dir.is_dir():
            attempt_n = len(list(attempts_dir.glob("attempt_*")))

        stable = bool(stats.get("copy_consensus_stable"))
        source = str(stats.get("source") or stats.get("copy_consensus_label") or "")
        confidence = "high" if stable else "medium"

        for b in self.batches:
            if int(b["id"]) != batch_id:
                continue
            start_p = int(b["start_page"])
            end_p = int(b["end_page"])
            slices = split_pages(raw_md)
            pages_meta: dict[str, dict] = {}
            for p in range(start_p, end_p + 1):
                sl = slices.get(p)
                if sl is None:
                    pages_meta[str(p)] = {
                        "status": "missing",
                        "chars": 0,
                        "source": source,
                        "confidence": "low",
                    }
                else:
                    pages_meta[str(p)] = {
                        "status": "accepted",
                        "chars": sl.chars,
                        "has_end": sl.has_end,
                        "source": source,
                        "confidence": confidence if sl.chars >= 200 else "low",
                    }
            b["attempt_count"] = attempt_n
            b["accepted_attempt"] = attempt_n if attempt_n else 1
            b["failure_class"] = str(stats.get("capture_failure_class") or "")
            b["confidence"] = confidence
            b["extract_source"] = source
            b["pages"] = pages_meta
            break
        self.version = max(int(self.version), MANIFEST_VERSION)


def vision_dir(output_dir: Path) -> Path:
    return output_dir / ".vision"


def batches_root(output_dir: Path) -> Path:
    return vision_dir(output_dir) / "batches"


def batch_dir(output_dir: Path, batch_id: int) -> Path:
    return batches_root(output_dir) / f"batch_{batch_id:04d}"


def manifest_path(output_dir: Path) -> Path:
    return vision_dir(output_dir) / "manifest.json"


def load_manifest(output_dir: Path) -> VisionManifest | None:
    path = manifest_path(output_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return VisionManifest.from_dict(data)


def should_force_vision_rerun(
    output_dir: Path | None,
    *,
    checkbox: bool = False,
    task_was_done: bool = False,
) -> bool:
    """点「转换」时是否整篇重跑浏览器。

    已完成（任务 Done 或目录内批次已全部 accepted）默认 True；
    未完成则仅当勾选「强制重跑」才丢掉已接受批次。
    """
    if checkbox or task_was_done:
        return True
    if output_dir is None:
        return False
    m = load_manifest(output_dir)
    return bool(m and m.all_batches_accepted())


def save_manifest(output_dir: Path, manifest: VisionManifest) -> Path:
    path = manifest_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
