"""Read-only campaign picker with saved-ID management popup."""

from __future__ import annotations

import json
import os
import dark_dialog as messagebox

import customtkinter as ctk

SAVED_CAMPAIGN_IDS_KEY = "saved_campaign_ids"
THEME_DARK_BG = "#1a1a1a"
THEME_PANEL = "#242424"
THEME_ORANGE = "#c77626"
THEME_TEAL = "#1f9d8f"


def _unique_campaign_ids(values):
    seen = set()
    ordered = []
    for raw in values or []:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(text)
    return ordered


def get_saved_campaign_ids(config) -> list[str]:
    config = config or {}
    saved = _unique_campaign_ids(config.get(SAVED_CAMPAIGN_IDS_KEY) or [])
    current = str(config.get("campaign_id", "") or "").strip()
    if current and current not in saved:
        saved.insert(0, current)
    return saved


def merge_saved_campaign_ids(config, campaign_id: str) -> dict:
    """Return config copy with campaign_id set and present in saved_campaign_ids."""
    merged = dict(config or {})
    campaign_id = str(campaign_id or "").strip()
    merged["campaign_id"] = campaign_id
    saved = _unique_campaign_ids(merged.get(SAVED_CAMPAIGN_IDS_KEY) or [])
    if campaign_id:
        saved = _unique_campaign_ids([campaign_id, *saved])
    merged[SAVED_CAMPAIGN_IDS_KEY] = saved
    return merged


def load_config_file(config_path: str) -> dict:
    if not config_path or not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config_file(config_path: str, config: dict) -> dict:
    merged = load_config_file(config_path)
    merged.update(dict(config or {}))
    os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2)
    return merged


class CampaignIdPickerRow(ctk.CTkFrame):
    """Label + read-only combobox + manage (+) button for campaign IDs."""

    def __init__(
        self,
        parent,
        config: dict,
        config_path: str,
        *,
        label: str = "Game name",
        combo_width: int = 420,
        primary_color: str = THEME_ORANGE,
        on_change=None,
    ):
        super().__init__(parent, fg_color="transparent")
        self.config_path = config_path
        self.primary_color = primary_color
        self.on_change = on_change
        self._config = dict(config or {})
        self._suppress_change = True

        ctk.CTkLabel(self, text=label, width=120, anchor="w").pack(side="left", padx=(0, 6))

        self.manage_btn = ctk.CTkButton(
            self,
            text="+",
            width=40,
            height=28,
            fg_color=primary_color,
            hover_color="#a56b32",
            command=self._open_manage_popup,
        )
        self.manage_btn.pack(side="right", padx=(4, 0))

        values = get_saved_campaign_ids(self._config)
        current = str(self._config.get("campaign_id", "") or "").strip()
        self.campaign_var = ctk.StringVar(value=current)
        # Let the combobox flex; a large fixed width pushes the + button off-screen.
        combo_pixel_width = max(140, min(int(combo_width or 200), 240))
        self.combo = ctk.CTkComboBox(
            self,
            values=values or [""],
            variable=self.campaign_var,
            width=combo_pixel_width,
            state="readonly",
            command=self._on_combo_selected,
        )
        self.combo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if current:
            self.combo.set(current)
        elif values:
            self.combo.set(values[0])

        self._suppress_change = False

    def reload_config(self):
        self._config = load_config_file(self.config_path)
        self.refresh_values()

    def refresh_values(self, *, select: str | None = None):
        self._suppress_change = True
        try:
            values = get_saved_campaign_ids(self._config)
            self.combo.configure(values=values or [""])
            chosen = str(select or self.get_value() or "").strip()
            if chosen and chosen in values:
                self.combo.set(chosen)
            elif values:
                self.combo.set(values[0])
            else:
                self.campaign_var.set("")
        finally:
            self._suppress_change = False

    def get_value(self) -> str:
        return str(self.campaign_var.get() or "").strip()

    def set_value(self, value: str):
        value = str(value or "").strip()
        self._suppress_change = True
        try:
            self.campaign_var.set(value)
            if value:
                self.combo.set(value)
        finally:
            self._suppress_change = False

    def _notify_change(self):
        if callable(self.on_change):
            try:
                self.on_change(self.get_value())
            except Exception:
                pass

    def _on_combo_selected(self, choice):
        if getattr(self, "_suppress_change", False):
            return
        value = str(choice or "").strip()
        if not value:
            return
        self._config = merge_saved_campaign_ids(self._config, value)
        save_config_file(self.config_path, self._config)
        self._notify_change()

    def _persist_config(self, config: dict):
        self._config = dict(config or {})
        save_config_file(self.config_path, self._config)
        self.refresh_values(select=self._config.get("campaign_id"))
        self._notify_change()

    def _open_manage_popup(self):
        open_manage_campaign_ids_popup(
            self.winfo_toplevel(),
            self._config,
            self.config_path,
            primary_color=self.primary_color,
            on_saved=self._persist_config,
        )


