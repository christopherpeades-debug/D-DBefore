"""Multi-step level-up wizard for D&D Beside."""

from __future__ import annotations

import copy
import random
import re
import tkinter as tk
import uuid
import dark_dialog as messagebox

import customtkinter as ctk

from character_creation_wizard import _is_class_skill, _iter_wizard_skill_rows
from languages import (
    CLASS_LANGUAGE_GRANTS,
    SPEAK_LANGUAGE_SKILL,
    build_language_picker,
    collect_character_languages,
    speak_language_options,
)

THEME_DARK_BG = "#1a1a1a"
THEME_DARK_TRACK = "#2F2F2F"
THEME_ORANGE = "#c77626"
THEME_TEAL = "#28a99e"
UNSELECTED_BTN = "#3a3a3a"

ABILITY_NAMES = ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma")
SPONTANEOUS_CASTERS = {"Sorcerer", "Bard"}
DIVINE_PREPARED_CASTERS = {"Cleric", "Druid", "Paladin", "Ranger"}
WIZARD_CLASSES = (
    "Barbarian", "Bard", "Cleric", "Druid", "Fighter",
    "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard",
)

try:
    import warlock_support as _warlock_support
except ImportError:
    _warlock_support = None

WIZARD_WIDTH = 980
WIZARD_HEIGHT = 680
WIZARD_WRAPLENGTH = 900


def _parse_hit_die_sides(hit_die):
    text = str(hit_die or "").strip().lower()
    match = re.search(r"d(\d+)", text)
    return int(match.group(1)) if match else 0


def _ability_mod(score):
    try:
        return (int(score) - 10) // 2
    except (TypeError, ValueError):
        return 0


