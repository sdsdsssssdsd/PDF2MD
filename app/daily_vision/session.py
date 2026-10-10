"""日常识图「陆续加图」会话：跨多轮识图累加同一篇结果。

为什么需要：
QQ / 微信这类来源只能一张一张复制，用户不可能一次选好整批图片。会话把「每轮识别」
的产物按图片顺序拼接成一篇文章——marker 与 source_image 都按已识别张数平移，
所以第二轮的第 1 张图在正文里是 i0007（而不是又回到 i0001），裁图也不会取错源图。

状态是纯数据（payload），可跨线程/落盘传递：MainWindow 只拿 payload，不碰算法层对象。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.daily_vision.batching import merge_batch
from app.daily_vision.models import DailyVisionResult, FigureRegion

PAYLOAD_VERSION = 1


def _normalize(paths: Iterable[Path | str]) -> list[Path]:
    return [Path(p) for p in paths]


@dataclass
class DailyVisionSession:
    """一次「陆续加图」会话：图片队列 + 累积结果。"""

    images: list[Path] = field(default_factory=list)
    done_images: list[Path] = field(default_factory=list)
    result: DailyVisionResult = field(default_factory=DailyVisionResult)

    # —— 队列 ——
    def add_images(self, paths: Iterable[Path | str]) -> list[Path]:
        """追加图片（按绝对路径去重，保持加入顺序）；返回本次真正新增的图片。"""
        existing = {_key(p) for p in self.images}
        added: list[Path] = []
        for path in _normalize(paths):
            key = _key(path)
            if key in existing:
                continue
            existing.add(key)
            self.images.append(path)
            added.append(path)
        return added

    def pending(self) -> list[Path]:
        """还没识别的图片（保持加入顺序）。"""
        done = {_key(p) for p in self.done_images}
        return [p for p in self.images if _key(p) not in done]

    def is_drained(self) -> bool:
        return not self.pending()

    @property
    def done(self) -> int:
        """已识别张数——也是下一轮的 marker / source_image 偏移量。"""
        return len(self.done_images)

    def counts(self) -> tuple[int, int]:
        return self.done, len(self.images)

    # —— 合并 ——
    def merge_run(self, run_images: Iterable[Path | str], run_result: DailyVisionResult) -> None:
        """把一轮识别结果按偏移并入会话累积结果，并把这批图片标记为已识别。"""
        images = [Path(p) for p in run_images]
        offset = self.done
        merge_batch(self.result, run_result, offset=offset)
        self.result.warnings.extend(run_result.warnings)
        self.done_images.extend(images)

    # —— 序列化（跨线程用） ——
    def to_payload(self) -> dict[str, Any]:
        return {
            "version": PAYLOAD_VERSION,
            "images": [str(p) for p in self.images],
            "done": [str(p) for p in self.done_images],
            "markdown": self.result.markdown,
            "regions": [
                {
                    "marker": r.marker,
                    "source_image": int(r.source_image),
                    "type": r.region_type,
                    "bbox": list(r.bbox),
                }
                for r in self.result.regions
            ],
            "warnings": list(self.result.warnings),
        }

    @classmethod
    def from_payload(cls, payload: Any) -> DailyVisionSession:
        if isinstance(payload, DailyVisionSession):
            return payload
        session = cls()
        if not isinstance(payload, dict):
            return session
        session.images = [Path(p) for p in payload.get("images") or []]
        session.done_images = [Path(p) for p in payload.get("done") or []]
        session.result = DailyVisionResult(
            markdown=str(payload.get("markdown") or ""),
            regions=[
                FigureRegion(
                    marker=str(r.get("marker") or ""),
                    source_image=int(r.get("source_image") or 1),
                    region_type=str(r.get("type") or "figure"),
                    bbox=[float(x) for x in (r.get("bbox") or [])[:4]],
                )
                for r in (payload.get("regions") or [])
                if isinstance(r, dict)
            ],
            warnings=[str(w) for w in payload.get("warnings") or []],
        )
        return session


def _key(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.resolve())
    except OSError:
        return str(p)
