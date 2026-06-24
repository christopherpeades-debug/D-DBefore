"""Modern dark/red statblock renderer for D&D Behind (BCC copy stays separate)."""

from __future__ import annotations

import os
import re
import sys
import time
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

from monster_statblock_icon import load_monster_image_icon
from reference_tooltips import format_feat_tooltip, format_spell_tooltip, normalize_feat_name, split_spell_line

_ASSETS_DIR = os.path.dirname(os.path.abspath(__file__))

STATBLOCK_BG = "#0c0c0e"
STATBLOCK_SURFACE = "#141418"
STATBLOCK_SURFACE_ALT = "#1a1a20"
STATBLOCK_TEXT = "#ececf0"
STATBLOCK_MUTED = "#8a8a95"
# CTkButton rejects fg_color/hover_color="transparent" on some CustomTkinter builds.
STATBLOCK_GHOST_BTN = STATBLOCK_SURFACE
STATBLOCK_GHOST_BTN_HOVER = STATBLOCK_SURFACE_ALT

STATBLOCK_THEMES = {
    "Monster": {
        "bcc_box": "box-red",
        "accent": "#FF6B5B",
        "accent_soft": "#FF857A",
        "border": "#3d2228",
        "badge_bg": "#2a1818",
        "chip_fg": "#2a1818",
        "chip_hover": "#4a2828",
        "outer_bg": "#2a1f1f",
        "outer_border": "#FF857A",
        "sash_bg": "#3d2228",
    },
    "NPC": {
        "bcc_box": "box-blue",
        "accent": "#5B9FFF",
        "accent_soft": "#7AB8FF",
        "border": "#2a3d52",
        "badge_bg": "#182028",
        "chip_fg": "#182028",
        "chip_hover": "#283848",
        "outer_bg": "#1a1f2a",
        "outer_border": "#7AB8FF",
        "sash_bg": "#22303d",
    },
}

ROLL_RE = re.compile(r"\[roll:([^|]+)\|([^\]]+)\]")
CB_RE = re.compile(r"\[c(?::([^\]]+))?\]")
DMG_PAREN_RE = re.compile(r"\((\d+d\d+(?:[+-]\d+)?)(/[^)]+)?\)", re.IGNORECASE)
BRACKET_ROLL_RE = re.compile(r"\[(\d+d\d+(?:[+-]\d+)?)\]", re.IGNORECASE)
ATK_BRACKET_RE = re.compile(r"\[\s*([+-]\d+)\s*\]")
ITER_ATK_RE = re.compile(r"(?<![\w\[])(?:[+-]\d+)(?:/[+-]\d+)+")
BARE_ROLL_TAG_RE = re.compile(
    r"(?<![\w\[])roll:([^|\]\s,;\)]*)(?:\|([^,\]\s;\)]*))?",
    re.IGNORECASE,
)


def normalize_bare_roll_tags(text: str) -> str:
    """Convert roll:expr|label into [roll:expr|label] for statblock rendering."""
    if not text:
        return text

    def _repl(match):
        expr = str(match.group(1) or "").strip().replace(" ", "")
        if not expr:
            return match.group(0)
        label = ""
        if match.lastindex and match.lastindex >= 2:
            label = str(match.group(2) or "").strip().replace(" ", "")
        if not label:
            label = expr
        return f"[roll:{expr}|{label}]"

    return BARE_ROLL_TAG_RE.sub(_repl, str(text))


def _attack_roll_tag(sign: str) -> str:
    text = str(sign or "").strip()
    if not text:
        return ""
    if not text.startswith(("+", "-")):
        text = f"+{text}"
    return f"[roll:1d20{text}|{text}]"


def auto_rollify(text: str) -> str:
    """Turn roll:expr|label, bracketed dice, (XdY+Z) damage, [+N] attacks, and [roll:expr] into clickable roll tags."""
    if not text:
        return text
    out = normalize_bare_roll_tags(str(text))

    def _normalize_roll_tag(m):
        expr = str(m.group(1) or "").strip().replace(" ", "")
        if not expr:
            return m.group(0)
        label = str(m.group(2) or "").strip().replace(" ", "") if m.lastindex and m.lastindex >= 2 else ""
        if not label:
            label = expr
        return f"[roll:{expr}|{label}]"

    out = re.sub(r"\[roll:([^|\]]+)(?:\|([^\]]*))?\]", _normalize_roll_tag, out, flags=re.IGNORECASE)

    out = ATK_BRACKET_RE.sub(lambda m: _attack_roll_tag(m.group(1)), out)
    if not ROLL_RE.search(out):
        out = ITER_ATK_RE.sub(
            lambda m: " /".join(_attack_roll_tag(part) for part in m.group(0).split("/") if part.strip()),
            out,
        )

    def _dmg(m):
        if re.search(r"\[roll:", m.group(0), re.IGNORECASE):
            return m.group(0)
        inner = m.group(1).replace(" ", "")
        suffix = m.group(2) or ""
        return f"([roll:{inner}|{inner}]{suffix})"

    out = DMG_PAREN_RE.sub(_dmg, out)

    def _bracket(m):
        inner = m.group(1).replace(" ", "")
        return f"[roll:{inner}|{inner}]"

    parts = re.split(r"(\[roll:[^\]]+\])", out, flags=re.IGNORECASE)
    rolled = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            rolled.append(part)
        else:
            rolled.append(BRACKET_ROLL_RE.sub(_bracket, part))
    return "".join(rolled)


def normalize_creature_category(category):
    cat = str(category or "Monster").strip()
    return cat if cat in STATBLOCK_THEMES else "Monster"


def get_statblock_theme(category):
    return dict(STATBLOCK_THEMES[normalize_creature_category(category)])


def _font(size=12, weight="normal", slant="roman"):
    return ctk.CTkFont(size=size, weight=weight, slant=slant)


