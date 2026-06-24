"""Render DM-shared follower statblocks in D&D Beside."""

from __future__ import annotations

import json

import customtkinter as ctk

try:
    from statblock_viewer import ModernStatblockRenderer
    HAS_STATBLOCK_VIEWER = True
except ImportError:
    ModernStatblockRenderer = None
    HAS_STATBLOCK_VIEWER = False


def normalize_view_data(entry):
    raw = (entry or {}).get("view_data_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def normalize_monster(entry):
    raw = (entry or {}).get("monster_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def follower_display_name(entry):
    name = str((entry or {}).get("follower_name") or "").strip()
    if name:
        return name
    monster = normalize_monster(entry)
    return str(monster.get("name") or "Follower").strip() or "Follower"


def render_follower_statblock(host, scroll_parent, view_data, *, features_parent=None, checkbox_states=None):
    if not HAS_STATBLOCK_VIEWER or not view_data:
        ctk.CTkLabel(
            scroll_parent,
            text="Statblock viewer unavailable.",
            text_color="#888888",
        ).pack(padx=12, pady=12)
        return None
    renderer = ModernStatblockRenderer(host)
    host._statblock_renderer = renderer
    renderer.render(
        scroll_parent,
        view_data,
        features_parent=features_parent,
        checkbox_states=checkbox_states or {},
        on_checkbox_toggle=None,
        on_layout_change=None,
        on_edit_combat_feature=None,
    )
    return renderer