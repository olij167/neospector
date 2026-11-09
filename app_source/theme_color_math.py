"""Pure colour helpers for OmN-e Retrospector themes.

No Tk imports live here so release validation and CI can run headlessly.
"""
from __future__ import annotations

import re

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def normalize_hex(value: str) -> str:
    match = _HEX.fullmatch(str(value).strip())
    if not match:
        raise ValueError(f"Expected six-digit hexadecimal colour, got {value!r}")
    return "#" + match.group(1).upper()


def _srgb_channel_to_linear(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(value: str) -> float:
    colour = normalize_hex(value)
    r = _srgb_channel_to_linear(int(colour[1:3], 16))
    g = _srgb_channel_to_linear(int(colour[3:5], 16))
    b = _srgb_channel_to_linear(int(colour[5:7], 16))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    a = relative_luminance(foreground)
    b = relative_luminance(background)
    lighter, darker = (a, b) if a >= b else (b, a)
    return (lighter + 0.05) / (darker + 0.05)


def best_text_color(background: str, *candidates: str) -> str:
    if not candidates:
        candidates = ("#000000", "#FFFFFF")
    scored = [(contrast_ratio(candidate, background), normalize_hex(candidate)) for candidate in candidates]
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][1]


def meets_contrast(foreground: str, background: str, minimum: float = 4.5) -> bool:
    return contrast_ratio(foreground, background) + 1e-9 >= float(minimum)
