"""
Portrait monitor layout profile for D&D Beside (1080×1920 vertical displays).

Kept separate from the default landscape layout — toggled via ui_settings.json
``layout_profile`` or the hamburger menu / launch_portrait_monitor.py helper.

Landscape (default): Stats uses three side-by-side columns (Abilities | Defense | Skills).
Portrait monitor:    Stats stacks those panels as full-width horizontal bands.
"""
from __future__ import annotations

LAYOUT_PROFILE_LANDSCAPE = "landscape"
LAYOUT_PROFILE_PORTRAIT = "portrait_monitor"

LAYOUT_PROFILES = (LAYOUT_PROFILE_LANDSCAPE, LAYOUT_PROFILE_PORTRAIT)

PORTRAIT_TARGET_WIDTH = 1080
PORTRAIT_TARGET_HEIGHT = 1920
PORTRAIT_UI_REFERENCE_WIDTH = 1080
PORTRAIT_UI_REFERENCE_HEIGHT = 1920

# Approximate band heights on the Stats page (pixels, before UI scale).
PORTRAIT_ABILITIES_BAND_HEIGHT = 420
PORTRAIT_DEFENSE_BAND_HEIGHT = 340
PORTRAIT_FEATURES_BAND_HEIGHT = 200
PORTRAIT_SKILLS_MIN_HEIGHT = 480


def normalize_layout_profile(value) -> str:
    profile = str(value or LAYOUT_PROFILE_LANDSCAPE).strip().lower()
    if profile in (LAYOUT_PROFILE_PORTRAIT, "portrait", "vertical", "1080x1920"):
        return LAYOUT_PROFILE_PORTRAIT
    return LAYOUT_PROFILE_LANDSCAPE


def is_portrait_profile(profile) -> bool:
    return normalize_layout_profile(profile) == LAYOUT_PROFILE_PORTRAIT


def default_ui_settings():
    return {"display_scale": "Auto", "performance_mode": "ultra_smooth"}


def merge_ui_settings(raw: dict | None) -> dict:
    merged = default_ui_settings()
    if isinstance(raw, dict):
        merged.update({k: v for k, v in raw.items() if k != "layout_profile"})
    preset = str(merged.get("display_scale", "Auto") or "Auto")
    if preset not in (
        "Auto", "100%", "90%", "85%", "80%", "75%", "70%",
    ):
        merged["display_scale"] = "Auto"
    perf = str(merged.get("performance_mode", "ultra_smooth") or "ultra_smooth").strip().lower()
    if perf not in ("ultra_smooth", "full_feature"):
        perf = "ultra_smooth"
    merged["performance_mode"] = perf
    return merged


def portrait_window_geometry(screen_w: int, screen_h: int) -> str:
    """Centered 1080×1920 window, clamped to the current monitor."""
    sw = max(1, int(screen_w or PORTRAIT_TARGET_WIDTH))
    sh = max(1, int(screen_h or PORTRAIT_TARGET_HEIGHT))
    w = min(PORTRAIT_TARGET_WIDTH, sw)
    h = min(PORTRAIT_TARGET_HEIGHT, sh)
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    return f"{w}x{h}+{x}+{y}"