def open_manage_campaign_ids_popup(
    parent,
    config: dict,
    config_path: str,
    *,
    primary_color: str = THEME_ORANGE,
    on_saved=None,
):
    working = dict(config or {})
    popup = ctk.CTkToplevel(parent)
    popup.title("Manage Campaigns")
    popup.configure(fg_color=THEME_DARK_BG)
    popup.grab_set()
    popup.geometry("460x420")
    try:
        parent.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - 460) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - 420) // 2)
        popup.geometry(f"460x420+{px}+{py}")
    except Exception:
        pass

    ctk.CTkLabel(
        popup,
        text="Campaigns",
        font=ctk.CTkFont(size=18, weight="bold"),
    ).pack(anchor="w", padx=16, pady=(14, 4))
    ctk.CTkLabel(
        popup,
        text="Add or remove campaigns here. Pick the active one from the dropdown.",
        text_color="#aaaaaa",
        wraplength=420,
        justify="left",
    ).pack(anchor="w", padx=16, pady=(0, 10))

    list_scroll = ctk.CTkScrollableFrame(popup, fg_color=THEME_PANEL, height=220)
    list_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 10))

    add_row = ctk.CTkFrame(popup, fg_color="transparent")
    add_row.pack(fill="x", padx=16, pady=(0, 10))
    new_var = ctk.StringVar(value="")
    new_entry = ctk.CTkEntry(add_row, textvariable=new_var, placeholder_text="New campaign name")
    new_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def render_list():
        for child in list_scroll.winfo_children():
            child.destroy()
        saved = get_saved_campaign_ids(working)
        if not saved:
            ctk.CTkLabel(
                list_scroll,
                text="No campaigns saved yet.",
                text_color="#888888",
            ).pack(anchor="w", padx=8, pady=8)
            return
        for game_id in saved:
            row = ctk.CTkFrame(list_scroll, fg_color="#2f2f2f", corner_radius=6)
            row.pack(fill="x", pady=3, padx=4)
            ctk.CTkLabel(row, text=game_id, anchor="w").pack(side="left", fill="x", expand=True, padx=10, pady=6)
            ctk.CTkButton(
                row,
                text="Delete",
                width=72,
                height=24,
                fg_color="#8b3a3a",
                hover_color="#6f2f2f",
                command=lambda gid=game_id: delete_id(gid),
            ).pack(side="right", padx=8, pady=4)

    def delete_id(game_id: str):
        game_id = str(game_id or "").strip()
        if not game_id:
            return
        if not messagebox.askyesno(
            "Delete Campaign",
            f"Remove '{game_id}' from saved campaigns?",
            parent=popup,
        ):
            return
        saved = [gid for gid in get_saved_campaign_ids(working) if gid != game_id]
        working[SAVED_CAMPAIGN_IDS_KEY] = saved
        current = str(working.get("campaign_id", "") or "").strip()
        if current == game_id:
            working["campaign_id"] = saved[0] if saved else ""
        render_list()

    def add_id():
        new_id = str(new_var.get() or "").strip()
        if not new_id:
            messagebox.showwarning("Campaign", "Enter a campaign name to add.", parent=popup)
            return
        working[SAVED_CAMPAIGN_IDS_KEY] = _unique_campaign_ids(
            [new_id, *get_saved_campaign_ids(working)],
        )
        new_var.set("")
        render_list()

    ctk.CTkButton(
        add_row,
        text="Add",
        width=72,
        fg_color=primary_color,
        command=add_id,
    ).pack(side="left")

    footer = ctk.CTkFrame(popup, fg_color="transparent")
    footer.pack(fill="x", padx=16, pady=(0, 14))

    def save_and_close():
        saved = _unique_campaign_ids(get_saved_campaign_ids(working))
        latest = load_config_file(config_path)
        active = str(latest.get("campaign_id", "") or "").strip()
        if not active and saved:
            active = saved[0]
        if active:
            saved = _unique_campaign_ids([active, *saved])
        merged = merge_saved_campaign_ids(latest, active)
        merged[SAVED_CAMPAIGN_IDS_KEY] = saved
        save_config_file(config_path, merged)
        if callable(on_saved):
            on_saved(merged)
        popup.destroy()

    ctk.CTkButton(
        footer, text="Cancel", width=108, height=36,
        fg_color="#555555", hover_color="#666666", command=popup.destroy,
    ).pack(side="right")
    ctk.CTkButton(
        footer, text="Save", width=108, height=36,
        fg_color=primary_color, command=save_and_close,
    ).pack(side="right", padx=(0, 8))

    render_list()
    new_entry.bind("<Return>", lambda _event: add_id())