class LevelUpWizard:
    """Guide a single class level increase with feats, HP, skills, and spells."""

    def __init__(self, sheet, *, on_complete=None, on_cancel=None):
        self.sheet = sheet
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        self.root = sheet.root

        self.state = {
            "slot_index": None,
            "class_name": "",
            "new_class_level": 0,
            "new_total_level": 0,
            "new_total_hd": 0,
            "asi_milestone": None,
            "asi_ability": "",
            "feat_milestone": None,
            "general_feat_slot": None,
            "general_feat": "",
            "bonus_feat_key": "",
            "bonus_feat": "",
            "bonus_feat_pool": "",
            "hp_roll": 0,
            "skill_points": 0,
            "skill_rank_additions": {},
            "speak_language_choices": [],
            "spells_to_add": [],
            "spell_plan": None,
            "invocations_to_add": [],
            "invocation_pick_count": 0,
        }
        self._step_index = 0
        self._content_frame = None
        self._title_label = None
        self._step_label = None
        self._back_btn = None
        self._next_btn = None
        self._class_choice_var = tk.StringVar(value="")
        self._new_class_var = tk.StringVar(value="")
        self._hp_var = tk.StringVar(value="")
        self._skill_var = tk.StringVar(value="")
        self._asi_var = tk.StringVar(value="")
        self._general_feat_var = tk.StringVar(value="")
        self._bonus_feat_var = tk.StringVar(value="")
        self._class_buttons = {}
        self._add_class_panel = None
        self._add_class_status_label = None
        self._spell_level_buttons = {}
        self._active_spell_level = 0
        self._spell_status_label = None
        self._spell_list_frame = None
        self._spell_search_var = tk.StringVar(value="")
        self._spell_db_popup = None
        self._skill_budget_label = None
        self._skill_rank_labels = {}
        self._skill_minus_buttons = {}
        self._skill_plus_buttons = {}
        self._speak_language_picker = None

        self.popup = ctk.CTkToplevel(self.root)
        self.popup.title("Level Up")
        self.popup.geometry(f"{WIZARD_WIDTH}x{WIZARD_HEIGHT}")
        self.popup.configure(fg_color=THEME_DARK_BG)
        self.popup.transient(self.root)
        self.popup.grab_set()
        self._center_popup()

        primary = self._primary_color()
        header = ctk.CTkFrame(self.popup, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))
        self._title_label = ctk.CTkLabel(
            header, text="Level Up",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=primary,
        )
        self._title_label.pack(side="left")
        self._step_label = ctk.CTkLabel(
            header, text="", text_color="#888888",
            font=ctk.CTkFont(size=12),
        )
        self._step_label.pack(side="right")

        self._content_frame = ctk.CTkFrame(self.popup, fg_color="transparent")
        self._content_frame.pack(fill="both", expand=True, padx=20, pady=8)

        footer = ctk.CTkFrame(self.popup, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(8, 16))
        self._back_btn = ctk.CTkButton(
            footer, text="Back", width=90, fg_color="#555555",
            command=self._go_back,
        )
        self._back_btn.pack(side="left")
        ctk.CTkButton(
            footer, text="Cancel", width=90, fg_color="#444444",
            command=self._cancel,
        ).pack(side="left", padx=(8, 0))
        self._next_btn = ctk.CTkButton(
            footer, text="Next", width=110,
            fg_color=primary, hover_color=self._primary_hover(),
            command=self._go_next,
        )
        self._next_btn.pack(side="right")

        self.popup.protocol("WM_DELETE_WINDOW", self._cancel)
        self._ensure_dbs()
        self._render_step()

    def _primary_color(self):
        return getattr(self.sheet, "primary_button_color", THEME_ORANGE)

    def _primary_hover(self):
        return getattr(self.sheet, "primary_hover_color", "#a56b32")

    def _secondary_color(self):
        return getattr(self.sheet, "secondary_button_color", THEME_TEAL)

    def _center_popup(self):
        try:
            if hasattr(self.sheet, "_center_popup_on_root"):
                self.sheet._center_popup_on_root(self.popup, WIZARD_WIDTH, WIZARD_HEIGHT)
        except Exception:
            pass

    def _ensure_dbs(self):
        for loader, attr in (
            ("load_classes_db", "classes_db"),
            ("load_feats_db", "feats_db"),
            ("load_spells_db", "spells_db"),
        ):
            if not getattr(self.sheet, attr, None):
                fn = getattr(self.sheet, loader, None)
                if fn:
                    try:
                        fn()
                    except Exception:
                        pass
        if getattr(self.sheet, "spells_db", None) and hasattr(self.sheet, "_rebuild_spell_indexes"):
            try:
                self.sheet._rebuild_spell_indexes()
            except Exception:
                pass

    def _get_step_order(self):
        steps = ["class", "progression", "health"]
        if self._speak_language_ranks_added() > 0:
            steps.append("speak_language")
        if self._needs_spell_step():
            steps.append("spells")
        if self._needs_invocation_step():
            steps.append("invocations")
        return steps

    def _current_step(self):
        return self._get_step_order()[self._step_index]

    def _clear_content(self):
        if self._content_frame:
            for w in self._content_frame.winfo_children():
                w.destroy()
        self._class_buttons = {}
        self._add_class_panel = None
        self._add_class_status_label = None
        self._spell_level_buttons = {}
        self._spell_list_frame = None
        self._spell_status_label = None
        self._skill_budget_label = None
        self._skill_rank_labels = {}
        self._skill_minus_buttons = {}
        self._skill_plus_buttons = {}
        self._speak_language_picker = None

    def _speak_language_ranks_added(self):
        addition = float(
            (self.state.get("skill_rank_additions") or {}).get(SPEAK_LANGUAGE_SKILL, 0) or 0,
        )
        if addition <= 0:
            return 0
        if abs(addition - round(addition)) < 0.001:
            return int(round(addition))
        return int(addition)

    def _level_up_known_languages(self):
        data = copy.deepcopy(self.sheet.data)
        additions = self.state.get("speak_language_choices") or []
        if additions:
            existing = list(data.get("speak_language_languages") or [])
            data["speak_language_languages"] = existing + list(additions)
        races = getattr(self.sheet, "races", {}) or {}
        return collect_character_languages(data, races)

    def _render_step(self):
        self._clear_content()
        steps = self._get_step_order()
        step = steps[self._step_index]
        titles = {
            "class": "Choose a Class to Advance",
            "progression": "Ability Score or Feats",
            "health": "Hit Points, Skills & New Features",
            "speak_language": "Speak Language",
            "spells": "Spells Gained",
            "invocations": "Invocations Gained",
        }
        self._title_label.configure(text=titles.get(step, "Level Up"))
        self._step_label.configure(text=f"Step {self._step_index + 1} of {len(steps)}")
        self._back_btn.configure(state="normal" if self._step_index > 0 else "disabled")

        builders = {
            "class": self._build_class_step,
            "progression": self._build_progression_step,
            "health": self._build_health_step,
            "speak_language": self._build_speak_language_step,
            "spells": self._build_spells_step,
            "invocations": self._build_invocations_step,
        }
        builders[step]()
        is_last = self._step_index >= len(steps) - 1
        self._next_btn.configure(text="Finish" if is_last else "Next")

    def _go_back(self):
        if self._step_index > 0:
            self._step_index -= 1
            self._render_step()

    def _go_next(self):
        if not self._validate_current_step():
            return
        steps = self._get_step_order()
        if self._step_index < len(steps) - 1:
            self._step_index += 1
            if steps[self._step_index] == "health":
                self._prepare_health_defaults()
            if steps[self._step_index] == "spells":
                self.state["asi_ability"] = self._asi_var.get().strip()
                self.state["spell_plan"] = self._compute_level_up_spell_plan()
            if steps[self._step_index] == "invocations":
                self._prepare_invocation_defaults()
            self._render_step()
            return
        self._finish()

    def _cancel(self):
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass
        try:
            self.popup.grab_release()
            self.popup.destroy()
        except tk.TclError:
            pass

    def _finish(self):
        result = copy.deepcopy(self.state)
        try:
            self.popup.grab_release()
            self.popup.destroy()
        except tk.TclError:
            pass
        if self.on_complete:
            self.on_complete(result)

    # --- Class step ---

    def _class_level_slots(self):
        slots = []
        for i, (cls_name, level) in enumerate(self.sheet._get_class_level_slots()):
            cls_name = str(cls_name or "None").strip() or "None"
            try:
                level = int(level or 0)
            except (TypeError, ValueError):
                level = 0
            slots.append((i, cls_name, level))
        return slots

    def _next_empty_class_slot(self):
        for slot_index, cls_name, _level in self._class_level_slots():
            if cls_name in (None, "", "None"):
                return slot_index
        return None

    def _get_new_class_options(self, slot_index):
        if slot_index is None:
            return []
        values = self.sheet._get_class_dropdown_values(slot_index)
        return [name for name in values if name not in (None, "", "None")]

    def _build_class_step(self):
        xp = self.sheet._get_current_xp()
        ecl, ecl_detail = self.sheet._format_ecl_breakdown()
        max_level = self.sheet._get_max_level_for_xp(xp)
        ctk.CTkLabel(
            self._content_frame,
            text=(
                f"Current XP: {xp:,}  |  Effective level: {ecl} ({ecl_detail})\n"
                f"Your XP supports up to ECL {max_level}. Choose which class gains a level."
            ),
            text_color="#aaaaaa",
            wraplength=WIZARD_WRAPLENGTH,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        primary = self._primary_color()
        hover = self._primary_hover()
        existing = [
            (slot_index, cls_name, level)
            for slot_index, cls_name, level in self._class_level_slots()
            if cls_name not in (None, "", "None")
        ]
        empty_slot = self._next_empty_class_slot()

        if not self._class_choice_var.get():
            if existing:
                first_key = f"slot:{existing[0][0]}"
                self._class_choice_var.set(first_key)
                self._select_class(
                    first_key,
                    existing[0][0],
                    existing[0][1],
                    existing[0][2] + 1,
                )

        if existing:
            ctk.CTkLabel(
                self._content_frame,
                text="Advance an existing class:",
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w",
            ).pack(anchor="w", pady=(0, 6))
            for slot_index, cls_name, level in existing:
                key = f"slot:{slot_index}"
                label = f"{cls_name}  (level {level} → {level + 1})"
                selected = self._class_choice_var.get() == key
                btn = ctk.CTkButton(
                    self._content_frame,
                    text=label,
                    anchor="w",
                    height=40,
                    fg_color=primary if selected else UNSELECTED_BTN,
                    hover_color=hover,
                    command=lambda k=key, si=slot_index, cn=cls_name, nl=level + 1: self._select_class(
                        k, si, cn, nl,
                    ),
                )
                btn.pack(fill="x", pady=4)
                self._class_buttons[key] = btn
        else:
            ctk.CTkLabel(
                self._content_frame,
                text="No classes yet. Add your first class below.",
                text_color="#aaaaaa",
                wraplength=WIZARD_WRAPLENGTH,
                justify="left",
            ).pack(anchor="w", pady=(0, 8))

        if empty_slot is not None:
            ctk.CTkButton(
                self._content_frame,
                text="+ Add New Class",
                anchor="w",
                height=36,
                fg_color=self._secondary_color(),
                hover_color="#1f8a82",
                command=self._show_add_class_panel,
            ).pack(fill="x", pady=(14, 4))

            choice = self._class_choice_var.get()
            show_panel = choice.startswith("new:") or not existing
            self._add_class_panel = ctk.CTkFrame(self._content_frame, fg_color="transparent")
            if show_panel:
                self._add_class_panel.pack(fill="x", pady=(6, 0))

            row = ctk.CTkFrame(self._add_class_panel, fg_color="transparent")
            row.pack(fill="x")
            ctk.CTkLabel(row, text="Class:", width=70, anchor="w").pack(side="left")
            values = self._get_new_class_options(empty_slot)
            if not values:
                values = list(WIZARD_CLASSES)
            current_pick = self._new_class_var.get().strip()
            if current_pick not in values:
                self._new_class_var.set(values[0] if values else "")
            combo = ctk.CTkComboBox(
                row, values=values, variable=self._new_class_var, width=260,
            )
            combo.pack(side="left", padx=(8, 0))
            ctk.CTkButton(
                row, text="Add", width=72,
                fg_color=primary, hover_color=hover,
                command=self._confirm_new_class,
            ).pack(side="left", padx=(10, 0))

            self._add_class_status_label = ctk.CTkLabel(
                self._add_class_panel, text="", text_color="#888888", anchor="w",
            )
            self._add_class_status_label.pack(anchor="w", pady=(6, 0))
            if choice.startswith("new:"):
                cls_name = self.state.get("class_name") or self._new_class_var.get()
                if cls_name:
                    self._add_class_status_label.configure(
                        text=f"Selected: {cls_name} will enter at level 1.",
                    )
        elif not existing:
            ctk.CTkLabel(
                self._content_frame,
                text="All class slots are full.",
                text_color="#d9534f",
            ).pack(anchor="w", pady=(8, 0))

    def _show_add_class_panel(self):
        if self._add_class_panel is not None:
            self._add_class_panel.pack(fill="x", pady=(6, 0))

    def _confirm_new_class(self):
        slot_index = self._next_empty_class_slot()
        if slot_index is None:
            messagebox.showwarning(
                "Class",
                "All class slots are already in use.",
                parent=self.popup,
            )
            return
        cls_name = self._new_class_var.get().strip()
        if not cls_name:
            messagebox.showwarning("Class", "Choose a class to add.", parent=self.popup)
            return
        self._select_new_class(slot_index, cls_name)

    def _select_new_class(self, slot_index, cls_name):
        key = f"new:{slot_index}"
        self._class_choice_var.set(key)
        self.state["slot_index"] = slot_index
        self.state["class_name"] = cls_name
        self.state["new_class_level"] = 1
        primary = self._primary_color()
        hover = self._primary_hover()
        for k, btn in self._class_buttons.items():
            btn.configure(fg_color=UNSELECTED_BTN, hover_color=hover)
        if self._add_class_status_label is not None:
            self._add_class_status_label.configure(
                text=f"Selected: {cls_name} will enter at level 1.",
            )
        self._show_add_class_panel()
        self._update_progression_milestones()

    def _select_class(self, key, slot_index, cls_name, new_level):
        self._class_choice_var.set(key)
        self.state["slot_index"] = slot_index
        self.state["class_name"] = cls_name
        self.state["new_class_level"] = new_level
        primary = self._primary_color()
        hover = self._primary_hover()
        for k, btn in self._class_buttons.items():
            btn.configure(
                fg_color=primary if k == key else UNSELECTED_BTN,
                hover_color=hover,
            )
        if self._add_class_status_label is not None:
            self._add_class_status_label.configure(text="")
        self._update_progression_milestones()

    def _resolve_class_selection(self):
        choice = self._class_choice_var.get()
        if not choice:
            return False
        if choice.startswith("slot:"):
            slot_index = int(choice.split(":")[1])
            for si, cls_name, level in self._class_level_slots():
                if si == slot_index and cls_name != "None":
                    self.state["slot_index"] = slot_index
                    self.state["class_name"] = cls_name
                    self.state["new_class_level"] = level + 1
                    self._update_progression_milestones()
                    return True
        if choice.startswith("new:"):
            slot_index = int(choice.split(":")[1])
            cls_name = self._new_class_var.get().strip()
            if not cls_name:
                return False
            self.state["slot_index"] = slot_index
            self.state["class_name"] = cls_name
            self.state["new_class_level"] = 1
            self._update_progression_milestones()
            return True
        return False

    def _update_progression_milestones(self):
        current_total = self.sheet._get_total_character_level()
        self.state["new_total_level"] = current_total + 1
        self.state["new_total_hd"] = self.sheet._get_total_hit_dice() + 1
        new_hd = self.state["new_total_hd"]

        self.state["asi_milestone"] = None
        self.state["feat_milestone"] = None
        self.state["general_feat_slot"] = None
        self.state["bonus_feat_key"] = ""
        self.state["bonus_feat_pool"] = ""

        asi_milestones = self.sheet._get_asi_milestones(new_hd)
        if new_hd in asi_milestones:
            existing = self.sheet.data.get("ability_score_improvements", {}).get(str(new_hd), "")
            if not str(existing or "").strip():
                self.state["asi_milestone"] = new_hd

        feat_milestones = self.sheet._get_general_feat_milestones(new_hd)
        if new_hd in feat_milestones:
            slot_index = self._feat_slot_index_for_milestone(new_hd)
            if slot_index is not None:
                existing = self.sheet._get_general_feat_slot_value(slot_index)
                if not str(existing or "").strip():
                    self.state["feat_milestone"] = new_hd
                    self.state["general_feat_slot"] = slot_index

        cls = self.state.get("class_name") or ""
        new_lvl = int(self.state.get("new_class_level") or 0)
        features = (getattr(self.sheet, "classes_db", {}) or {}).get(cls, {}).get("features", {})
        level_feats = features.get(str(new_lvl)) or []
        for feat in level_feats:
            if feat.get("is_bonus_feat"):
                key = f"{cls}_{new_lvl}_bonus"
                existing = (self.sheet.data.get("bonus_feats") or {}).get(key, "")
                if not str(existing or "").strip():
                    self.state["bonus_feat_key"] = key
                    self.state["bonus_feat_pool"] = feat.get("bonus_feat_pool", "")
                break

    def _feat_slot_index_for_milestone(self, milestone_hd):
        feat_levels = self.sheet._get_general_feat_milestones(milestone_hd)
        idx = 1 if self.sheet.data.get("race") == "Human" else 0
        for lvl in feat_levels:
            if lvl == milestone_hd:
                return idx
            idx += 1
        return None

    def _validate_class_step(self):
        if not self._resolve_class_selection():
            messagebox.showwarning("Class", "Select a class to advance.", parent=self.popup)
            return False
        new_ecl = self.sheet._get_effective_character_level() + 1
        if new_ecl > self.sheet._get_max_level_for_xp():
            messagebox.showwarning(
                "Not Enough XP",
                "You do not have enough XP to gain another level.",
                parent=self.popup,
            )
            return False
        return True

    # --- Progression step ---

    def _build_progression_step(self):
        cls = self.state.get("class_name") or "?"
        new_lvl = self.state.get("new_class_level") or "?"
        ctk.CTkLabel(
            self._content_frame,
            text=f"Advancing {cls} to level {new_lvl}.",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", pady=(0, 10))

        has_any = False
        if self.state.get("asi_milestone"):
            has_any = True
            row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
            row.pack(fill="x", pady=6)
            ctk.CTkLabel(
                row,
                text=f"Ability Score Improvement (HD {self.state['asi_milestone']}):",
                font=ctk.CTkFont(weight="bold"),
                width=320,
                anchor="w",
            ).pack(side="left")
            combo = ctk.CTkComboBox(
                row, values=[""] + list(ABILITY_NAMES),
                variable=self._asi_var, width=220,
            )
            combo.pack(side="left", padx=(8, 0))
            self._asi_preview_label = ctk.CTkLabel(
                row,
                text=self._asi_preview_text(self._asi_var.get().strip()),
                text_color="#aaaaaa",
                wraplength=WIZARD_WRAPLENGTH - 340,
                justify="left",
            )
            self._asi_preview_label.pack(side="left", padx=(12, 0))

            def _refresh_asi_preview(*_args):
                if getattr(self, "_asi_preview_label", None) is None:
                    return
                self._asi_preview_label.configure(
                    text=self._asi_preview_text(self._asi_var.get().strip()),
                )

            self._asi_var.trace_add("write", _refresh_asi_preview)

        if self.state.get("feat_milestone") is not None:
            has_any = True
            row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
            row.pack(fill="x", pady=6)
            ctk.CTkLabel(
                row,
                text=f"General Feat (HD {self.state['feat_milestone']}):",
                font=ctk.CTkFont(weight="bold"),
                width=320,
                anchor="w",
            ).pack(side="left")
            values = [""] + sorted((getattr(self.sheet, "feats_db", {}) or {}).keys())
            combo = ctk.CTkComboBox(row, values=values, variable=self._general_feat_var, width=280)
            combo.pack(side="left", padx=(8, 0))

        if self.state.get("bonus_feat_key"):
            has_any = True
            pool = self.state.get("bonus_feat_pool") or ""
            pool_label = f" ({pool})" if pool else ""
            row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
            row.pack(fill="x", pady=6)
            ctk.CTkLabel(
                row,
                text=f"Class Bonus Feat{pool_label}:",
                font=ctk.CTkFont(weight="bold"),
                width=320,
                anchor="w",
            ).pack(side="left")
            options = self.sheet._get_bonus_feat_options(pool)
            combo = ctk.CTkComboBox(
                row, values=[""] + options,
                variable=self._bonus_feat_var, width=280,
            )
            combo.pack(side="left", padx=(8, 0))

        if not has_any:
            ctk.CTkLabel(
                self._content_frame,
                text="No ability score increase or feats at this level. Press Next to continue.",
                text_color="#888888",
                wraplength=WIZARD_WRAPLENGTH,
            ).pack(anchor="w", pady=8)

    def _validate_progression_step(self):
        if self.state.get("asi_milestone") and not self._asi_var.get().strip():
            messagebox.showwarning(
                "Ability Score",
                "Choose an ability score to improve.",
                parent=self.popup,
            )
            return False
        if self.state.get("feat_milestone") is not None and not self._general_feat_var.get().strip():
            messagebox.showwarning("Feat", "Choose a general feat.", parent=self.popup)
            return False
        if self.state.get("bonus_feat_key") and not self._bonus_feat_var.get().strip():
            messagebox.showwarning("Bonus Feat", "Choose a class bonus feat.", parent=self.popup)
            return False
        self.state["asi_ability"] = self._asi_var.get().strip()
        self.state["general_feat"] = self._general_feat_var.get().strip()
        self.state["bonus_feat"] = self._bonus_feat_var.get().strip()
        return True

    def _pending_asi_ability(self):
        """Ability chosen for this level's +1 ASI (not yet committed until Finish)."""
        if not self.state.get("asi_milestone"):
            return ""
        ability = str(self.state.get("asi_ability") or self._asi_var.get() or "").strip()
        return ability if ability in ABILITY_NAMES else ""

    def _projected_ability_score(self, ability_name):
        """Live ability score including a pending +1 ASI when it targets this ability."""
        score = self.sheet._get_live_ability_score(ability_name)
        if ability_name == self._pending_asi_ability():
            score += 1
        return score

    def _projected_ability_mod(self, ability_name):
        return _ability_mod(self._projected_ability_score(ability_name))

    def _asi_projection_note(self, ability_name):
        """Short note when a pending ASI changes this ability (e.g. for skill/spell formulas)."""
        if ability_name != self._pending_asi_ability():
            return ""
        before = self.sheet._get_live_ability_score(ability_name)
        after = before + 1
        before_mod = _ability_mod(before)
        after_mod = _ability_mod(after)
        if before_mod == after_mod:
            return f"  ({ability_name} {before} → {after}; modifier stays {after_mod:+d} with ASI)"
        return (
            f"  ({ability_name} {before} → {after}; "
            f"modifier {before_mod:+d} → {after_mod:+d} including ASI)"
        )

    def _asi_preview_text(self, ability_name):
        if ability_name not in ABILITY_NAMES:
            return "Choose an ability to see the new score after your +1 improvement."
        before = self.sheet._get_live_ability_score(ability_name)
        after = before + 1
        before_mod = _ability_mod(before)
        after_mod = _ability_mod(after)
        mod_note = (
            f", modifier {before_mod:+d} → {after_mod:+d}"
            if before_mod != after_mod
            else f", modifier stays {after_mod:+d}"
        )
        return f"After ASI: {ability_name} {before} → {after}{mod_note}."

    # --- Health step ---

    def _class_hit_die_sides(self, cls_name):
        info = (getattr(self.sheet, "classes_db", {}) or {}).get(cls_name, {})
        return _parse_hit_die_sides(info.get("hit_die"))

    def _is_human_character(self):
        race = str(getattr(self.sheet, "data", {}).get("race", "") or "").strip()
        return race.casefold() == "human"

    def _human_skill_point_bonus(self):
        """Humans: +4 at 1st character level, +1 each level thereafter (3.5 SRD)."""
        if not self._is_human_character():
            return 0
        if self.sheet._get_total_character_level() == 0:
            return 4
        return 1

    def _human_skill_point_formula_note(self):
        bonus = self._human_skill_point_bonus()
        if bonus <= 0:
            return ""
        if bonus == 4:
            return " + 4 human (×4 at 1st level)"
        return " + 1 human"

    def _skill_points_formula_text(self):
        cls = self.state.get("class_name") or ""
        info = (getattr(self.sheet, "classes_db", {}) or {}).get(cls, {})
        class_sp = int(info.get("skill_points_per_level", 2) or 2)
        int_mod = self._projected_ability_mod("Intelligence")
        per_level = max(1, class_sp + int_mod)
        asi_note = self._asi_projection_note("Intelligence")
        human_note = self._human_skill_point_formula_note()
        current_total = self.sheet._get_total_character_level()
        if current_total == 0:
            total = per_level * 4 + self._human_skill_point_bonus()
            return (
                f"Skill points this level: ({class_sp} + Int mod {int_mod:+d}) × 4"
                f"{human_note} = {total}  "
                f"(first character level quadruples class skill points)"
                f"{asi_note}"
            )
        total = per_level + self._human_skill_point_bonus()
        return (
            f"Skill points this level: {class_sp} + Int mod ({int_mod:+d})"
            f"{human_note} = {total}"
            f"{asi_note}"
        )

    def _default_skill_points(self):
        cls = self.state.get("class_name") or ""
        info = (getattr(self.sheet, "classes_db", {}) or {}).get(cls, {})
        class_sp = int(info.get("skill_points_per_level", 2) or 2)
        int_mod = self._projected_ability_mod("Intelligence")
        per_level = max(1, class_sp + int_mod)
        human_bonus = self._human_skill_point_bonus()
        if self.sheet._get_total_character_level() == 0:
            return per_level * 4 + human_bonus
        return per_level + human_bonus

    def _prepare_health_defaults(self):
        self.state["asi_ability"] = self._asi_var.get().strip()
        sides = self._class_hit_die_sides(self.state.get("class_name"))
        if self.sheet._get_total_character_level() == 0 and sides:
            self._hp_var.set(str(sides))
        elif not self._hp_var.get().strip():
            self._hp_var.set("0")
        self.state.setdefault("skill_rank_additions", {})
        self._skill_var.set(str(self._default_skill_points()))

    def _projected_skill_cap_hd(self):
        return self.sheet._get_skill_level_for_caps() + 1

    def _wizard_skill_step(self, skill_key):
        cls = self.state.get("class_name") or ""
        return self.sheet._get_skill_rank_step(skill_key, leveling_class=cls)

    def _wizard_skill_base_rank(self, skill_key):
        return self.sheet._get_skill_rank_value(skill_key)

    def _wizard_skill_addition(self, skill_key):
        return float((self.state.get("skill_rank_additions") or {}).get(skill_key, 0) or 0)

    def _wizard_skill_display_rank(self, skill_key):
        return self._wizard_skill_base_rank(skill_key) + self._wizard_skill_addition(skill_key)

    def _wizard_max_skill_rank(self, skill_key):
        return float(
            self.sheet._get_max_skill_rank(skill_key, hd_level=self._projected_skill_cap_hd()),
        )

    def _wizard_skill_points_spent(self):
        spent = 0
        for skill_key, addition in (self.state.get("skill_rank_additions") or {}).items():
            addition = float(addition or 0)
            if addition <= 0:
                continue
            step = self._wizard_skill_step(skill_key)
            if step > 0:
                spent += int(round(addition / step))
        return spent

    def _update_wizard_skill_budget_display(self):
        if not self._skill_budget_label:
            return
        budget = self._default_skill_points()
        spent = self._wizard_skill_points_spent()
        remaining = budget - spent
        color = "#d9534f" if remaining < 0 else self._secondary_color()
        self._skill_budget_label.configure(
            text=f"Skill points remaining: {remaining}  (spent {spent} / {budget})",
            text_color=color,
        )

    def _refresh_wizard_skill_row(self, skill_key):
        rank_lbl = self._skill_rank_labels.get(skill_key)
        if rank_lbl:
            display = self.sheet._format_skill_rank_display(
                skill_key, self._wizard_skill_display_rank(skill_key),
            )
            try:
                rank_lbl.configure(text=display)
            except tk.TclError:
                pass
        minus_btn = self._skill_minus_buttons.get(skill_key)
        plus_btn = self._skill_plus_buttons.get(skill_key)
        addition = self._wizard_skill_addition(skill_key)
        step = self._wizard_skill_step(skill_key)
        budget = self._default_skill_points()
        spent = self._wizard_skill_points_spent()
        display_rank = self._wizard_skill_display_rank(skill_key)
        max_rank = self._wizard_max_skill_rank(skill_key)
        can_minus = addition >= step - 0.001
        can_plus = (
            spent < budget
            and display_rank + step <= max_rank + 0.001
        )
        for btn, enabled in ((minus_btn, can_minus), (plus_btn, can_plus)):
            if not btn:
                continue
            try:
                btn.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass

    def _adjust_wizard_skill_rank(self, skill_key, direction):
        """direction +1 spends one skill point; -1 refunds one."""
        step = self._wizard_skill_step(skill_key)
        additions = self.state.setdefault("skill_rank_additions", {})
        current = float(additions.get(skill_key, 0) or 0)
        if direction > 0:
            if self._wizard_skill_points_spent() >= self._default_skill_points():
                return
            if self._wizard_skill_display_rank(skill_key) + step > self._wizard_max_skill_rank(skill_key) + 0.001:
                return
            additions[skill_key] = round((current + step) * 2) / 2.0
        else:
            if current < step - 0.001:
                return
            new_addition = round((current - step) * 2) / 2.0
            if new_addition <= 0:
                additions.pop(skill_key, None)
            else:
                additions[skill_key] = new_addition
        self._update_wizard_skill_budget_display()
        self._refresh_wizard_skill_row(skill_key)

    def _build_wizard_skill_list(self):
        cls = self.state.get("class_name") or ""
        classes_db = getattr(self.sheet, "classes_db", {}) or {}
        ctk.CTkLabel(
            self._content_frame,
            text="Allocate skill ranks (+/− spends 1 skill point; cross-class skills gain 0.5 rank per point)",
            text_color="#aaaaaa",
            wraplength=WIZARD_WRAPLENGTH,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))
        self._skill_budget_label = ctk.CTkLabel(
            self._content_frame,
            text="",
            text_color=self._secondary_color(),
            font=ctk.CTkFont(weight="bold"),
        )
        self._skill_budget_label.pack(anchor="w", pady=(0, 6))

        scroll = ctk.CTkScrollableFrame(
            self._content_frame, height=200, fg_color=THEME_DARK_TRACK,
        )
        scroll.pack(fill="x", pady=(0, 8))

        for skill_key, ability_key, display_name in _iter_wizard_skill_rows(self.sheet):
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)
            is_class = _is_class_skill(skill_key, cls, classes_db)
            label = f"{display_name}*" if is_class else display_name
            ctk.CTkLabel(row, text=label, width=180, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=ability_key, width=36, anchor="center").pack(side="left", padx=(4, 8))

            minus_btn = ctk.CTkButton(
                row, text="−", width=28, height=26,
                fg_color="#444444",
                command=lambda key=skill_key: self._adjust_wizard_skill_rank(key, -1),
            )
            minus_btn.pack(side="left", padx=(0, 4))
            self._skill_minus_buttons[skill_key] = minus_btn

            rank_lbl = ctk.CTkLabel(
                row,
                text=self.sheet._format_skill_rank_display(
                    skill_key, self._wizard_skill_display_rank(skill_key),
                ),
                width=48,
                anchor="center",
            )
            rank_lbl.pack(side="left")
            self._skill_rank_labels[skill_key] = rank_lbl

            plus_btn = ctk.CTkButton(
                row, text="+", width=28, height=26,
                fg_color="#444444",
                command=lambda key=skill_key: self._adjust_wizard_skill_rank(key, 1),
            )
            plus_btn.pack(side="left", padx=(4, 0))
            self._skill_plus_buttons[skill_key] = plus_btn

            self._refresh_wizard_skill_row(skill_key)

        self._update_wizard_skill_budget_display()

    def _build_speak_language_step(self):
        needed = self._speak_language_ranks_added()
        known = set(self._level_up_known_languages())
        for lang in self.state.get("speak_language_choices") or []:
            known.discard(lang)
        options = speak_language_options(include_secret=False)
        subtitle = (
            f"You added {needed} rank{'s' if needed != 1 else ''} in Speak Language. "
            f"Choose {needed} new language{'s' if needed != 1 else ''} (any standard language). "
            "Languages you already know are greyed out."
        )
        self._speak_language_picker = build_language_picker(
            self._content_frame,
            title="Speak Language Choices",
            subtitle=subtitle,
            languages=options,
            known_languages=known,
            selected=list(self.state.get("speak_language_choices") or []),
            max_picks=needed,
            on_change=lambda picks: self.state.__setitem__("speak_language_choices", list(picks)),
            wraplength=WIZARD_WRAPLENGTH,
        )

    def _new_features_text(self):
        cls = self.state.get("class_name") or ""
        new_lvl = int(self.state.get("new_class_level") or 0)
        features = (getattr(self.sheet, "classes_db", {}) or {}).get(cls, {}).get("features", {})
        level_feats = features.get(str(new_lvl)) or []
        lines = []
        for feat in level_feats:
            name = feat.get("name", "Feature")
            desc = str(feat.get("description", "")).strip()
            if feat.get("is_bonus_feat"):
                name += " (bonus feat — choose above)"
            lines.append(f"• {name}")
            if desc:
                lines.append(f"  {desc[:200]}{'…' if len(desc) > 200 else ''}")
        if new_lvl == 1:
            class_langs = CLASS_LANGUAGE_GRANTS.get(cls)
            if class_langs:
                lines.append("• Languages granted: " + ", ".join(class_langs))
        return "\n".join(lines) if lines else "No new class features listed at this level."

    def _build_health_step(self):
        cls = self.state.get("class_name") or ""
        sides = self._class_hit_die_sides(cls)
        total_row = self.state.get("new_total_level") or (self.sheet._get_total_character_level() + 1)

        ctk.CTkLabel(
            self._content_frame,
            text=f"Character level after advancement: {total_row}",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", pady=(0, 8))

        hp_row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        hp_row.pack(fill="x", pady=6)
        ctk.CTkLabel(hp_row, text="Hit Die roll:", width=120, anchor="w").pack(side="left")
        ctk.CTkEntry(hp_row, textvariable=self._hp_var, width=72).pack(side="left", padx=(4, 8))
        if sides:
            dice_row = ctk.CTkFrame(hp_row, fg_color="transparent")
            dice_row.pack(side="left")
            for die in (4, 6, 8, 10, 12):
                if die != sides:
                    continue
                ctk.CTkButton(
                    dice_row, text=f"Roll d{die}", width=72, height=26,
                    fg_color="#444444",
                    command=lambda d=die: self._roll_hp(d),
                ).pack(side="left", padx=2)
            note = (
                f"Class HD: d{sides}."
                + (" First character level uses maximum HD." if self.sheet._get_total_character_level() == 0 else "")
            )
            ctk.CTkLabel(hp_row, text=note, text_color="#888888").pack(side="left", padx=(12, 0))

        sp_row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        sp_row.pack(fill="x", pady=6)
        ctk.CTkLabel(sp_row, text="Skill points:", width=120, anchor="w").pack(side="left")
        ctk.CTkLabel(
            sp_row,
            textvariable=self._skill_var,
            width=72,
            anchor="w",
        ).pack(side="left", padx=(4, 8))
        ctk.CTkLabel(
            self._content_frame,
            text=self._skill_points_formula_text(),
            text_color="#aaaaaa",
            wraplength=WIZARD_WRAPLENGTH,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        self._build_wizard_skill_list()

        feat_box = ctk.CTkFrame(self._content_frame, fg_color=THEME_DARK_TRACK)
        feat_box.pack(fill="both", expand=True, pady=(4, 0))
        ctk.CTkLabel(
            feat_box, text="New class features",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self._primary_color(),
        ).pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            feat_box,
            text=self._new_features_text(),
            justify="left",
            wraplength=WIZARD_WRAPLENGTH - 40,
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(0, 12))

        plan = self._compute_level_up_spell_plan()
        if plan and plan.get("divine_note"):
            ctk.CTkLabel(
                self._content_frame,
                text=plan["divine_note"],
                text_color=THEME_TEAL,
                wraplength=WIZARD_WRAPLENGTH,
                justify="left",
            ).pack(anchor="w", pady=(10, 0))

    def _roll_hp(self, sides):
        if self.sheet._get_total_character_level() == 0:
            self._hp_var.set(str(sides))
            return
        roll = random.randint(1, sides)
        self._hp_var.set(str(roll))

    def _validate_health_step(self):
        try:
            hp = int(self._hp_var.get().strip() or 0)
        except ValueError:
            messagebox.showwarning("Hit Points", "Enter a valid hit die roll.", parent=self.popup)
            return False
        if hp <= 0:
            messagebox.showwarning("Hit Points", "Hit die roll must be greater than 0.", parent=self.popup)
            return False
        sp = self._default_skill_points()
        if sp <= 0:
            messagebox.showwarning("Skill Points", "Skill points must be greater than 0.", parent=self.popup)
            return False
        spent = self._wizard_skill_points_spent()
        if spent > sp:
            messagebox.showwarning(
                "Skill Points",
                f"You spent {spent} skill points but only have {sp} this level.",
                parent=self.popup,
            )
            return False
        self.state["hp_roll"] = hp
        self.state["skill_points"] = sp
        return True

    # --- Spells step ---

    def _needs_spell_step(self):
        if not self.state.get("class_name"):
            return False
        plan = self._compute_level_up_spell_plan()
        return bool(plan and (plan.get("pick_known") or plan.get("wizard_pick_count")))

    def _compute_level_up_spell_plan(self):
        cls = self.state.get("class_name") or ""
        new_lvl = int(self.state.get("new_class_level") or 0)
        old_lvl = max(0, new_lvl - 1)
        info = (getattr(self.sheet, "classes_db", {}) or {}).get(cls, {})
        sc = info.get("spellcasting") or {}
        if not sc or sc.get("advancement"):
            return None

        if cls in DIVINE_PREPARED_CASTERS:
            old_max = 0
            new_max = 0
            if hasattr(self.sheet, "_get_class_level_max_spell_level"):
                if old_lvl > 0:
                    old_max = self.sheet._get_class_level_max_spell_level(cls, old_lvl)
                new_max = self.sheet._get_class_level_max_spell_level(cls, new_lvl)
            if new_max > old_max:
                return {
                    "mode": "divine",
                    "pick_known": {},
                    "divine_note": (
                        f"As a {cls}, all spells on your class list up to level {new_max} are "
                        "available when you Pray for Spells. They are not added to Spells Known "
                        "to keep your list manageable."
                    ),
                }
            return None

        if cls == "Wizard":
            max_lvl = self.sheet._get_class_level_max_spell_level(cls, new_lvl)
            if new_lvl == 1:
                int_mod = self._projected_ability_mod("Intelligence")
                book_lvl1 = max(1, 3 + int_mod)
                asi_note = self._asi_projection_note("Intelligence")
                return {
                    "mode": "wizard_first",
                    "pick_known": {1: book_lvl1},
                    "auto_known_level": 0,
                    "max_cast_level": max_lvl,
                    "advice": (
                        "All 0-level wizard spells are added to your spellbook automatically. "
                        f"Choose {book_lvl1} first-level spell{'s' if book_lvl1 != 1 else ''} "
                        f"for your spellbook (3 + Int modifier {int_mod:+d})."
                        f"{asi_note}"
                    ),
                }
            return {
                "mode": "wizard",
                "wizard_pick_count": 2,
                "max_cast_level": max_lvl,
                "pick_known": {},
                "advice": (
                    f"Choose 2 wizard spells of any level you can cast (0–{max_lvl}) "
                    "to add to your spellbook."
                ),
            }

        if cls in SPONTANEOUS_CASTERS or sc.get("casting_style") == "spontaneous":
            table = (sc.get("spells_known") or {})
            old_row = [int(x) for x in (table.get(str(old_lvl)) or [])]
            new_row = [int(x) for x in (table.get(str(new_lvl)) or [])]
            pick_known = {}
            for i in range(max(len(old_row), len(new_row))):
                old_c = old_row[i] if i < len(old_row) else 0
                new_c = new_row[i] if i < len(new_row) else 0
                delta = new_c - old_c
                if delta > 0:
                    pick_known[i] = delta
            if not pick_known:
                return None
            parts = [
                f"{count} level-{lvl}" for lvl, count in sorted(pick_known.items())
            ]
            return {
                "mode": "spontaneous",
                "pick_known": pick_known,
                "advice": f"Choose {' and '.join(parts)} new spell(s) for your repertoire.",
            }

        return None

    def _spell_level_label(self, level):
        return "Cantrips (0)" if level == 0 else f"Level {level}"

    def _spell_level_for_class(self, spell_name, class_name):
        info = (getattr(self.sheet, "spells_db", {}) or {}).get(spell_name, {})
        if hasattr(self.sheet, "_get_spell_level_for_class"):
            return self.sheet._get_spell_level_for_class(info, class_name)
        return int(info.get("level", 0) or 0)

    def _get_class_spells_for_level(self, class_name, spell_level, *, max_level=None):
        class_key = class_name.lower()
        indexed = list(
            getattr(self.sheet, "_spells_by_class_level", {}).get((class_key, spell_level), []),
        )
        if indexed:
            spells = indexed
        else:
            spells_db = getattr(self.sheet, "spells_db", {}) or {}
            get_level = getattr(self.sheet, "_get_spell_level_for_class", None)
            get_classes = getattr(self.sheet, "_get_spell_classes", None)
            spells = []
            for spell_name, info in spells_db.items():
                level = get_level(info, class_name) if get_level else int(info.get("level", 0) or 0)
                if level != spell_level:
                    continue
                if max_level is not None and level > max_level:
                    continue
                if get_classes:
                    if class_name not in get_classes(info):
                        continue
                elif class_name not in (info.get("classes") or []):
                    continue
                spells.append((spell_name, info))
            spells = sorted(spells, key=lambda item: item[0].lower())
        if max_level is not None and spell_level > max_level:
            return []
        return spells

    def _build_spells_step(self):
        plan = self.state.get("spell_plan") or self._compute_level_up_spell_plan() or {}
        self.state["spell_plan"] = plan
        cls = self.state.get("class_name") or ""

        ctk.CTkLabel(
            self._content_frame,
            text=plan.get("advice", "Choose new spells."),
            text_color="#aaaaaa",
            wraplength=WIZARD_WRAPLENGTH,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        self._spell_status_label = ctk.CTkLabel(
            self._content_frame, text="",
            text_color=self._secondary_color(),
            font=ctk.CTkFont(weight="bold"),
        )
        self._spell_status_label.pack(anchor="w", pady=(0, 6))

        search_row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        search_row.pack(fill="x", pady=(0, 4))
        ctk.CTkEntry(
            search_row, textvariable=self._spell_search_var, width=360,
            placeholder_text="Filter spells...",
        ).pack(side="left")
        self._spell_search_var.trace_add("write", lambda *_a: self._refresh_spell_list())
        ctk.CTkButton(
            search_row,
            text="Browse Spell Database",
            fg_color=self._secondary_color(),
            hover_color=getattr(self.sheet, "secondary_hover_color", "#1f7f75"),
            command=self._open_spell_database_popup,
        ).pack(side="left", padx=(10, 0))

        level_row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        level_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(level_row, text="Spell level:", width=90, anchor="w").pack(side="left")

        if plan.get("mode") == "wizard":
            max_lvl = int(plan.get("max_cast_level", 0) or 0)
            levels = list(range(0, max_lvl + 1))
        else:
            levels = sorted(plan.get("pick_known", {}).keys())

        primary = self._primary_color()
        hover = self._primary_hover()

        def select_level(level):
            self._active_spell_level = level
            for lv, btn in self._spell_level_buttons.items():
                btn.configure(
                    fg_color=primary if lv == level else UNSELECTED_BTN,
                    hover_color=hover,
                )
            self._refresh_spell_list()

        for level in levels:
            btn = ctk.CTkButton(
                level_row, text=self._spell_level_label(level), width=100, height=28,
                fg_color=UNSELECTED_BTN,
                command=lambda lv=level: select_level(lv),
            )
            btn.pack(side="left", padx=3)
            self._spell_level_buttons[level] = btn

        if levels:
            self._active_spell_level = levels[0]
            select_level(levels[0])

        if plan.get("auto_known_level") is not None:
            cantrip_count = len(self._get_class_spells_for_level(cls, plan["auto_known_level"]))
            ctk.CTkLabel(
                self._content_frame,
                text=f"Spellbook: all {cantrip_count} wizard cantrips will be added automatically.",
                text_color="#888888",
            ).pack(anchor="w", pady=(0, 4))

        self._spell_list_frame = ctk.CTkScrollableFrame(
            self._content_frame, height=320, fg_color=THEME_DARK_TRACK,
        )
        self._spell_list_frame.pack(fill="both", expand=True, pady=(4, 0))

    def _wizard_spells_picked(self):
        cls = self.state.get("class_name") or ""
        max_lvl = int((self.state.get("spell_plan") or {}).get("max_cast_level", 9) or 9)
        picked = []
        for name in self.state.get("spells_to_add") or []:
            lvl = self._spell_level_for_class(name, cls)
            if lvl <= max_lvl:
                picked.append(name)
        return picked

    def _spells_at_level(self, spell_level):
        cls = self.state.get("class_name") or ""
        return [
            s for s in self.state.get("spells_to_add") or []
            if self._spell_level_for_class(s, cls) == spell_level
        ]

    def _refresh_spell_list(self):
        if self._spell_list_frame is None:
            return
        for w in self._spell_list_frame.winfo_children():
            w.destroy()

        plan = self.state.get("spell_plan") or {}
        cls = self.state.get("class_name") or ""
        level = self._active_spell_level
        search = self._spell_search_var.get().strip().lower()
        primary = self._primary_color()
        hover = self._primary_hover()

        if plan.get("mode") == "wizard":
            limit_total = int(plan.get("wizard_pick_count", 2) or 2)
            picked = self._wizard_spells_picked()
            limit = limit_total
            selected_at_level = [s for s in picked if self._spell_level_for_class(s, cls) == level]
            self._spell_status_label.configure(
                text=f"Spellbook: {len(picked)} / {limit_total} chosen (any castable level)",
            )
            max_lvl = int(plan.get("max_cast_level", 0) or 0)
            spells = self._get_class_spells_for_level(cls, level, max_level=max_lvl)
        else:
            limit = int(plan.get("pick_known", {}).get(level, 0) or 0)
            selected_at_level = self._spells_at_level(level)
            self._spell_status_label.configure(
                text=f"{self._spell_level_label(level)}: {len(selected_at_level)} / {limit}",
            )
            spells = self._get_class_spells_for_level(cls, level)

        if search:
            spells = [
                (name, info) for name, info in spells
                if search in name.lower() or search in str(info.get("description", "")).lower()
            ]

        if not spells and limit <= 0 and plan.get("mode") != "wizard":
            ctk.CTkLabel(
                self._spell_list_frame,
                text="No new spells to choose at this spell level.",
                text_color="#888888",
            ).pack(pady=16, padx=12, anchor="w")
            return

        for spell_name, info in spells[:180]:
            is_selected = spell_name in (self.state.get("spells_to_add") or [])
            desc = str(info.get("description", ""))[:90]
            btn = ctk.CTkButton(
                self._spell_list_frame,
                text=f"{spell_name}\n{desc}",
                anchor="w", height=38,
                fg_color=primary if is_selected else UNSELECTED_BTN,
                hover_color=hover,
                command=lambda n=spell_name, lv=level: self._toggle_spell(n, lv),
            )
            btn.pack(fill="x", padx=6, pady=2)

    def _toggle_spell(self, spell_name, spell_level):
        plan = self.state.get("spell_plan") or {}
        cls = self.state.get("class_name") or ""
        spells = list(self.state.get("spells_to_add") or [])

        if spell_name in spells:
            spells.remove(spell_name)
        else:
            if plan.get("mode") == "wizard":
                max_lvl = int(plan.get("max_cast_level", 0) or 0)
                if self._spell_level_for_class(spell_name, cls) > max_lvl:
                    return
                if len(self._wizard_spells_picked()) >= int(plan.get("wizard_pick_count", 2) or 2):
                    messagebox.showwarning(
                        "Spells",
                        "You can only add 2 wizard spells per level gained.",
                        parent=self.popup,
                    )
                    return
            else:
                limit = int(plan.get("pick_known", {}).get(spell_level, 0) or 0)
                at_level = self._spells_at_level(spell_level)
                if len(at_level) >= limit:
                    messagebox.showwarning(
                        "Spells",
                        f"You can only add {limit} spell(s) at {self._spell_level_label(spell_level)}.",
                        parent=self.popup,
                    )
                    return
            spells.append(spell_name)

        self.state["spells_to_add"] = sorted(spells, key=str.lower)
        self._refresh_spell_list()

    def _open_spell_database_popup(self):
        if self._spell_db_popup is not None:
            try:
                self._spell_db_popup.lift()
                return
            except tk.TclError:
                self._spell_db_popup = None

        plan = self.state.get("spell_plan") or {}
        cls = self.state.get("class_name") or ""
        popup = ctk.CTkToplevel(self.popup)
        popup.title("Spell Database")
        popup.geometry("760x560")
        popup.grab_set()
        self._spell_db_popup = popup

        search_var = tk.StringVar()
        ctk.CTkEntry(popup, textvariable=search_var, width=400, placeholder_text="Search...").pack(
            padx=16, pady=12, anchor="w",
        )
        scroll = ctk.CTkScrollableFrame(popup, height=420)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        def refresh():
            for w in scroll.winfo_children():
                w.destroy()
            q = search_var.get().strip().lower()
            if plan.get("mode") == "wizard":
                max_lvl = int(plan.get("max_cast_level", 0) or 0)
                pool = []
                for lvl in range(0, max_lvl + 1):
                    pool.extend(self._get_class_spells_for_level(cls, lvl, max_level=max_lvl))
            else:
                pool = []
                for lvl in plan.get("pick_known", {}):
                    pool.extend(self._get_class_spells_for_level(cls, lvl))
            seen = set()
            for spell_name, info in pool:
                if spell_name in seen:
                    continue
                seen.add(spell_name)
                if q and q not in spell_name.lower() and q not in str(info.get("description", "")).lower():
                    continue
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=spell_name, width=280, anchor="w").pack(side="left", padx=4)
                ctk.CTkButton(
                    row, text="Add", width=70,
                    command=lambda n=spell_name: (self._toggle_spell(n, self._spell_level_for_class(n, cls)), refresh()),
                ).pack(side="right", padx=4)

        search_var.trace_add("write", lambda *_a: refresh())
        refresh()
        popup.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "_spell_db_popup", None), popup.destroy()))

    def _validate_spells_step(self):
        plan = self.state.get("spell_plan") or {}
        cls = self.state.get("class_name") or ""
        if plan.get("mode") == "wizard":
            picked = self._wizard_spells_picked()
            need = int(plan.get("wizard_pick_count", 2) or 2)
            if len(picked) < need:
                messagebox.showwarning(
                    "Spells",
                    f"Choose {need} wizard spells to add to your spellbook.",
                    parent=self.popup,
                )
                return False
            return True
        for level, needed in (plan.get("pick_known") or {}).items():
            count = len(self._spells_at_level(level))
            if count < needed:
                messagebox.showwarning(
                    "Spells",
                    f"Choose {needed} spell(s) at {self._spell_level_label(level)}.",
                    parent=self.popup,
                )
                return False
        return True

    def _validate_speak_language_step(self):
        needed = self._speak_language_ranks_added()
        picks = list(self.state.get("speak_language_choices") or [])
        if self._speak_language_picker:
            picks = self._speak_language_picker["get_selected"]()
            self.state["speak_language_choices"] = picks
        if needed > 0 and len(picks) != needed:
            messagebox.showwarning(
                "Speak Language",
                f"Select exactly {needed} language{'s' if needed != 1 else ''} "
                f"({len(picks)} selected).",
                parent=self.popup,
            )
            return False
        return True

    def _needs_invocation_step(self):
        if self.state.get("class_name") != "Warlock" or not _warlock_support:
            return False
        new_lvl = int(self.state.get("new_class_level") or 0)
        old_lvl = max(0, new_lvl - 1)
        classes_db = getattr(self.sheet, "classes_db", {}) or {}
        gain = _warlock_support.compute_level_up_invocation_gain(
            old_lvl, new_lvl, classes_db=classes_db,
        )
        self.state["invocation_pick_count"] = gain
        return gain > 0

    def _prepare_invocation_defaults(self):
        if not _warlock_support:
            return
        new_lvl = int(self.state.get("new_class_level") or 0)
        old_lvl = max(0, new_lvl - 1)
        classes_db = getattr(self.sheet, "classes_db", {}) or {}
        self.state["invocation_pick_count"] = _warlock_support.compute_level_up_invocation_gain(
            old_lvl, new_lvl, classes_db=classes_db,
        )

    def _projected_warlock_known_invocations(self):
        known = list(getattr(self.sheet, "_get_known_invocations", lambda: [])() or [])
        known.extend(self.state.get("invocations_to_add") or [])
        return known

    def _available_level_up_invocations(self):
        if not _warlock_support:
            return []
        new_lvl = int(self.state.get("new_class_level") or 0)
        return _warlock_support.list_available_invocations(
            getattr(self.sheet, "invocations_db", {}) or {},
            new_lvl,
            self._projected_warlock_known_invocations(),
        )

    def _build_invocations_step(self):
        pick_count = int(self.state.get("invocation_pick_count") or 0)
        picked = list(self.state.get("invocations_to_add") or [])
        ctk.CTkLabel(
            self._content_frame,
            text=(
                f"Choose {pick_count} new warlock invocation{'s' if pick_count != 1 else ''}. "
                "Only invocations you qualify for are listed."
            ),
            text_color="#aaaaaa",
            wraplength=WIZARD_WRAPLENGTH,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        if picked:
            ctk.CTkLabel(
                self._content_frame,
                text="Selected: " + ", ".join(picked),
                text_color=THEME_TEAL,
                wraplength=WIZARD_WRAPLENGTH,
                justify="left",
            ).pack(anchor="w", pady=(0, 8))

        options = [""] + self._available_level_up_invocations()
        row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        combo = ctk.CTkComboBox(row, values=options, width=320)
        combo.set("")
        combo.pack(side="left", padx=(0, 8))

        def _add_invocation():
            name = combo.get().strip()
            if not name:
                return
            if name in picked:
                return
            if len(picked) >= pick_count:
                messagebox.showwarning(
                    "Invocation Limit",
                    f"You may only choose {pick_count} invocation(s) this level.",
                    parent=self.popup,
                )
                return
            picked.append(name)
            self.state["invocations_to_add"] = picked
            self._render_step()

        def _remove_last():
            if picked:
                picked.pop()
                self.state["invocations_to_add"] = picked
                self._render_step()

        ctk.CTkButton(row, text="Add", width=80, fg_color=THEME_TEAL, command=_add_invocation).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Remove Last", width=110, fg_color="#666666", command=_remove_last).pack(side="left")

        list_frame = ctk.CTkScrollableFrame(self._content_frame, height=280, fg_color=THEME_DARK_TRACK)
        list_frame.pack(fill="both", expand=True, pady=(8, 0))
        for name in self._available_level_up_invocations():
            info = (getattr(self.sheet, "invocations_db", {}) or {}).get(name, {})
            grade = info.get("grade", "")
            ctk.CTkLabel(
                list_frame,
                text=f"{name} ({grade}) — {info.get('description', '')[:120]}",
                wraplength=WIZARD_WRAPLENGTH - 40,
                justify="left",
                anchor="w",
            ).pack(anchor="w", padx=10, pady=4)

    def _validate_invocations_step(self):
        pick_count = int(self.state.get("invocation_pick_count") or 0)
        picked = list(self.state.get("invocations_to_add") or [])
        if len(picked) < pick_count:
            messagebox.showwarning(
                "Invocations",
                f"Choose {pick_count} invocation(s) before continuing.",
                parent=self.popup,
            )
            return False
        return True

    def _validate_current_step(self):
        step = self._current_step()
        validators = {
            "class": self._validate_class_step,
            "progression": self._validate_progression_step,
            "health": self._validate_health_step,
            "speak_language": self._validate_speak_language_step,
            "spells": self._validate_spells_step,
            "invocations": self._validate_invocations_step,
        }
        return validators[step]()


def _grant_class_spells_at_level(sheet, class_name, spell_level, known, known_set):
    """Add every spell of spell_level for class_name into known (in-place)."""
    class_key = class_name.lower()
    indexed = list(
        getattr(sheet, "_spells_by_class_level", {}).get((class_key, spell_level), []),
    )
    if indexed:
        spell_names = [name for name, _info in indexed]
    else:
        spells_db = getattr(sheet, "spells_db", {}) or {}
        get_level = getattr(sheet, "_get_spell_level_for_class", None)
        get_classes = getattr(sheet, "_get_spell_classes", None)
        spell_names = []
        for spell_name, info in spells_db.items():
            level = get_level(info, class_name) if get_level else int(info.get("level", 0) or 0)
            if level != spell_level:
                continue
            if get_classes:
                if class_name not in get_classes(info):
                    continue
            elif class_name not in (info.get("classes") or []):
                continue
            spell_names.append(spell_name)
    for spell_name in sorted(spell_names, key=str.lower):
        if spell_name and spell_name not in known_set:
            known.append(spell_name)
            known_set.add(spell_name)


def apply_level_up_to_sheet(sheet, result):
    """Apply a completed level-up wizard result to the character sheet."""
    slot_index = int(result.get("slot_index", 0) or 0)
    cls_name = str(result.get("class_name") or "").strip()
    if not cls_name:
        return False

    classes = list(sheet.data.get("classes") or ["None", "None", "None"])
    levels = list(sheet.data.get("levels") or [0, 0, 0])
    while len(classes) < 3:
        classes.append("None")
    while len(levels) < 3:
        levels.append(0)

    classes[slot_index] = cls_name
    levels[slot_index] = int(result.get("new_class_level") or (int(levels[slot_index] or 0) + 1))
    sheet.data["classes"] = classes[:3]
    sheet.data["levels"] = levels[:3]
    for i in range(3):
        sheet.data[f"class_{i}"] = classes[i]
        sheet.data[f"level_{i}"] = str(levels[i])

    if sheet._class_ui_ready():
        try:
            sheet.class_vars[slot_index].set(classes[slot_index])
            sheet.level_vars[slot_index].set(str(levels[slot_index]))
        except (tk.TclError, IndexError, AttributeError):
            pass
        if hasattr(sheet, "_refresh_class_level_display"):
            sheet._refresh_class_level_display()

    health = sheet.data.setdefault("health", {})
    rolls = list(health.get("hit_dice_rolls", []))
    skill_pts = list(health.get("skill_points_per_level", []))
    hp_roll = int(result.get("hp_roll") or 0)
    sp = int(result.get("skill_points") or 0)
    level_index = sum(int(l or 0) for l in levels) - 1
    if level_index < 0:
        level_index = 0
    while len(rolls) <= level_index:
        rolls.append(0)
    while len(skill_pts) <= level_index:
        skill_pts.append(0)
    rolls[level_index] = sheet._effective_hit_die_roll_value(level_index, hp_roll)
    skill_pts[level_index] = sp
    health["hit_dice_rolls"] = rolls
    health["skill_points_per_level"] = skill_pts

    additions = result.get("skill_rank_additions") or {}
    touched_skills = []
    for skill_key, addition in additions.items():
        addition = float(addition or 0)
        if addition <= 0:
            continue
        old_rank = sheet._get_skill_rank_value(skill_key)
        new_rank = old_rank + addition
        capped = sheet._set_skill_rank_value(skill_key, new_rank, refresh=False)
        sheet._update_skill_rank_cost_for_change(
            skill_key, old_rank, capped, leveling_class=cls_name,
        )
        touched_skills.append(skill_key)
    for skill_key in touched_skills:
        if hasattr(sheet, "skill_vars") and skill_key in sheet.skill_vars:
            sheet.recalc_skill(skill_key)

    speak_choices = [
        str(lang).strip()
        for lang in (result.get("speak_language_choices") or [])
        if str(lang).strip()
    ]
    if speak_choices:
        existing = list(sheet.data.get("speak_language_languages") or [])
        for lang in speak_choices:
            if lang not in existing:
                existing.append(lang)
        sheet.data["speak_language_languages"] = existing

    milestone = result.get("asi_milestone")
    ability = str(result.get("asi_ability") or "").strip()
    if milestone and ability:
        sheet.data.setdefault("ability_score_improvements", {})[str(milestone)] = ability

    feat_slot = result.get("general_feat_slot")
    general_feat = str(result.get("general_feat") or "").strip()
    if feat_slot is not None and general_feat:
        sheet._save_general_feat(int(feat_slot), general_feat)

    bonus_key = str(result.get("bonus_feat_key") or "").strip()
    bonus_feat = str(result.get("bonus_feat") or "").strip()
    if bonus_key and bonus_feat:
        sheet.save_bonus_feat(bonus_key, bonus_feat)

    known = list(sheet.data.get("known_spells") or [])
    known_set = set(known)
    spell_plan = result.get("spell_plan") or {}
    auto_level = spell_plan.get("auto_known_level")
    if auto_level is not None and cls_name == "Wizard":
        _grant_class_spells_at_level(sheet, cls_name, int(auto_level), known, known_set)
    for spell_name in result.get("spells_to_add") or []:
        if spell_name and spell_name not in known_set:
            known.append(spell_name)
            known_set.add(spell_name)
    sheet.data["known_spells"] = sorted(known, key=str.lower)

    if cls_name == "Warlock" and _warlock_support:
        current = _warlock_support.get_known_invocations(sheet.data)
        for name in result.get("invocations_to_add") or []:
            name = str(name).strip()
            if name and name not in current:
                current.append(name)
        _warlock_support.set_known_invocations(sheet.data, current)
        if hasattr(sheet, "_sync_warlock_invocation_prepared_spells"):
            sheet._sync_warlock_invocation_prepared_spells()

    sheet.invalidate_caches()
    sheet.refresh_level_up_button()
    sheet.refresh_health_display()
    if hasattr(sheet, "refresh_spells_page"):
        sheet.refresh_spells_page()
    sheet.refresh_feats_scope("class_tabs", "general")
    sheet.refresh_all()
    sheet._schedule_priority_cloud_push(delay_ms=500)
    return True