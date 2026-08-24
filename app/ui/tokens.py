# -*- coding: utf-8 -*-
"""视觉 Token：颜色 / 间距 / 圆角。不在各窗口硬编码 #hex。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    window: str
    surface: str
    surface_alt: str
    surface_hover: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_subtle: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    success: str
    success_bg: str
    warning: str
    warning_bg: str
    danger: str
    danger_bg: str
    info: str
    info_bg: str
    selection: str
    disabled_bg: str
    disabled_text: str


LIGHT = ThemeTokens(
    window="#F4F7FA",
    surface="#FFFFFF",
    surface_alt="#F8FAFC",
    surface_hover="#F1F5F9",
    border="#DCE3EA",
    border_strong="#C7D0DA",
    text="#17212B",
    text_muted="#596675",
    text_subtle="#7B8794",
    accent="#2563EB",
    accent_hover="#1D4ED8",
    accent_pressed="#1E40AF",
    accent_text="#FFFFFF",
    success="#16803A",
    success_bg="#EAF7EE",
    warning="#9A6700",
    warning_bg="#FFF4CE",
    danger="#C42B1C",
    danger_bg="#FDECEC",
    info="#175CD3",
    info_bg="#EEF4FF",
    selection="#E8F0FE",
    disabled_bg="#EEF1F4",
    disabled_text="#9AA4AF",
)

DARK = ThemeTokens(
    window="#111418",
    surface="#191D22",
    surface_alt="#20252B",
    surface_hover="#272D34",
    border="#323840",
    border_strong="#424A54",
    text="#F1F4F7",
    text_muted="#B2BBC5",
    text_subtle="#88939F",
    accent="#5B8DEF",
    accent_hover="#74A0F5",
    accent_pressed="#4778D5",
    accent_text="#FFFFFF",
    success="#58C878",
    success_bg="#173A23",
    warning="#E3B341",
    warning_bg="#413515",
    danger="#FF7166",
    danger_bg="#421F1D",
    info="#77A7FF",
    info_bg="#182C4D",
    selection="#273A5A",
    disabled_bg="#24292F",
    disabled_text="#69737E",
)


class Spacing:
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32


class Radius:
    CONTROL = 7
    CARD = 11
    PILL = 999


class Size:
    CONTROL = 32
    PRIMARY_CONTROL = 38
    TABLE_ROW = 36
