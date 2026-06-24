"""Grey transparent health-widget icons for rest and nonlethal heal buttons."""

from __future__ import annotations

import os

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    Image = None
    ImageDraw = None
    HAS_PIL = False

_ICON_CACHE: dict[tuple, object] = {}


def load_grey_health_icon(
    assets_dir: str,
    filename: str,
    *,
    size: int = 32,
    grey: tuple[int, int, int] = (156, 156, 156),
):
    """Load a JPG/PNG icon, drop the light background, tint to grey, return CTkImage."""
    if not HAS_PIL or Image is None:
        return None
    import customtkinter as ctk

    cache_key = (assets_dir, filename, size, grey)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

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
    grey_r, grey_g, grey_b = grey
    for y in range(size):
        for x in range(size):
            r, g, b, a = pixels[x, y]
            lum = (int(r) + int(g) + int(b)) / 3.0
            if lum >= 228:
                pixels[x, y] = (0, 0, 0, 0)
            else:
                ink = max(0.0, min(1.0, (228 - lum) / 228.0))
                alpha = int(max(35, min(255, ink * 255)))
                pixels[x, y] = (grey_r, grey_g, grey_b, alpha)

    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    _ICON_CACHE[cache_key] = ctk_img
    return ctk_img


def make_grey_book_icon(
    *,
    size: int = 32,
    grey: tuple[int, int, int] = (156, 156, 156),
):
    """Draw a simple grey book icon with transparent background; return CTkImage."""
    if not HAS_PIL or Image is None or ImageDraw is None:
        return None
    import customtkinter as ctk

    cache_key = ("__book_icon__", size, grey)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(2, size // 6)
    book_left = margin
    book_right = size - margin
    book_top = margin + 1
    book_bottom = size - margin - 1
    grey_r, grey_g, grey_b = grey
    fill = (grey_r, grey_g, grey_b, 215)
    outline = (grey_r, grey_g, grey_b, 255)
    draw.rectangle(
        [book_left, book_top, book_right, book_bottom],
        fill=fill,
        outline=outline,
        width=1,
    )
    spine_x = book_left + max(3, (book_right - book_left) // 4)
    draw.line([spine_x, book_top + 1, spine_x, book_bottom - 1], fill=outline, width=2)
    page_y = book_top + max(4, size // 5)
    while page_y < book_bottom - max(3, size // 7):
        draw.line(
            [spine_x + 3, page_y, book_right - 4, page_y],
            fill=(grey_r, grey_g, grey_b, 130),
            width=1,
        )
        page_y += max(3, size // 7)

    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    _ICON_CACHE[cache_key] = ctk_img
    return ctk_img