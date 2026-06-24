"""Tinted monster-face icon for statblock image buttons (no border/background)."""

from __future__ import annotations

import os

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    Image = None
    HAS_PIL = False

_ICON_CACHE: dict[tuple, object] = {}
DEFAULT_ICON_FILENAME = "monster face icon.jpg"


def _parse_hex_color(color: str) -> tuple[int, int, int]:
    value = str(color or "#FF857A").strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except Exception:
        return 255, 133, 122


def load_monster_image_icon(
    assets_dir: str,
    *,
    color: str = "#FF857A",
    size: int = 26,
    filename: str = DEFAULT_ICON_FILENAME,
):
    """Load the monster-face JPG, drop the light background, tint to the statblock accent."""
    if not HAS_PIL or Image is None:
        return None
    import customtkinter as ctk

    tint = _parse_hex_color(color)
    cache_key = (assets_dir, filename, size, tint)
    cached = _ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached

    path = os.path.join(assets_dir, filename)
    if not os.path.isfile(path):
        return None

    with Image.open(path) as source:
        img = source.convert("RGBA")
        width, height = img.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((size, size), Image.Resampling.LANCZOS)

    pixels = img.load()
    tr, tg, tb = tint
    for y in range(size):
        for x in range(size):
            r, g, b, _a = pixels[x, y]
            lum = (int(r) + int(g) + int(b)) / 3.0
            if lum >= 220:
                pixels[x, y] = (0, 0, 0, 0)
            else:
                ink = max(0.0, min(1.0, (220 - lum) / 220.0))
                alpha = int(max(40, min(255, ink * 255)))
                pixels[x, y] = (tr, tg, tb, alpha)

    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    _ICON_CACHE[cache_key] = ctk_img
    return ctk_img