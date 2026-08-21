"""保守子图检测：证据不足则不拆。"""
from __future__ import annotations

from dataclasses import dataclass

from app.assets.caption_matcher import extract_subfigure_labels, normalize_subfigure_index
from app.assets.models import FigureAsset, SubfigureAsset


@dataclass
class SubfigurePlan:
    """通过验证后的裁切计划（相对主图 0..1 bbox）。"""

    label: str
    index: int
    bbox: tuple[float, float, float, float]
    confidence: float


def detect_subfigures(
    figure: FigureAsset,
    *,
    enable_split: bool = True,
    require_all: bool = True,
    min_confidence: float = 0.85,
    vision_result: dict | None = None,
) -> tuple[list[SubfigurePlan], str]:
    """
    返回 (plans, status)。

    V1：无 Vision 结构化结果时绝不均分硬切；caption 与 vision 不一致则 uncertain。
    """
    if not enable_split:
        return [], "skipped"

    expected = extract_subfigure_labels(figure.caption or "")
    if len(expected) < 2:
        return [], "none"

    vision_labels: list[str] = []
    vision_boxes: dict[str, tuple[float, float, float, float]] = {}
    vision_conf: dict[str, float] = {}
    if vision_result and vision_result.get("has_subfigures"):
        for item in vision_result.get("subfigures") or []:
            lab = str(item.get("label", "")).strip().lower()
            bbox = item.get("bbox")
            conf = float(item.get("confidence", 0.0))
            if not lab or not bbox or len(bbox) != 4:
                continue
            vision_labels.append(lab)
            vision_boxes[lab] = (
                float(bbox[0]),
                float(bbox[1]),
                float(bbox[2]),
                float(bbox[3]),
            )
            vision_conf[lab] = conf

    if not vision_labels:
        return [], "skipped"

    exp_set = {x.lower() for x in expected}
    vis_set = set(vision_labels)

    if require_all and exp_set != vis_set:
        return [], "uncertain"

    if not require_all:
        common = exp_set & vis_set
        if len(common) < 2:
            return [], "uncertain"
        labels = [x.lower() for x in expected if x.lower() in common]
    else:
        labels = [x.lower() for x in expected]

    plans: list[SubfigurePlan] = []
    for lab in labels:
        conf = vision_conf.get(lab, 0.0)
        if conf < min_confidence:
            return [], "uncertain"
        idx = normalize_subfigure_index(lab)
        if idx is None:
            return [], "uncertain"
        box = vision_boxes.get(lab)
        if not box:
            return [], "uncertain"
        x1, y1, x2, y2 = box
        if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
            return [], "uncertain"
        plans.append(SubfigurePlan(label=lab, index=idx, bbox=box, confidence=conf))

    plans.sort(key=lambda p: p.index)
    for i, p in enumerate(plans, start=1):
        p.index = i
    return plans, "extracted"


def plans_to_assets(
    plans: list[SubfigurePlan],
    *,
    parent_index: int,
    pdf_stem: str,
    ext: str,
) -> list[SubfigureAsset]:
    out: list[SubfigureAsset] = []
    for p in plans:
        name = f"image_{parent_index}-{p.index}_{pdf_stem}{ext}"
        out.append(
            SubfigureAsset(
                index=p.index,
                original_label=p.label,
                file=name,
                bbox=list(p.bbox),
                confidence=p.confidence,
            )
        )
    return out