class ModernStatblockRenderer:
    """Render structured statblock data into a scrollable modern card layout."""

    def __init__(self, host_app):
        self.app = host_app
        self._measure_fonts: dict[tuple[int, bool], tkfont.Font] = {}
        self._tooltip_state: dict[int, dict] = {}
        self._theme = get_statblock_theme("Monster")

    def _use_theme(self, theme=None):
        self._theme = dict(theme) if theme else get_statblock_theme("Monster")

    def _content_host(self, scroll_parent):
        """Persistent inner host — never destroy CTkScrollableFrame structural children."""
        host = getattr(scroll_parent, "_sb_content_host", None)
        try:
            if host is not None and host.winfo_exists():
                for child in host.winfo_children():
                    child.destroy()
                try:
                    host.pack_configure(fill="x", anchor="nw", expand=False)
                except Exception:
                    pass
                return host
        except Exception:
            pass
        try:
            scroll_parent.configure(fg_color=STATBLOCK_BG)
        except Exception:
            pass
        host = ctk.CTkFrame(scroll_parent, fg_color=STATBLOCK_BG)
        host.pack(fill="x", anchor="nw")
        scroll_parent._sb_content_host = host
        return host

    def _refresh_scroll_region(self, scroll_parent):
        """Update CTkScrollableFrame canvas scrollregion after content height changes."""
        if scroll_parent is None:
            return
        try:
            host = getattr(scroll_parent, "_sb_content_host", None)
            if host is not None and host.winfo_exists():
                host.update_idletasks()
            scroll_parent.update_idletasks()
            canvas = getattr(scroll_parent, "_parent_canvas", None)
            if canvas is not None and canvas.winfo_exists():
                bbox = canvas.bbox("all")
                if bbox:
                    canvas.configure(scrollregion=bbox)
        except Exception:
            pass

    def _bind_column_scrolling(self, scroll_parent):
        """Ensure mouse wheel scrolls this column when hovering its content (not only the canvas gutter)."""
        if scroll_parent is None:
            return
        canvas = getattr(scroll_parent, "_parent_canvas", None)
        if canvas is None:
            return

        def _wheel(event):
            try:
                if sys.platform.startswith("win"):
                    step = -int(event.delta / 6)
                elif sys.platform == "darwin":
                    step = -event.delta
                else:
                    step = -event.delta
                canvas.yview("scroll", step, "units")
            except Exception:
                pass
            return "break"

        if not getattr(scroll_parent, "_sb_wheel_bound", False):
            scroll_parent._sb_wheel_bound = True
            try:
                scroll_parent.bind("<MouseWheel>", _wheel, add="+")
                scroll_parent.bind("<Enter>", lambda _e, c=canvas: c.focus_set(), add="+")
            except Exception:
                pass

        def _walk(widget):
            try:
                widget.bind("<MouseWheel>", _wheel, add="+")
                for child in widget.winfo_children():
                    _walk(child)
            except Exception:
                pass

        host = getattr(scroll_parent, "_sb_content_host", None)
        if host is not None:
            _walk(host)

    def _finalize_scroll_columns(self, *scroll_parents):
        for scroll_parent in scroll_parents:
            if scroll_parent is None:
                continue
            self._refresh_scroll_region(scroll_parent)
            self._bind_column_scrolling(scroll_parent)
            try:
                scroll_parent.after(80, lambda sp=scroll_parent: self._refresh_scroll_region(sp))
            except Exception:
                pass

    def render(
        self, scroll_parent, view_data, *,
        features_parent=None,
        checkbox_states=None,
        on_checkbox_toggle=None,
        on_layout_change=None,
        on_edit_combat_feature=None,
        cb_prefix="",
    ):
        checkbox_states = checkbox_states if checkbox_states is not None else {}
        font_size = int(view_data.get("font_size", 12) or 12)
        self._use_theme(view_data.get("theme"))
        split = features_parent is not None

        stats_host = self._content_host(scroll_parent)
        if split:
            feat_host = self._content_host(features_parent)
            settle_until = time.monotonic() + 1.2
            for col_parent in (scroll_parent, features_parent):
                if col_parent is not None:
                    col_parent._sb_render_in_progress = True
                    col_parent._sb_resize_suppress_until = settle_until
            try:
                self._render_stats_column(
                    stats_host, view_data, font_size, checkbox_states, on_checkbox_toggle, cb_prefix,
                    column_parent=scroll_parent,
                )
                self._render_features_column(
                    feat_host,
                    view_data,
                    font_size,
                    checkbox_states,
                    on_checkbox_toggle,
                    cb_prefix,
                    column_parent=features_parent,
                    on_edit_combat_feature=on_edit_combat_feature,
                )
            finally:
                for col_parent in (scroll_parent, features_parent):
                    if col_parent is not None:
                        col_parent._sb_render_in_progress = False
            if on_layout_change is not None:
                self._bind_column_resize(features_parent, on_layout_change)
            self._finalize_scroll_columns(scroll_parent, features_parent)
        else:
            self._render_full_column(
                stats_host, view_data, font_size, checkbox_states, on_checkbox_toggle, cb_prefix,
            )
            self._finalize_scroll_columns(scroll_parent)

    def _render_full_column(self, root, view_data, font_size, checkbox_states, on_toggle, cb_prefix):
        header = view_data.get("header") or {}
        self._render_header(root, header, font_size)
        self._render_perception_card(root, view_data.get("perception") or {}, font_size)
        self._render_defense_card(root, view_data.get("defense") or {}, font_size)
        self._render_combat_card(
            root, view_data.get("combat") or {}, font_size, checkbox_states, on_toggle, cb_prefix,
        )
        self._render_sla_card(root, view_data.get("sla") or {}, font_size, checkbox_states, on_toggle, cb_prefix)
        self._render_spells_card(root, view_data.get("spells") or {}, font_size, checkbox_states, on_toggle, cb_prefix)
        self._render_abilities_card(root, view_data.get("abilities") or [], font_size)
        self._render_footer_sections(root, view_data, font_size, checkbox_states, on_toggle, cb_prefix)

    def _render_stats_column(self, root, view_data, font_size, checkbox_states, on_toggle, cb_prefix, *, column_parent=None):
        header = view_data.get("header") or {}
        self._render_header(root, header, font_size)
        self._render_perception_card(root, view_data.get("perception") or {}, font_size)
        self._render_defense_card(root, view_data.get("defense") or {}, font_size)
        self._render_abilities_card(root, view_data.get("abilities") or [], font_size)
        self._render_footer_sections(
            root, view_data, font_size, checkbox_states, on_toggle, cb_prefix, column_parent=column_parent,
        )

    def _render_custom_combat_features(
        self,
        parent,
        extra,
        font_size,
        checkbox_states,
        on_toggle,
        cb_prefix,
        *,
        wraplength,
        on_edit_combat_feature=None,
    ):
        if not extra:
            return
        self._section_label(parent, "Features", font_size)
        for feat in extra:
            if isinstance(feat, dict):
                title = str(feat.get("title") or "").strip()
                text = str(feat.get("text") or "").strip()
                feat_index = feat.get("index")
            else:
                title, text = "", str(feat).strip()
                feat_index = None
            if not text and not title:
                continue
            editable = on_edit_combat_feature is not None and feat_index is not None
            if editable:
                self._render_editable_feature_block(
                    parent,
                    title,
                    text,
                    font_size,
                    checkbox_states,
                    on_toggle,
                    cb_prefix,
                    wraplength=wraplength,
                    feature_index=int(feat_index),
                    on_edit=on_edit_combat_feature,
                )
            elif title and text:
                self._render_heading_block(
                    parent, title, text, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wraplength,
                )
            elif title:
                self._accent_heading(parent, title, font_size, wraplength=wraplength)
            else:
                self._render_rich_text(
                    parent, text, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wraplength,
                )

    def _render_features_column(
        self,
        root,
        view_data,
        font_size,
        checkbox_states,
        on_toggle,
        cb_prefix,
        *,
        column_parent=None,
        on_edit_combat_feature=None,
    ):
        wrap = self._column_wraplength(root, column_parent=column_parent, default=300)
        card = self._card(root, pad_bottom=8)
        self._section_label(card, "Combat Features", font_size)

        combat = view_data.get("combat") or {}
        self._render_combat_feature_body(
            card, combat, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wrap,
        )

        extra = view_data.get("combat_features") or []
        self._render_custom_combat_features(
            card,
            extra,
            font_size,
            checkbox_states,
            on_toggle,
            cb_prefix,
            wraplength=wrap,
            on_edit_combat_feature=on_edit_combat_feature,
        )

        sla = view_data.get("sla") or {}
        if sla.get("lines"):
            self._section_label(card, "Spell-Like Abilities", font_size)
            if sla.get("intro"):
                self._render_rich_text(card, sla["intro"], font_size, checkbox_states, on_toggle, cb_prefix, muted=True, wraplength=wrap)
            for line in sla.get("lines") or []:
                self._render_spell_aware_line(
                    card, line, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wrap,
                )

        spells = view_data.get("spells") or {}
        if spells.get("lines"):
            self._section_label(card, "Spellcasting", font_size)
            if spells.get("intro"):
                self._render_rich_text(card, spells["intro"], font_size, checkbox_states, on_toggle, cb_prefix, muted=True, wraplength=wrap)
            for line in spells.get("lines") or []:
                self._render_spell_aware_line(
                    card, line, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wrap,
                )

        if not any([
            combat.get("speed"), combat.get("melee"), combat.get("ranged"),
            combat.get("attack_options"), combat.get("special_actions"), combat.get("sq"),
            combat.get("combat_gear"), extra, sla.get("lines"), spells.get("lines"),
        ]):
            ctk.CTkLabel(
                card, text="No combat features yet.\nAdd attacks, SLAs, or use the Features column to the left of this preview.",
                font=_font(font_size - 1), text_color=STATBLOCK_MUTED, wraplength=280, justify="left",
            ).pack(padx=12, pady=12, anchor="w")

    def _card(self, parent, *, pad_bottom=8):
        frame = ctk.CTkFrame(
            parent, fg_color=STATBLOCK_SURFACE, corner_radius=10,
            border_width=1, border_color=self._theme["border"],
        )
        frame.pack(fill="x", padx=2, pady=(0, pad_bottom))
        return frame

    def _section_label(self, parent, text, font_size):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(10, 6))
        bar = ctk.CTkFrame(row, fg_color=self._theme["accent"], width=4, height=18, corner_radius=2)
        bar.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            row, text=text, font=_font(font_size, "bold"), text_color=self._theme["accent_soft"], anchor="w",
        ).pack(side="left")

    def _accent_heading(self, parent, text, font_size, *, wraplength=None):
        """Bold red inline heading (feature title, SQ label, etc.)."""
        if not text:
            return
        ctk.CTkLabel(
            parent, text=text, font=_font(font_size, "bold"), text_color=self._theme["accent_soft"],
            anchor="w", justify="left", wraplength=wraplength,
        ).pack(fill="x", padx=12, pady=(6, 2), anchor="w")

    def _border_roll_box(self, parent, title: str, label: str, expr: str, font_size, *, stacked: bool = False):
        """Bordered stat box with a +## chip that rolls 1d20+##."""
        box = ctk.CTkFrame(
            parent,
            fg_color=STATBLOCK_SURFACE_ALT,
            corner_radius=8,
            border_width=1,
            border_color=self._theme["border"],
        )
        if stacked:
            box.pack(fill="x", pady=4, anchor="w")
        else:
            box.pack(side="left", padx=(0, 8), pady=4)
        ctk.CTkLabel(box, text=title, font=_font(10), text_color=STATBLOCK_MUTED).pack(padx=10, pady=(6, 2))
        chip_row = ctk.CTkFrame(box, fg_color="transparent")
        chip_row.pack(padx=10, pady=(0, 6))
        self._roll_chip(chip_row, label, expr, font_size)
        return box

    def _combat_attack_group(
        self,
        parent,
        label: str,
        lines,
        font_size,
        checkbox_states,
        on_toggle,
        cb_prefix,
        *,
        wraplength,
    ):
        """Bold label with each attack line stacked below, individual roll chips per bonus/damage."""
        if not lines:
            return
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", padx=12, pady=(2, 4))
        lbl_text = label if label.endswith(":") or label.endswith(" ") else f"{label}:"
        ctk.CTkLabel(
            block, text=lbl_text, font=_font(font_size, "bold"), text_color=self._theme["accent_soft"], anchor="w",
        ).pack(fill="x", anchor="w")
        for line in lines:
            if not str(line).strip():
                continue
            self._render_rich_text(
                block, auto_rollify(str(line)), font_size, checkbox_states, on_toggle, cb_prefix,
                wraplength=wraplength, muted=False,
            )

    def _combat_label_line(
        self,
        parent,
        label: str,
        content: str,
        font_size,
        checkbox_states,
        on_toggle,
        cb_prefix,
        *,
        wraplength,
        roll_chips: list | None = None,
    ):
        if not content and not roll_chips:
            return
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", padx=12, pady=(2, 4))
        lbl_text = label if label.endswith(":") or label.endswith(" ") else f"{label}:"
        ctk.CTkLabel(
            block, text=lbl_text, font=_font(font_size, "bold"), text_color=self._theme["accent_soft"], anchor="w",
        ).pack(fill="x", anchor="w")
        if content:
            self._render_rich_text(
                block, auto_rollify(content), font_size, checkbox_states, on_toggle, cb_prefix,
                wraplength=wraplength, muted=False,
            )
        if roll_chips:
            chip_row = ctk.CTkFrame(block, fg_color="transparent")
            chip_row.pack(fill="x", anchor="w", pady=(2, 0))
            for chip in roll_chips:
                self._roll_chip(chip_row, chip.get("label"), chip.get("expr"), font_size)

    def _render_combat_feature_body(
        self,
        parent,
        combat: dict,
        font_size,
        checkbox_states,
        on_toggle,
        cb_prefix,
        *,
        wraplength,
    ):
        """Combat layout: Speed → Attacks → BAB/Grp → options → gear."""
        if combat.get("speed"):
            self._combat_label_line(
                parent, "Speed", str(combat["speed"]), font_size, checkbox_states, on_toggle, cb_prefix,
                wraplength=wraplength,
            )

        melee = combat.get("melee") or []
        ranged = combat.get("ranged") or []
        if melee or ranged:
            if melee:
                self._combat_attack_group(
                    parent, "Melee", melee, font_size, checkbox_states, on_toggle, cb_prefix,
                    wraplength=wraplength,
                )
            if ranged:
                self._combat_attack_group(
                    parent, "Ranged", ranged, font_size, checkbox_states, on_toggle, cb_prefix,
                    wraplength=wraplength,
                )

        if combat.get("bab") is not None:
            bab = int(combat.get("bab") or 0)
            bab_lbl = f"+{bab}" if bab >= 0 else str(bab)
            grp = int(combat.get("grp") or 0)
            grp_lbl = f"+{grp}" if grp >= 0 else str(grp)
            grp_roll = combat.get("grp_roll") or {}
            bab_roll = combat.get("bab_roll") or {}
            box_col = ctk.CTkFrame(parent, fg_color="transparent")
            box_col.pack(fill="x", padx=12, pady=(4, 4))
            self._border_roll_box(
                box_col, "Base Atk", bab_roll.get("label", bab_lbl),
                bab_roll.get("expr", f"1d20{bab_lbl}"), font_size, stacked=True,
            )
            self._border_roll_box(
                box_col, "Grp", grp_roll.get("label", grp_lbl),
                grp_roll.get("expr", f"1d20{grp_lbl}"), font_size, stacked=True,
            )

        for key, label in (("attack_options", "Attack Options"), ("special_actions", "Special Actions")):
            if combat.get(key):
                self._combat_label_line(
                    parent, label, str(combat[key]), font_size, checkbox_states, on_toggle, cb_prefix,
                    wraplength=wraplength,
                )

        gear = combat.get("combat_gear") or []
        if isinstance(gear, str):
            gear = [g.strip() for g in gear.split(",") if g.strip()]
        if gear:
            self._accent_heading(parent, "Combat Gear", font_size, wraplength=wraplength)
            for item in gear:
                self._render_rich_text(
                    parent, auto_rollify(str(item)), font_size, checkbox_states, on_toggle, cb_prefix,
                    wraplength=wraplength,
                )

        if combat.get("sq"):
            self._render_heading_block(
                parent, "SQ", combat["sq"], font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wraplength,
            )

    def _render_editable_feature_block(
        self,
        parent,
        title,
        text,
        font_size,
        checkbox_states,
        on_toggle,
        cb_prefix,
        *,
        wraplength,
        feature_index,
        on_edit,
    ):
        """Custom + Features entry with delayed hover edit control in the top-right corner."""
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="x", padx=0, pady=(0, 6))

        content = ctk.CTkFrame(outer, fg_color="transparent")
        content.pack(fill="x", expand=True)

        if title and text:
            self._render_heading_block(
                content, title, text, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wraplength,
            )
        elif title:
            self._accent_heading(content, title, font_size, wraplength=wraplength)
        else:
            self._render_rich_text(
                content, text, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wraplength,
            )

        edit_btn = ctk.CTkButton(
            outer,
            text="✎",
            width=22,
            height=22,
            fg_color=STATBLOCK_GHOST_BTN,
            hover_color=STATBLOCK_GHOST_BTN_HOVER,
            border_width=0,
            text_color=STATBLOCK_MUTED,
            font=_font(max(11, font_size)),
            command=lambda idx=feature_index: on_edit(edit_index=idx),
        )

        hover = {"show_after": None, "hide_after": None, "shown": False}
        hover_targets = {outer, content, edit_btn}

        def _cancel_show():
            if hover["show_after"] is not None:
                try:
                    outer.after_cancel(hover["show_after"])
                except Exception:
                    pass
                hover["show_after"] = None

        def _cancel_hide():
            if hover["hide_after"] is not None:
                try:
                    outer.after_cancel(hover["hide_after"])
                except Exception:
                    pass
                hover["hide_after"] = None

        def _pointer_inside():
            try:
                widget = outer.winfo_containing(outer.winfo_pointerx(), outer.winfo_pointery())
            except Exception:
                return False
            while widget is not None:
                if widget in hover_targets:
                    return True
                widget = widget.master
            return False

        def _show_edit():
            hover["show_after"] = None
            hover["shown"] = True
            edit_btn.place(relx=1.0, x=-6, y=2, anchor="ne")

        def _hide_edit():
            hover["hide_after"] = None
            hover["shown"] = False
            edit_btn.place_forget()

        def _schedule_show(_event=None):
            _cancel_hide()
            if hover["shown"] or hover["show_after"] is not None:
                return
            hover["show_after"] = outer.after(450, _show_edit)

        def _schedule_hide(_event=None):
            _cancel_show()
            if not hover["shown"]:
                return
            _cancel_hide()

            def _maybe_hide():
                if not _pointer_inside():
                    _hide_edit()

            hover["hide_after"] = outer.after(120, _maybe_hide)

        def _edit_enter(_event=None):
            _cancel_hide()
            edit_btn.configure(text_color=self._theme["accent_soft"])

        def _edit_leave(_event=None):
            edit_btn.configure(text_color=STATBLOCK_MUTED)
            _schedule_hide()

        edit_btn.bind("<Enter>", _edit_enter, add="+")
        edit_btn.bind("<Leave>", _edit_leave, add="+")

        def _bind_hover(widget):
            if widget is edit_btn:
                return
            widget.bind("<Enter>", _schedule_show, add="+")
            widget.bind("<Leave>", _schedule_hide, add="+")
            for child in widget.winfo_children():
                _bind_hover(child)

        _bind_hover(outer)

    def _render_heading_block(self, parent, heading, body, font_size, checkbox_states, on_toggle, cb_prefix, *, wraplength=260):
        """Bold red heading with wrapped body text below."""
        if not body:
            return
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", padx=0, pady=(0, 4))
        if heading:
            self._accent_heading(block, heading, font_size, wraplength=wraplength)
        self._render_rich_text(
            block, body, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wraplength,
        )

    def _roll_chip(self, parent, label, expr, font_size):
        text = str(label or "").strip() or "roll"
        btn = ctk.CTkButton(
            parent,
            text=text,
            width=max(36, min(72, 10 + len(text) * 7)),
            height=24,
            font=_font(max(10, font_size - 1), "bold"),
            fg_color=self._theme["chip_fg"],
            hover_color=self._theme["chip_hover"],
            text_color=self._theme["accent_soft"],
            border_width=1,
            border_color=self._theme["accent"],
            command=lambda e=expr, lb=text: self.app._roll_dice(e, lb),
        )
        btn.pack(side="left", padx=(0, 4), pady=2)
        return btn

    def _tokenize_rich_text(self, text):
        specials = []
        for m in ROLL_RE.finditer(text):
            specials.append((m.start(), m.end(), "roll", m))
        for m in CB_RE.finditer(text):
            specials.append((m.start(), m.end(), "cb", m))
        specials.sort(key=lambda x: x[0])
        tokens = []
        pos = 0
        for start, end, kind, match in specials:
            if start > pos:
                tokens.append(("plain", text[pos:start]))
            tokens.append((kind, match))
            pos = end
        if pos < len(text):
            tokens.append(("plain", text[pos:]))
        return tokens

    def _get_measure_font(self, font_size, *, muted=False):
        key = (font_size, muted)
        cached = self._measure_fonts.get(key)
        if cached is not None:
            return cached
        size = font_size - 1 if muted else font_size
        cached = tkfont.Font(size=size)
        self._measure_fonts[key] = cached
        return cached

    def _measure_text_width(self, text, font_size, *, muted=False):
        if not text:
            return 0
        return int(self._get_measure_font(font_size, muted=muted).measure(text))

    def _render_wrapped_flow(
        self, parent, text, font_size, checkbox_states, on_checkbox_toggle, cb_prefix, *,
        wraplength, muted=False,
    ):
        tokens = self._tokenize_rich_text(text)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", anchor="w")
        row_width = 0
        cb_counter = {"n": 0}
        body_font = _font(font_size - 1 if muted else font_size)
        body_color = STATBLOCK_MUTED if muted else STATBLOCK_TEXT

        def _new_row():
            nonlocal row, row_width
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", anchor="w")
            row_width = 0

        def _reserve(width):
            nonlocal row_width
            if row_width > 0 and row_width + width > wraplength:
                _new_row()
            row_width += width

        def _pack_plain_words(words):
            nonlocal row_width
            if not words:
                return
            chunk = []
            chunk_width = 0
            space_w = self._measure_text_width(" ", font_size, muted=muted)

            def _flush():
                nonlocal chunk, chunk_width, row_width
                if not chunk:
                    return
                text = " ".join(chunk)
                width = self._measure_text_width(text, font_size, muted=muted)
                _reserve(width)
                ctk.CTkLabel(
                    row, text=text, font=body_font, text_color=body_color, anchor="w",
                ).pack(side="left", anchor="w")
                chunk = []
                chunk_width = 0

            for word in words:
                word_w = self._measure_text_width(word, font_size, muted=muted)
                extra = chunk_width + (space_w if chunk else 0) + word_w
                if chunk and row_width + extra > wraplength:
                    _flush()
                    extra = word_w
                if chunk:
                    chunk_width += space_w
                chunk.append(word)
                chunk_width += word_w
            _flush()

        for kind, payload in tokens:
            if kind == "plain":
                plain = str(payload)
                if " /" in plain or plain.startswith("/"):
                    segments = re.split(r"\s*(/)\s*", plain)
                    for seg in segments:
                        if seg == "/":
                            _reserve(self._measure_text_width(" / ", font_size, muted=muted))
                            ctk.CTkLabel(row, text=" / ", font=body_font, text_color=body_color).pack(side="left")
                            row_width += self._measure_text_width(" / ", font_size, muted=muted)
                        else:
                            words = [part for part in seg.split() if part]
                            _pack_plain_words(words)
                else:
                    words = [part for part in plain.split() if part]
                    _pack_plain_words(words)
            elif kind == "roll":
                match = payload
                label = str(match.group(2) or "").strip() or "roll"
                est = max(44, 10 + len(label) * 7)
                _reserve(est)
                self._roll_chip(row, label, match.group(1), font_size)
            elif kind == "cb":
                match = payload
                key = (match.group(1) or "").strip()
                if not key:
                    key = f"{cb_prefix}__auto_cb_{cb_counter['n']}"
                    cb_counter["n"] += 1
                checked = bool(checkbox_states.get(key, False))
                glyph = "☑" if checked else "☐"

                def _toggle(k=key):
                    checkbox_states[k] = not checkbox_states.get(k, False)
                    if on_checkbox_toggle:
                        on_checkbox_toggle()

                _reserve(32)
                ctk.CTkButton(
                    row, text=glyph, width=28, height=24, font=_font(font_size),
                    fg_color=STATBLOCK_GHOST_BTN, hover_color="#2a2828", text_color="#5ec4b7",
                    command=_toggle,
                ).pack(side="left", padx=(0, 2))

        for child in list(parent.winfo_children()):
            try:
                if not child.winfo_children():
                    child.destroy()
            except Exception:
                pass

    def _cancel_delayed_tooltip(self, widget):
        state = self._tooltip_state.get(id(widget))
        if not state:
            return
        after_id = state.get("after")
        if after_id is not None:
            try:
                widget.after_cancel(after_id)
            except Exception:
                pass
            state["after"] = None

    def _bind_delayed_tooltip(self, widget, text, *, delay_ms=450):
        if not str(text or "").strip():
            return
        tip_text = str(text)
        state = {"after": None, "top": None}
        self._tooltip_state[id(widget)] = state

        def _hide(_evt=None):
            self._cancel_delayed_tooltip(widget)
            top = state.get("top")
            if top is not None:
                try:
                    top.destroy()
                except Exception:
                    pass
                state["top"] = None

        def _show(_evt=None):
            state["after"] = None
            if state.get("top"):
                return
            try:
                top = tk.Toplevel(widget)
                top.overrideredirect(True)
                top.attributes("-topmost", True)
                frm = ctk.CTkFrame(
                    top, fg_color="#1f1f1f", border_width=1, border_color="#444", corner_radius=5,
                )
                frm.pack()
                ctk.CTkLabel(
                    frm, text=tip_text, font=_font(9), text_color="#ccc",
                    wraplength=320, justify="left", anchor="nw",
                ).pack(padx=8, pady=6)
                top.update_idletasks()
                x = widget.winfo_rootx()
                y = widget.winfo_rooty() + widget.winfo_height() + 2
                top.geometry(f"+{x}+{y}")
                state["top"] = top
            except Exception:
                pass

        def _schedule(_evt=None):
            _hide()
            state["after"] = widget.after(delay_ms, _show)

        try:
            widget.bind("<Enter>", _schedule, add="+")
            widget.bind("<Leave>", _hide, add="+")
            widget.bind("<Button-1>", _hide, add="+")
        except Exception:
            pass

    def _render_feat_entry(self, parent, feat_name, font_size, *, wraplength, prefix: str = ""):
        text = str(feat_name or "").strip()
        if not text:
            return
        display = f"{prefix}{text}" if prefix else text
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", padx=12, pady=(0, 4))
        lbl = ctk.CTkLabel(
            block, text=display, font=_font(font_size), text_color=STATBLOCK_TEXT,
            wraplength=wraplength, justify="left", anchor="w",
        )
        lbl.pack(fill="x", anchor="w")
        tip = format_feat_tooltip(text)
        if tip:
            self._bind_delayed_tooltip(lbl, tip)
            try:
                lbl.configure(cursor="hand2")
            except Exception:
                pass

    def _render_spell_aware_line(
        self, parent, line, font_size, checkbox_states, on_checkbox_toggle, cb_prefix, *,
        wraplength, muted=False,
    ):
        text = str(line or "").strip()
        if not text:
            return
        if ROLL_RE.search(text) or CB_RE.search(text):
            self._render_rich_text(
                parent, text, font_size, checkbox_states, on_checkbox_toggle, cb_prefix,
                wraplength=wraplength, muted=muted,
            )
            return

        prefix, tokens = split_spell_line(text)
        if not tokens:
            self._render_rich_text(
                parent, text, font_size, checkbox_states, on_checkbox_toggle, cb_prefix,
                wraplength=wraplength, muted=muted,
            )
            return

        tips = [format_spell_tooltip(tok) for tok in tokens]
        if not any(tips):
            self._render_rich_text(
                parent, text, font_size, checkbox_states, on_checkbox_toggle, cb_prefix,
                wraplength=wraplength, muted=muted,
            )
            return

        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", padx=12, pady=(0, 4))
        body_font = _font(font_size - 1 if muted else font_size)
        body_color = STATBLOCK_MUTED if muted else STATBLOCK_TEXT
        row = ctk.CTkFrame(block, fg_color="transparent")
        row.pack(fill="x", anchor="w")
        row_width = 0

        def _new_row():
            nonlocal row, row_width
            row = ctk.CTkFrame(block, fg_color="transparent")
            row.pack(fill="x", anchor="w")
            row_width = 0

        def _pack_piece(widget, width_est):
            nonlocal row_width
            if row_width > 0 and row_width + width_est > wraplength:
                _new_row()
            widget.pack(side="left", anchor="w", pady=(2, 0))
            row_width += width_est

        if prefix:
            prefix_text = f"{prefix} — "
            _pack_piece(
                ctk.CTkLabel(row, text=prefix_text, font=body_font, text_color=body_color, anchor="w"),
                self._measure_text_width(prefix_text, font_size, muted=muted),
            )

        for idx, tok in enumerate(tokens):
            if idx > 0:
                _pack_piece(
                    ctk.CTkLabel(row, text=", ", font=body_font, text_color=body_color, anchor="w"),
                    self._measure_text_width(", ", font_size, muted=muted),
                )
            est = max(40, self._measure_text_width(tok, font_size, muted=muted) + 4)
            lbl = ctk.CTkLabel(row, text=tok, font=body_font, text_color=body_color, anchor="w")
            _pack_piece(lbl, est)
            tip = format_spell_tooltip(tok)
            if tip:
                self._bind_delayed_tooltip(lbl, tip)
                try:
                    lbl.configure(cursor="hand2")
                except Exception:
                    pass

    def _render_rich_text(
        self, parent, text, font_size, checkbox_states, on_checkbox_toggle, cb_prefix,
        *, wraplength=640, muted=False,
    ):
        if not text:
            return
        text = auto_rollify(str(text))
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", padx=12, pady=(0, 4))

        if not ROLL_RE.search(text) and not CB_RE.search(text):
            ctk.CTkLabel(
                block, text=text, font=_font(font_size - 1 if muted else font_size),
                text_color=STATBLOCK_MUTED if muted else STATBLOCK_TEXT,
                wraplength=wraplength, justify="left", anchor="nw",
            ).pack(fill="x", anchor="w")
            return

        paragraphs = str(text).split("\n")
        for idx, para in enumerate(paragraphs):
            if not para:
                if idx < len(paragraphs) - 1:
                    ctk.CTkFrame(block, height=6, fg_color="transparent").pack()
                continue
            self._render_wrapped_flow(
                block, para, font_size, checkbox_states, on_checkbox_toggle, cb_prefix,
                wraplength=wraplength, muted=muted,
            )

    def _render_header(self, parent, header, font_size):
        card = self._card(parent, pad_bottom=10)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")

        name = str(header.get("name") or "Monster").strip()
        name_row = ctk.CTkFrame(top, fg_color="transparent")
        name_row.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            name_row, text=name, font=_font(font_size + 8, "bold"),
            text_color=self._theme["accent_soft"], anchor="w",
        ).pack(side="left")
        image_url = str(header.get("image_url") or "").strip()
        if image_url:
            def _open_monster_image(_event=None):
                ctx = getattr(self.app, "_preview_monster_context", None) or getattr(self.app, "current_monster", None)
                if ctx and getattr(self.app, "_open_monster_image_popup", None):
                    self.app._open_monster_image_popup(ctx)

            icon_size = max(22, min(30, font_size + 10))
            icon = load_monster_image_icon(
                _ASSETS_DIR,
                color=self._theme["accent_soft"],
                size=icon_size,
            )
            if icon is not None:
                img_btn = ctk.CTkLabel(
                    name_row,
                    text="",
                    image=icon,
                    width=icon_size + 2,
                    height=icon_size + 2,
                    fg_color="transparent",
                )
                img_btn._icon_ref = icon
                img_btn.pack(side="left", padx=(8, 0))
                img_btn.bind("<Button-1>", _open_monster_image)
                img_btn.bind("<Enter>", lambda _e: img_btn.configure(cursor="hand2"))
                img_btn.bind("<Leave>", lambda _e: img_btn.configure(cursor=""))
            else:
                fallback = ctk.CTkLabel(
                    name_row,
                    text="[Image]",
                    font=_font(font_size, "bold"),
                    text_color=self._theme["accent_soft"],
                    cursor="hand2",
                )
                fallback.pack(side="left", padx=(8, 0))
                fallback.bind("<Button-1>", _open_monster_image)

        cr = header.get("cr", "?")
        badge = ctk.CTkFrame(
            top, fg_color=self._theme["badge_bg"], corner_radius=8,
            border_width=1, border_color=self._theme["accent"],
        )
        badge.pack(side="right", padx=(8, 0))
        ctk.CTkLabel(
            badge, text=f"CR {cr}", font=_font(font_size, "bold"), text_color=self._theme["accent_soft"],
        ).pack(padx=10, pady=4)
        chip_row = ctk.CTkFrame(badge, fg_color="transparent")
        chip_row.pack(padx=6, pady=(0, 6))
        self._roll_chip(chip_row, "d20", "1d20", font_size)
        self._roll_chip(chip_row, "d%", "1d100", font_size)

        type_line = str(header.get("type_line") or "").strip()
        if type_line:
            ctk.CTkLabel(
                inner, text=type_line, font=_font(font_size + 1),
                text_color=STATBLOCK_TEXT, anchor="w",
            ).pack(fill="x", pady=(6, 0))
        class_line = str(header.get("class_line") or "").strip()
        if class_line:
            ctk.CTkLabel(
                inner, text=class_line, font=_font(font_size),
                text_color=STATBLOCK_MUTED, anchor="w",
            ).pack(fill="x", pady=(2, 0))

    def _render_perception_card(self, parent, data, font_size):
        if not any(data.get(k) for k in ("senses", "listen", "spot", "langs", "aura", "init_roll")):
            return
        card = self._card(parent)
        self._section_label(card, "Initiative & Senses", font_size)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkLabel(row, text="Init", font=_font(font_size - 1, "bold"), text_color=STATBLOCK_MUTED).pack(side="left")
        init = data.get("init_roll") or {}
        self._roll_chip(row, init.get("label", "+0"), init.get("expr", "1d20"), font_size)
        if data.get("senses"):
            ctk.CTkLabel(
                row, text=f"  ·  Senses {data['senses']}", font=_font(font_size - 1),
                text_color=STATBLOCK_TEXT, wraplength=500,
            ).pack(side="left", padx=(8, 0))
        if data.get("listen"):
            ctk.CTkLabel(row, text="Listen", font=_font(font_size - 2), text_color=STATBLOCK_MUTED).pack(side="left", padx=(8, 2))
            self._roll_chip(row, data["listen"].get("label"), data["listen"].get("expr"), font_size)
        if data.get("spot"):
            ctk.CTkLabel(row, text="Spot", font=_font(font_size - 2), text_color=STATBLOCK_MUTED).pack(side="left", padx=(8, 2))
            self._roll_chip(row, data["spot"].get("label"), data["spot"].get("expr"), font_size)
        if data.get("langs"):
            self._render_rich_text(card, f"Languages: {data['langs']}", font_size, {}, None, "", muted=True)
        if data.get("aura"):
            self._render_rich_text(card, f"Aura: {data['aura']}", font_size, {}, None, "", muted=True)

    def _render_defense_card(self, parent, data, font_size):
        card = self._card(parent)
        self._section_label(card, "Defense", font_size)

        stats_row = ctk.CTkFrame(card, fg_color="transparent")
        stats_row.pack(fill="x", padx=12, pady=(0, 6))

        left_group = ctk.CTkFrame(stats_row, fg_color="transparent")
        left_group.pack(side="left")

        right_group = ctk.CTkFrame(stats_row, fg_color="transparent")
        right_group.pack(side="left", padx=(12, 0))

        def _border_box(parent_frame):
            return ctk.CTkFrame(
                parent_frame,
                fg_color=STATBLOCK_SURFACE_ALT,
                corner_radius=8,
                border_width=1,
                border_color=self._theme["border"],
            )

        def _stat_chip(parent_frame, title, value, detail=""):
            box = _border_box(parent_frame)
            box.pack(side="left", padx=(0, 8), pady=4)
            ctk.CTkLabel(box, text=title, font=_font(10), text_color=STATBLOCK_MUTED).pack(padx=10, pady=(6, 0))
            ctk.CTkLabel(
                box, text=str(value), font=_font(font_size + 4, "bold"), text_color=self._theme["accent_soft"],
            ).pack(padx=10)
            if detail:
                ctk.CTkLabel(
                    box, text=detail, font=_font(9), text_color=STATBLOCK_MUTED, wraplength=120,
                ).pack(padx=10, pady=(0, 6))
            else:
                ctk.CTkFrame(box, height=6, fg_color="transparent").pack()

        def _save_chip(parent_frame, title, save):
            box = _border_box(parent_frame)
            box.pack(side="left", padx=(0, 8), pady=4)
            ctk.CTkLabel(
                box, text=title, font=_font(10), text_color=STATBLOCK_MUTED,
            ).pack(padx=10, pady=(6, 2))
            chip_row = ctk.CTkFrame(box, fg_color="transparent")
            chip_row.pack(padx=10, pady=(0, 6))
            self._roll_chip(chip_row, save.get("label"), save.get("expr"), font_size)

        ac_detail = str(data.get("ac_breakdown") or "").strip()
        touch = data.get("touch")
        ff = data.get("ff")
        extras = []
        if touch not in (None, "", 0):
            extras.append(f"T {touch}")
        if ff not in (None, "", 0):
            extras.append(f"FF {ff}")
        if extras:
            ac_detail = (ac_detail + "  " if ac_detail else "") + "  ".join(extras)
        _stat_chip(left_group, "AC", data.get("ac", "—"), ac_detail)
        dr = data.get("dr")
        _stat_chip(
            left_group,
            "HP",
            data.get("hp", "—"),
            f"({data.get('hd_display', '')})" + (f"  DR {dr}" if dr else ""),
        )

        save_map = {
            str(save.get("name") or "").strip(): save
            for save in (data.get("saves") or [])
        }
        for save_name in ("Fort", "Ref", "Will"):
            save = save_map.get(save_name)
            if save is not None:
                _save_chip(right_group, save_name, save)

        for key, label in (("immune", "Immune"), ("resist", "Resist"), ("sr", "SR")):
            val = data.get(key)
            if val:
                self._render_rich_text(card, f"{label}: {val}", font_size, {}, None, "", muted=True)

    def _render_combat_card(self, parent, data, font_size, checkbox_states, on_toggle, cb_prefix):
        if not data:
            return
        card = self._card(parent)
        self._section_label(card, "Combat", font_size)
        self._render_combat_feature_body(
            card, data, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=640,
        )

    def _render_sla_card(self, parent, data, font_size, checkbox_states, on_toggle, cb_prefix):
        if not data or not data.get("lines"):
            return
        card = self._card(parent)
        self._section_label(card, "Spell-Like Abilities", font_size)
        if data.get("intro"):
            self._render_rich_text(card, data["intro"], font_size, checkbox_states, on_toggle, cb_prefix, muted=True)
        for line in data.get("lines") or []:
            self._render_spell_aware_line(
                card, line, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=640,
            )

    def _render_spells_card(self, parent, data, font_size, checkbox_states, on_toggle, cb_prefix):
        if not data or not data.get("lines"):
            return
        card = self._card(parent)
        self._section_label(card, "Spellcasting", font_size)
        if data.get("intro"):
            self._render_rich_text(card, data["intro"], font_size, checkbox_states, on_toggle, cb_prefix, muted=True)
        for line in data.get("lines") or []:
            self._render_spell_aware_line(
                card, line, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=640,
            )

    def _render_abilities_card(self, parent, abilities, font_size):
        if not abilities:
            return
        card = self._card(parent)
        self._section_label(card, "Abilities", font_size)
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=(0, 10))
        for col, ab in enumerate(abilities):
            cell = ctk.CTkFrame(grid, fg_color=STATBLOCK_SURFACE_ALT, corner_radius=8)
            cell.grid(row=0, column=col, padx=3, pady=2, sticky="nsew")
            grid.grid_columnconfigure(col, weight=1)
            score = ab.get("score")
            ctk.CTkLabel(
                cell, text=ab.get("abbr", "?"), font=_font(10, "bold"), text_color=STATBLOCK_MUTED,
            ).pack(pady=(6, 0))
            if score is None:
                ctk.CTkLabel(cell, text="—", font=_font(font_size + 2, "bold"), text_color=STATBLOCK_TEXT).pack(pady=(0, 6))
            else:
                ctk.CTkLabel(
                    cell, text=str(score), font=_font(font_size + 2, "bold"), text_color=STATBLOCK_TEXT,
                ).pack()
                self._roll_chip(cell, ab.get("label", "+0"), ab.get("expr", "1d20"), font_size)

    def _widget_widths(self, *widgets):
        widths: list[int] = []
        for widget in widgets:
            if widget is None:
                continue
            try:
                widget.update_idletasks()
                w = int(widget.winfo_width() or 0)
                if w > 80:
                    widths.append(w)
            except Exception:
                pass
        return widths

    def _column_wraplength(self, content_parent, *, column_parent=None, default=300):
        """Use the scroll column viewport width, not the full statblock split pane."""
        for widget in (column_parent, content_parent):
            if widget is None:
                continue
            try:
                widget.update_idletasks()
                w = int(widget.winfo_width() or 0)
                if w > 80:
                    return max(160, w - 24)
            except Exception:
                pass
        return default

    def _footer_wraplength(self, parent, default=300, *, column_parent=None):
        return self._column_wraplength(parent, column_parent=column_parent, default=default)

    def _bind_column_resize(self, column_parent, on_layout_change):
        if column_parent is None or on_layout_change is None:
            return

        def _debounced_refresh():
            column_parent._sb_wrap_after_id = None
            if getattr(column_parent, "_sb_render_in_progress", False):
                return
            try:
                on_layout_change()
            except Exception:
                pass

        def _on_configure(event):
            if getattr(column_parent, "_sb_render_in_progress", False):
                return
            if time.monotonic() < float(getattr(column_parent, "_sb_resize_suppress_until", 0) or 0):
                return
            if int(getattr(event, "width", 0) or 0) < 80:
                return
            new_wrap = max(160, int(event.width) - 24)
            last_wrap = getattr(column_parent, "_sb_last_wrap", 0)
            if last_wrap and abs(new_wrap - last_wrap) < 16:
                return
            column_parent._sb_last_wrap = new_wrap
            after_id = getattr(column_parent, "_sb_wrap_after_id", None)
            if after_id is not None:
                try:
                    column_parent.after_cancel(after_id)
                except Exception:
                    pass
            column_parent._sb_wrap_after_id = column_parent.after(250, _debounced_refresh)

        bind_id = getattr(column_parent, "_sb_wrap_bind_id", None)
        if bind_id is not None:
            try:
                column_parent.unbind("<Configure>", bind_id)
            except Exception:
                pass
        column_parent._sb_wrap_bind_id = column_parent.bind("<Configure>", _on_configure, add="+")

    def _render_footer_sections(self, parent, view_data, font_size, checkbox_states, on_toggle, cb_prefix, *, column_parent=None):
        card = self._card(parent, pad_bottom=4)
        wrap = self._footer_wraplength(parent, default=300, column_parent=column_parent)
        for key, label in (("feats", "Feats"), ("skills", "Skills"), ("equipment", "Equipment")):
            val = view_data.get(key)
            if not val:
                continue
            self._section_label(card, label, font_size)
            if key == "skills" and isinstance(val, list):
                for s in val:
                    name = str(s.get("name") or "").strip()
                    if not name:
                        continue
                    if s.get("label") is not None:
                        text = f"{name} [roll:1d20{s.get('label')}|{s.get('label')}]"
                    else:
                        text = name
                    self._render_rich_text(
                        card, text, font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wrap,
                    )
            elif key == "feats":
                human = str(view_data.get("human_bonus_feat") or "").strip()
                if human:
                    self._render_feat_entry(
                        card, human, font_size, wraplength=wrap, prefix="Human racial feat: ",
                    )
                raw = str(val).strip()
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                if human:
                    human_key = normalize_feat_name(human).lower()
                    parts = [p for p in parts if normalize_feat_name(p).lower() != human_key]
                for part in parts:
                    self._render_feat_entry(card, part, font_size, wraplength=wrap)
            else:
                self._render_rich_text(
                    card, str(val), font_size, checkbox_states, on_toggle, cb_prefix, wraplength=wrap,
                )