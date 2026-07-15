"""
Persist main-window size, position, and maximized state between sessions.

Stored separately from ui_settings.json (display scale only) — layout profile
is never written here.
"""
from __future__ import annotations

import json
import os
import re

WINDOW_STATE_FILENAME = "window_state.json"

_GEOMETRY_RE = re.compile(
    r"^(\d+)x(\d+)(?:\+(-?\d+)\+(-?\d+))?$",
)


def window_state_path(script_dir: str) -> str:
    return os.path.join(script_dir, WINDOW_STATE_FILENAME)


def load_window_state(script_dir: str) -> dict:
    path = window_state_path(script_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {}
        geom = str(data.get("geometry", "") or "").strip()
        if not _GEOMETRY_RE.match(geom):
            return {}
        wm_state = str(data.get("wm_state", "normal") or "normal").strip().lower()
        if wm_state not in ("normal", "zoomed", "iconic"):
            wm_state = "normal"
        return {"geometry": geom, "wm_state": wm_state}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def save_window_state(script_dir: str, *, geometry: str, wm_state: str) -> bool:
    geom = str(geometry or "").strip()
    if not _GEOMETRY_RE.match(geom):
        return False
    state = str(wm_state or "normal").strip().lower()
    if state not in ("normal", "zoomed", "iconic"):
        state = "normal"
    path = window_state_path(script_dir)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"geometry": geom, "wm_state": state}, handle, indent=2)
        return True
    except OSError:
        return False