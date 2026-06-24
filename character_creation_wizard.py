"""Multi-step character creation wizard for D&D Beside."""

from __future__ import annotations

import copy
import random
import re
import tkinter as tk
import uuid
import dark_dialog as messagebox

import customtkinter as ctk

from languages import (
    CLASS_LANGUAGE_GRANTS,
    SPEAK_LANGUAGE_SKILL,
    bonus_language_options,
    build_language_picker,
    collect_character_languages,
    int_bonus_language_count,
    racial_automatic_languages,
    speak_language_options,
)

try:
    import warlock_support as _warlock_support
except ImportError:
    _warlock_support = None

THEME_DARK_BG = "#1a1a1a"
THEME_DARK_TRACK = "#2F2F2F"
THEME_ORANGE = "#c77626"
THEME_TEAL = "#28a99e"
UNSELECTED_BTN = "#3a3a3a"
SELECTED_TEXT = "#ffffff"

ALL_ALIGNMENTS = (
    "Lawful Good", "Neutral Good", "Chaotic Good",
    "Lawful Neutral", "True Neutral", "Chaotic Neutral",
    "Lawful Evil", "Neutral Evil", "Chaotic Evil",
)
ALIGNMENT_RESTRICTED_FG = "#555555"
ALIGNMENT_RESTRICTED_TEXT = "#888888"

ABILITY_NAMES = ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma")
ABILITY_SHORT = {
    "Strength": "Str", "Dexterity": "Dex", "Constitution": "Con",
    "Intelligence": "Int", "Wisdom": "Wis", "Charisma": "Cha",
}
ABILITY_RACE_KEYS = {
    "Strength": "str", "Dexterity": "dex", "Constitution": "con",
    "Intelligence": "int", "Wisdom": "wis", "Charisma": "cha",
}

SRD_WIZARD_CLASSES = (
    "Barbarian", "Bard", "Cleric", "Druid", "Fighter",
    "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard",
)
WIZARD_CLASSES = SRD_WIZARD_CLASSES

HALF_CASTER_CLASSES = {"Paladin", "Ranger"}
SPONTANEOUS_CASTERS = {"Sorcerer", "Bard"}

STARTING_GOLD = {
    "Barbarian": {"dice": 4, "sides": 4, "multiplier": 10, "label": "4d4 × 10 gp"},
    "Bard": {"dice": 4, "sides": 4, "multiplier": 10, "label": "4d4 × 10 gp"},
    "Cleric": {"dice": 4, "sides": 4, "multiplier": 10, "label": "4d4 × 10 gp"},
    "Druid": {"dice": 2, "sides": 4, "multiplier": 10, "label": "2d4 × 10 gp"},
    "Fighter": {"dice": 5, "sides": 4, "multiplier": 10, "label": "5d4 × 10 gp"},
    "Monk": {"dice": 5, "sides": 4, "multiplier": 1, "label": "5d4 gp"},
    "Paladin": {"dice": 6, "sides": 4, "multiplier": 10, "label": "6d4 × 10 gp"},
    "Ranger": {"dice": 6, "sides": 4, "multiplier": 10, "label": "6d4 × 10 gp"},
    "Rogue": {"dice": 5, "sides": 4, "multiplier": 10, "label": "5d4 × 10 gp"},
    "Sorcerer": {"dice": 3, "sides": 4, "multiplier": 10, "label": "3d4 × 10 gp"},
    "Wizard": {"dice": 3, "sides": 4, "multiplier": 10, "label": "3d4 × 10 gp"},
    "Warlock": {"dice": 3, "sides": 4, "multiplier": 10, "label": "3d4 × 10 gp"},
}

AUTO_CASTER_GEAR = ("Spell component pouch",)
AUTO_CLERIC_GEAR = ("Holy symbol, wooden",)
AUTO_WIZARD_GEAR = ("Spellbook, wizard\u2019s (blank)",)
AUTO_BARD_GEAR = ("Musical instrument, common",)

BASE_STEPS = ("class", "race", "identity", "abilities", "feats", "skills", "languages")
EQUIP_STEPS = ("equip_weapons", "equip_armor", "equip_gear")

WIZARD_WIDTH = 1000
WIZARD_HEIGHT = 650
WIZARD_WRAPLENGTH = 920

POINT_BUY_POOL = 27
POINT_BUY_MIN_SCORE = 8
POINT_BUY_MAX_SCORE = 18
POINT_BUY_COST = {
    8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 6, 15: 8, 16: 10, 17: 13, 18: 16,
}
STANDARD_ABILITY_ARRAY = [15, 14, 13, 12, 10, 8]


def _parse_hit_die_sides(hit_die):
    text = str(hit_die or "").strip().lower()
    match = re.search(r"d(\d+)", text)
    return int(match.group(1)) if match else 0


def _ability_mod(score):
    try:
        return (int(score) - 10) // 2
    except (TypeError, ValueError):
        return 0


def _roll_4d6_drop_lowest():
    rolls = [random.randint(1, 6) for _ in range(4)]
    dropped = min(rolls)
    return rolls, dropped, sum(rolls) - dropped


def _point_buy_cost(score):
    try:
        return POINT_BUY_COST.get(int(score), 0)
    except (TypeError, ValueError):
        return 0


def _class_summary(class_name, classes_db):
    info = (classes_db or {}).get(class_name, {})
    if not info:
        return "No description available."
    hd = info.get("hit_die", "?")
    bab = str(info.get("bab", "?")).replace("_", " ").title()
    fort = info.get("fort", "?")
    ref = info.get("ref", "?")
    will = info.get("will", "?")
    sp = info.get("skill_points_per_level", "?")
    lines = [
        f"Hit Die: {hd}  |  Base Attack Bonus: {bab}",
        f"Saving Throws — Fort {fort}, Ref {ref}, Will {will}",
        f"Skill Points per Level: {sp} + Int modifier",
    ]
    sc = info.get("spellcasting") or {}
    if sc and not sc.get("advancement"):
        lines.append(
            f"Spellcasting: {sc.get('type', 'arcane').title()} "
            f"({sc.get('ability', '—')})",
        )
    feats = (info.get("features") or {}).get("1") or []
    if feats:
        names = [f.get("name", "") for f in feats[:5] if f.get("name")]
        if names:
            lines.append("Level 1 features: " + ", ".join(names))
    class_langs = CLASS_LANGUAGE_GRANTS.get(class_name)
    if class_langs:
        lines.append("Languages granted: " + ", ".join(class_langs))
    return "\n".join(lines)


def _skill_display_base(skill_key):
    if skill_key.startswith("Knowledge ("):
        return "Knowledge"
    prefix = skill_key.split("_", 1)[0] if "_" in skill_key else ""
    if prefix in ("craft", "profession", "perform"):
        return prefix.title()
    return skill_key


def _is_class_skill(skill_key, class_name, classes_db):
    if skill_key == SPEAK_LANGUAGE_SKILL:
        return True
    info = (classes_db or {}).get(class_name, {})
    class_skills = info.get("class_skills") or []
    base = _skill_display_base(skill_key)
    label = skill_key
    for entry in class_skills:
        if entry == "Knowledge (all)" and (
            label.startswith("Knowledge") or base == "Knowledge"
        ):
            return True
        if entry.lower() == label.lower() or entry.lower() == base.lower():
            return True
    return False


def _iter_wizard_skill_rows(sheet):
    rows_fn = getattr(sheet, "_skill_rows_for_ui", None)
    specialty_key = getattr(sheet, "_skill_specialty_key", None)
    resolve_label = getattr(sheet, "_resolved_skill_label", None)
    if rows_fn and specialty_key:
        for row_kind, row_index, ability_key, display_base in rows_fn():
            skill_key = specialty_key(row_kind, row_index) if row_index is not None else row_kind
            label = resolve_label(skill_key) if resolve_label else display_base
            yield skill_key, ability_key, label
        return
    for skill, ability_key in getattr(sheet, "all_skills", []):
        yield skill, ability_key, skill


def _refresh_highlighted_buttons(buttons, selected, primary, hover, unselected=UNSELECTED_BTN):
    for key, btn in buttons.items():
        try:
            if key == selected:
                btn.configure(fg_color=primary, hover_color=hover, text_color=SELECTED_TEXT)
            else:
                btn.configure(fg_color=unselected, hover_color="#4a4a4a", text_color=SELECTED_TEXT)
        except tk.TclError:
            pass


class CharacterCreationWizard:
    """Dark-mode step wizard; applies finished data through the host sheet."""

    def __init__(self, sheet, *, on_complete=None, on_cancel=None):
        self.sheet = sheet
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        self.root = sheet.root

        self.state = {
            "class_name": "",
            "race": "Human",
            "name": "",
            "alignment": "True Neutral",
            "abilities": {ab: POINT_BUY_MIN_SCORE for ab in ABILITY_NAMES},
            "rolled_ability_scores": [],
            "ability_score_pool": [],
            "ability_assignments": {},
            "ability_method": "point_buy",
            "general_feats": [],
            "human_bonus_feat": "",
            "feat_specs": {},
            "skill_ranks": {},
            "bonus_language_choices": [],
            "speak_language_choices": [],
            "known_spells": [],
            "prepared_spells": [],
            "known_invocations": [],
            "invocation_pick_count": 0,
            "inventory": [],
            "starting_gold": 0,
            "gold_remaining": 0,
            "auto_gear_applied": False,
            "wizard_cantrips_added": False,
        }
        self._step_index = 0
        self._content_frame = None
        self._title_label = None
        self._step_label = None
        self._back_btn = None
        self._next_btn = None
        self._skill_rank_labels = {}
        self._skill_minus_buttons = {}
        self._skill_plus_buttons = {}
        self._race_desc_label = None
        self._class_desc_label = None
        self._skill_budget_label = None
        self._shop_scroll = None
        self._class_buttons = {}
        self._race_buttons = {}
        self._alignment_buttons = {}
        self._feat_combos = {}
        self._feat_spec_frames = {}
        self._feat_spec_entries = {}
        self._sheet_data_backup = None
        self._spell_level_buttons = {}
        self._spell_list_buttons = {}
        self._active_spell_level = 0
        self._spell_status_label = None
        self._spell_advice_label = None
        self._spell_plan = None
        self._language_picker = None
        self._speak_language_picker = None

        self.popup = ctk.CTkToplevel(self.root)
        self.popup.title("Character Creation Wizard")
        self.popup.geometry(f"{WIZARD_WIDTH}x{WIZARD_HEIGHT}")
        self.popup.configure(fg_color=THEME_DARK_BG)
        self.popup.transient(self.root)
        self.popup.grab_set()
        self._center_popup()

        primary = self._primary_color()

        header = ctk.CTkFrame(self.popup, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))
        self._title_label = ctk.CTkLabel(
            header, text="Create Your Character",
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
            ("load_mundane_weapons_db", "mundane_weapons_db"),
            ("load_mundane_armors_shields_db", "mundane_armors_shields_db"),
            ("load_adventuring_gear_db", "adventuring_gear_db"),
            ("load_feats_db", "feats_db"),
            ("load_classes_db", "classes_db"),
        ):
            if not getattr(self.sheet, attr, None):
                fn = getattr(self.sheet, loader, None)
                if fn:
                    try:
                        fn()
                    except Exception:
                        pass
        if _warlock_support and hasattr(self.sheet, "load_invocations_db"):
            try:
                self.sheet.load_invocations_db()
            except Exception:
                pass
        self._ensure_spells_db_ready()

    def _ensure_spells_db_ready(self):
        loader = getattr(self.sheet, "load_spells_db", None)
        if loader:
            try:
                loader()
            except Exception:
                pass
        if getattr(self.sheet, "spells_db", None) and hasattr(self.sheet, "_rebuild_spell_indexes"):
            try:
                self.sheet._rebuild_spell_indexes()
            except Exception:
                pass

    def _get_step_order(self):
        steps = list(BASE_STEPS)
        if self._creation_speak_language_ranks() > 0:
            steps.append("speak_language")
        if self._needs_spell_step():
            steps.append("spells")
        if self._needs_invocation_step():
            steps.append("invocations")
        steps.extend(EQUIP_STEPS)
        return steps

    def _creation_speak_language_ranks(self):
        rank = float((self.state.get("skill_ranks") or {}).get(SPEAK_LANGUAGE_SKILL, 0) or 0)
        if rank <= 0:
            return 0
        if abs(rank - round(rank)) < 0.001:
            return int(round(rank))
        return int(rank)

    def _wizard_language_preview_data(self):
        abilities = {}
        for ab in ABILITY_NAMES:
            abilities[ab] = {"total": self._effective_ability(ab)}
        return {
            "race": self.state.get("race") or "",
            "abilities": abilities,
            "bonus_language_choices": list(self.state.get("bonus_language_choices") or []),
            "speak_language_languages": list(self.state.get("speak_language_choices") or []),
            "classes": [self.state.get("class_name") or "None", "None", "None"],
            "levels": [1, 0, 0],
        }

    def _wizard_known_languages(self):
        races = getattr(self.sheet, "races", {}) or {}
        return collect_character_languages(self._wizard_language_preview_data(), races)

    def _bonus_language_pick_count(self):
        return int_bonus_language_count(self._effective_ability("Intelligence"))

    def _current_step(self):
        return self._get_step_order()[self._step_index]

    def _clear_content(self):
        if self._content_frame:
            for w in self._content_frame.winfo_children():
                w.destroy()
        self._skill_rank_labels = {}
        self._skill_minus_buttons = {}
        self._skill_plus_buttons = {}
        self._shop_scroll = None
        self._class_buttons = {}
        self._race_buttons = {}
        self._alignment_buttons = {}
        self._feat_combos = {}
        if self._sheet_data_backup is not None:
            self.sheet.data = self._sheet_data_backup
            self._sheet_data_backup = None
        self._spell_level_buttons = {}
        self._spell_list_buttons = {}
        self._spell_status_label = None
        self._spell_advice_label = None
        self._spell_list_frame = None
        self._wizard_spell_db_popup = None
        self._language_picker = None
        self._speak_language_picker = None

    def _render_step(self):
        self._clear_content()
        step = self._current_step()
        order = self._get_step_order()
        titles = {
            "class": "Choose Your Class",
            "race": "Choose Your Race",
            "identity": "Name & Alignment",
            "abilities": "Ability Scores",
            "feats": "Starting Feats",
            "skills": "Skills",
            "languages": "Bonus Languages",
            "speak_language": "Speak Language",
            "spells": "Spells",
            "invocations": "Warlock Invocations",
            "equip_weapons": "Equipment — Weapons",
            "equip_armor": "Equipment — Armor & Shields",
            "equip_gear": "Equipment — Adventuring Gear",
        }
        self._title_label.configure(text=titles.get(step, "Create Your Character"))
        self._step_label.configure(text=f"Step {self._step_index + 1} of {len(order)}")
        self._back_btn.configure(state="normal" if self._step_index > 0 else "disabled")
        is_last = self._step_index >= len(order) - 1
        self._next_btn.configure(text="Finish" if is_last else "Next")

        builders = {
            "class": self._build_class_step,
            "race": self._build_race_step,
            "identity": self._build_identity_step,
            "abilities": self._build_abilities_step,
            "feats": self._build_feats_step,
            "skills": self._build_skills_step,
            "languages": self._build_languages_step,
            "speak_language": self._build_speak_language_step,
            "spells": self._build_spells_step,
            "invocations": self._build_invocations_step,
            "equip_weapons": self._build_equip_weapons_step,
            "equip_armor": self._build_equip_armor_step,
            "equip_gear": self._build_equip_gear_step,
        }
        builders[step]()

    def _build_class_step(self):
        primary = self._primary_color()
        hover = self._primary_hover()
        ctk.CTkLabel(
            self._content_frame,
            text="Select a class to begin. Descriptions summarize hit die, saves, skills, and level-1 features.",
            text_color="#aaaaaa", wraplength=WIZARD_WRAPLENGTH, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        body = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        list_frame = ctk.CTkScrollableFrame(body, fg_color=THEME_DARK_TRACK, width=220)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        desc_frame = ctk.CTkFrame(body, fg_color=THEME_DARK_TRACK)
        desc_frame.grid(row=0, column=1, sticky="nsew")
        self._class_desc_label = ctk.CTkLabel(
            desc_frame,
            text="Select a class.",
            justify="left", wraplength=420,
            font=ctk.CTkFont(size=13),
        )
        self._class_desc_label.pack(anchor="nw", padx=14, pady=14)

        def select_class(name):
            self.state["class_name"] = name
            classes_db = getattr(self.sheet, "classes_db", {}) or {}
            self._class_desc_label.configure(text=_class_summary(name, classes_db))
            _refresh_highlighted_buttons(
                self._class_buttons, name, primary, hover,
            )

        ctk.CTkLabel(
            list_frame, text="SRD Classes",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa",
        ).pack(anchor="w", padx=8, pady=(4, 2))
        for cls_name in SRD_WIZARD_CLASSES:
            btn = ctk.CTkButton(
                list_frame, text=cls_name, anchor="w", height=30,
                fg_color=UNSELECTED_BTN, hover_color="#4a4a4a",
                command=lambda n=cls_name: select_class(n),
            )
            btn.pack(fill="x", padx=6, pady=3)
            self._class_buttons[cls_name] = btn

        if not self.state["class_name"] and WIZARD_CLASSES:
            select_class(WIZARD_CLASSES[0])
        elif self.state["class_name"]:
            select_class(self.state["class_name"])

    def _build_race_step(self):
        primary = self._primary_color()
        hover = self._primary_hover()
        races = getattr(self.sheet, "races", {}) or {}
        ctk.CTkLabel(
            self._content_frame,
            text="Pick a race from the list. Your selection is highlighted; features appear on the right.",
            text_color="#aaaaaa", wraplength=WIZARD_WRAPLENGTH, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        body = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        list_frame = ctk.CTkScrollableFrame(body, fg_color=THEME_DARK_TRACK, width=220)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        desc_frame = ctk.CTkScrollableFrame(body, fg_color=THEME_DARK_TRACK)
        desc_frame.grid(row=0, column=1, sticky="nsew")
        self._race_desc_label = ctk.CTkLabel(
            desc_frame, text="", justify="left",
            wraplength=420, font=ctk.CTkFont(size=12),
            text_color="#cccccc",
        )
        self._race_desc_label.pack(anchor="nw", padx=14, pady=14)

        def select_race(name):
            self.state["race"] = name
            self._update_race_description(name)
            _refresh_highlighted_buttons(self._race_buttons, name, primary, hover)

        for race_name in sorted(races.keys(), key=str.lower):
            btn = ctk.CTkButton(
                list_frame, text=race_name, anchor="w", height=28,
                fg_color=UNSELECTED_BTN, hover_color="#4a4a4a",
                command=lambda n=race_name: select_race(n),
            )
            btn.pack(fill="x", padx=6, pady=2)
            self._race_buttons[race_name] = btn

        if self.state["race"] not in races and races:
            self.state["race"] = sorted(races.keys(), key=str.lower)[0]
        select_race(self.state["race"])

    def _update_race_description(self, race_name):
        race_data = (getattr(self.sheet, "races", {}) or {}).get(race_name, {})
        features = race_data.get("features", "No description available.")
        mods = []
        for ab in ABILITY_NAMES:
            short = ABILITY_SHORT[ab]
            key = ABILITY_RACE_KEYS[ab]
            val = int(race_data.get(key, 0) or 0)
            if val:
                mods.append(f"{short} {val:+d}")
        header = race_name
        if mods:
            header += f"  ({', '.join(mods)})"
        if race_data.get("size"):
            header += f"  |  Size: {race_data['size']}"
        auto = racial_automatic_languages(race_name, getattr(self.sheet, "races", {}) or {})
        lang_lines = []
        if auto:
            lang_lines.append("Automatic Languages: " + ", ".join(auto))
        pool = bonus_language_options(race_name, getattr(self.sheet, "races", {}) or {})
        if race_data.get("bonus_languages_any"):
            lang_lines.append(
                "Bonus Languages: Any (other than secret languages, such as Druidic).",
            )
        elif pool:
            lang_lines.append("Bonus Languages: " + ", ".join(pool))
        lang_block = ("\n".join(lang_lines) + "\n\n") if lang_lines else ""
        self._race_desc_label.configure(text=f"{header}\n\n{lang_block}{features}")

    def _build_identity_step(self):
        primary = self._primary_color()
        hover = self._primary_hover()
        ctk.CTkLabel(
            self._content_frame, text="Character Name", font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", pady=(0, 4))
        self._name_var = tk.StringVar(value=self.state["name"])
        ctk.CTkEntry(
            self._content_frame, textvariable=self._name_var, width=360,
            placeholder_text="Enter character name",
        ).pack(anchor="w", pady=(0, 14))

        ctk.CTkLabel(
            self._content_frame, text="Alignment", font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", pady=(0, 4))
        restricted = self._restricted_alignments()
        grid = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        grid.pack(anchor="w", pady=4)
        self._alignment_var = tk.StringVar(value=self.state["alignment"])

        def select_alignment(alignment):
            if alignment in restricted:
                return
            self._alignment_var.set(alignment)
            self.state["alignment"] = alignment
            _refresh_highlighted_buttons(
                self._alignment_buttons, alignment, primary, hover,
                unselected="#2F2F2F",
            )

        for index, alignment in enumerate(ALL_ALIGNMENTS):
            row, col = divmod(index, 3)
            is_bad = alignment in restricted
            if is_bad:
                btn = ctk.CTkButton(
                    grid, width=120, height=30, text=alignment,
                    fg_color=ALIGNMENT_RESTRICTED_FG,
                    hover_color=ALIGNMENT_RESTRICTED_FG,
                    text_color=ALIGNMENT_RESTRICTED_TEXT,
                    state="disabled",
                )
            else:
                btn = ctk.CTkButton(
                    grid, width=120, height=30, text=alignment,
                    fg_color=UNSELECTED_BTN, hover_color="#4a4a4a",
                    command=lambda a=alignment: select_alignment(a),
                )
                self._alignment_buttons[alignment] = btn
            btn.grid(row=row, column=col, padx=4, pady=4)

        if self.state["alignment"] not in restricted:
            select_alignment(self.state["alignment"])

    def _restricted_alignments(self):
        cls = self.state.get("class_name") or ""
        info = (getattr(self.sheet, "classes_db", {}) or {}).get(cls, {})
        return set(info.get("restricted_alignments") or [])

    def _race_data(self):
        return (getattr(self.sheet, "races", {}) or {}).get(self.state.get("race"), {}) or {}

    def _racial_mod(self, ability_name):
        return int(self._race_data().get(ABILITY_RACE_KEYS[ability_name], 0) or 0)

    def _set_ability_score(self, ability_name, score):
        try:
            value = int(score)
        except (TypeError, ValueError):
            return
        value = max(3, min(18, value))
        self.state["abilities"][ability_name] = value
        var = getattr(self, "_ability_vars", {}).get(ability_name)
        if var is not None:
            var.set(str(value))
        self._refresh_ability_row_labels()

    def _resolved_ability_score(self, ability_name, *, default=POINT_BUY_MIN_SCORE):
        assigned = (self.state.get("ability_assignments") or {}).get(ability_name)
        if assigned is not None:
            return int(assigned)
        try:
            return int(self.state["abilities"].get(ability_name, default) or default)
        except (TypeError, ValueError):
            return default

    def _ability_base_score(self, ability_name):
        if self._ability_input_mode() == "assign":
            assigned = (self.state.get("ability_assignments") or {}).get(ability_name)
            if assigned is None:
                return None
            return int(assigned)
        try:
            return int(self._ability_vars[ability_name].get() or POINT_BUY_MIN_SCORE)
        except (TypeError, ValueError, KeyError):
            return POINT_BUY_MIN_SCORE

    def _ability_input_mode(self):
        return getattr(self, "_ability_ui_mode", "point_buy")

    def _switch_ability_ui_mode(self, mode):
        self._ability_ui_mode = mode
        if mode == "point_buy":
            self.state["ability_assignments"] = {}
        for ability_name in ABILITY_NAMES:
            label = getattr(self, "_ability_base_labels", {}).get(ability_name)
            menu = getattr(self, "_ability_assign_menus", {}).get(ability_name)
            var = getattr(self, "_ability_vars", {}).get(ability_name)
            if label is None or menu is None:
                continue
            if mode == "assign":
                label.pack_forget()
                menu.pack(side="left", padx=(0, 8))
            else:
                menu.pack_forget()
                label.pack(side="left", padx=(0, 8))
                if var is not None:
                    score = self.state["abilities"].get(ability_name, POINT_BUY_MIN_SCORE)
                    var.set(str(score))

    def _clear_ability_assignments(self):
        self.state["ability_assignments"] = {}
        for ability_name in ABILITY_NAMES:
            assign_var = getattr(self, "_ability_assign_vars", {}).get(ability_name)
            if assign_var is not None:
                assign_var.set("—")

    def _assigned_ability_scores(self, *, exclude=None):
        assigned = dict(self.state.get("ability_assignments") or {})
        if exclude:
            assigned = {ab: score for ab, score in assigned.items() if ab != exclude}
        return assigned

    def _dropdown_values_for(self, ability_name):
        pool = list(self.state.get("ability_score_pool") or [])
        if not pool:
            return ["—"]
        assigned_elsewhere = list(self._assigned_ability_scores(exclude=ability_name).values())
        pool_counts = {}
        for score in pool:
            pool_counts[score] = pool_counts.get(score, 0) + 1
        assigned_counts = {}
        for score in assigned_elsewhere:
            assigned_counts[score] = assigned_counts.get(score, 0) + 1
        available = []
        for score in sorted(pool_counts, reverse=True):
            remaining = pool_counts[score] - assigned_counts.get(score, 0)
            available.extend([score] * max(0, remaining))
        assign_var = getattr(self, "_ability_assign_vars", {}).get(ability_name)
        current = assign_var.get().strip() if assign_var else ""
        options = ["—"] + [str(score) for score in available]
        if current and current != "—" and current not in options:
            options.insert(1, current)
        return options

    def _refresh_ability_dropdowns(self):
        for ability_name in ABILITY_NAMES:
            menu = getattr(self, "_ability_assign_menus", {}).get(ability_name)
            if menu is None:
                continue
            values = self._dropdown_values_for(ability_name)
            menu.configure(values=values)
            assign_var = self._ability_assign_vars.get(ability_name)
            if assign_var and assign_var.get() not in values:
                assign_var.set("—")

    def _on_ability_assign(self, ability_name, choice):
        assignments = dict(self.state.get("ability_assignments") or {})
        if choice == "—":
            assignments.pop(ability_name, None)
            self._ability_vars[ability_name].set("—")
        else:
            score = int(choice)
            assignments[ability_name] = score
            self.state["abilities"][ability_name] = score
            self._ability_vars[ability_name].set(str(score))
        self.state["ability_assignments"] = assignments
        self._refresh_ability_dropdowns()
        self._refresh_ability_row_labels()

    def _refresh_ability_row_labels(self):
        for ability_name, labels in getattr(self, "_ability_row_labels", {}).items():
            base = self._ability_base_score(ability_name)
            if base is None:
                if "racial" in labels:
                    labels["racial"].configure(text="")
                if "total" in labels:
                    labels["total"].configure(text="—")
                continue
            racial = self._racial_mod(ability_name)
            total = base + racial
            mod = _ability_mod(total)
            mod_text = f"{mod:+d}" if mod else "+0"
            if "racial" in labels:
                labels["racial"].configure(
                    text=f"Racial {racial:+d}" if racial else "Racial +0",
                )
            if "total" in labels:
                labels["total"].configure(text=f"Total {total} ({mod_text})")

    def _point_buy_spent(self):
        spent = 0
        for ability_name in ABILITY_NAMES:
            try:
                score = int(self._ability_vars[ability_name].get() or POINT_BUY_MIN_SCORE)
            except (TypeError, ValueError, KeyError):
                score = POINT_BUY_MIN_SCORE
            spent += _point_buy_cost(score)
        return spent

    def _update_point_buy_display(self):
        label = getattr(self, "_point_buy_points_label", None)
        if label is None:
            return
        spent = self._point_buy_spent()
        remaining = POINT_BUY_POOL - spent
        color = "#7fd6c7" if remaining == 0 else ("#d9534f" if remaining < 0 else "#cccccc")
        label.configure(
            text=f"Points spent: {spent} / {POINT_BUY_POOL}   •   Remaining: {remaining}",
            text_color=color,
        )

    def _point_buy_adjust(self, ability_name, delta):
        self._switch_ability_ui_mode("point_buy")
        try:
            current = int(self._ability_vars[ability_name].get() or POINT_BUY_MIN_SCORE)
        except (TypeError, ValueError, KeyError):
            current = POINT_BUY_MIN_SCORE
        new_score = current + int(delta)
        if new_score < POINT_BUY_MIN_SCORE or new_score > POINT_BUY_MAX_SCORE:
            return
        old_cost = _point_buy_cost(current)
        new_cost = _point_buy_cost(new_score)
        if self._point_buy_spent() - old_cost + new_cost > POINT_BUY_POOL:
            return
        self._set_ability_score(ability_name, new_score)
        self.state["ability_method"] = "point_buy"
        self._update_point_buy_display()

    def _reset_point_buy(self):
        self._switch_ability_ui_mode("point_buy")
        for ability_name in ABILITY_NAMES:
            self._set_ability_score(ability_name, POINT_BUY_MIN_SCORE)
        self.state["ability_method"] = "point_buy"
        self.state["ability_score_pool"] = []
        self.state["ability_assignments"] = {}
        self._update_point_buy_display()

    def _apply_scores_in_order(self, scores):
        for ability_name, score in zip(ABILITY_NAMES, scores):
            self._set_ability_score(ability_name, score)

    def _activate_standard_array_pool(self):
        self.state["ability_score_pool"] = list(STANDARD_ABILITY_ARRAY)
        self.state["ability_method"] = "standard_array"
        self._clear_ability_assignments()
        self._switch_ability_ui_mode("assign")
        self._refresh_ability_dropdowns()
        self._refresh_ability_row_labels()

    def _update_roll_log_display(self):
        log = getattr(self, "_roll_log_box", None)
        if log is None:
            return
        lines = []
        for index, entry in enumerate(self.state.get("rolled_ability_scores") or [], start=1):
            rolls = entry.get("rolls") or []
            dropped = entry.get("dropped", 0)
            total = entry.get("total", 0)
            lines.append(f"Roll {index}: {rolls} → drop {dropped} = {total}")
        pool = self.state.get("ability_score_pool") or []
        if pool:
            lines.append("")
            lines.append(f"Pool: {', '.join(str(score) for score in sorted(pool, reverse=True))}")
            lines.append("Assign each value using the Base dropdowns on the left.")
        if not lines:
            log.configure(
                text="No rolls yet. Roll all six, then assign each result from the Base dropdowns.",
            )
        else:
            log.configure(text="\n".join(lines))

    def _build_4d6_roll_result(self, roll_label, rolls, dropped, total):
        return {
            "label": f"{roll_label} — 4d6 drop lowest",
            "formula": f"{rolls} (drop {dropped})",
            "groups": [{
                "display": "4d6",
                "rolls": list(rolls),
                "modifier": -int(dropped),
                "total": int(total),
                "min_total": int(total),
                "max_total": int(total),
            }],
            "result_text": str(total),
        }

    def _show_ability_dice_roll(self, roll_label, rolls, dropped, total, on_complete):
        roll_result = self._build_4d6_roll_result(roll_label, rolls, dropped, total)
        show_popup = getattr(self.sheet, "_show_local_dice_roll_popup", None)
        if callable(show_popup):
            show_popup(roll_result, on_complete=lambda _result: on_complete(total))
        else:
            on_complete(total)

    def _record_generic_roll(self, rolls, dropped, total):
        entries = list(self.state.get("rolled_ability_scores") or [])
        entries.append({
            "rolls": list(rolls),
            "dropped": dropped,
            "total": total,
        })
        self.state["rolled_ability_scores"] = entries

    def _roll_all_ability_scores(self, index=0):
        if index == 0:
            self.state["rolled_ability_scores"] = []
            self.state["ability_score_pool"] = []
            self._clear_ability_assignments()
        if index >= len(ABILITY_NAMES):
            totals = [entry.get("total", 0) for entry in self.state.get("rolled_ability_scores") or []]
            self.state["ability_score_pool"] = totals
            self.state["ability_method"] = "roll"
            self._switch_ability_ui_mode("assign")
            self._refresh_ability_dropdowns()
            self._refresh_ability_row_labels()
            self._update_roll_log_display()
            return
        rolls, dropped, total = _roll_4d6_drop_lowest()

        def _after_popup(_score):
            self._record_generic_roll(rolls, dropped, total)
            self._update_roll_log_display()
            self.root.after(350, lambda: self._roll_all_ability_scores(index + 1))

        self._show_ability_dice_roll(f"Roll {index + 1}", rolls, dropped, total, _after_popup)

    def _build_abilities_step(self):
        primary = self._primary_color()
        hover = self._primary_hover()
        ctk.CTkLabel(
            self._content_frame,
            text="Set base ability scores (before racial adjustments). Use the panel on the right for point buy, rolling, or the standard array.",
            text_color="#aaaaaa", wraplength=WIZARD_WRAPLENGTH, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        body = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=THEME_DARK_TRACK)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(
            left, text="Base Scores", font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 6))

        header = ctk.CTkFrame(left, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(0, 4))
        for text, width in (("Ability", 118), ("Base", 56), ("Racial", 72), ("After Race", 100)):
            ctk.CTkLabel(
                header, text=text, width=width, anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"), text_color="#888888",
            ).pack(side="left")

        self._ability_vars = {}
        self._ability_row_labels = {}
        self._ability_base_labels = {}
        self._ability_assign_vars = {}
        self._ability_assign_menus = {}
        self._ability_ui_mode = "point_buy"
        for ability_name in ABILITY_NAMES:
            row = ctk.CTkFrame(left, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(row, text=ability_name, width=118, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(self.state["abilities"].get(ability_name, POINT_BUY_MIN_SCORE)))
            self._ability_vars[ability_name] = var
            base_label = ctk.CTkLabel(
                row, textvariable=var, width=56, anchor="center",
                fg_color="#2a2a2a", corner_radius=6,
            )
            base_label.pack(side="left", padx=(0, 8))
            self._ability_base_labels[ability_name] = base_label
            assign_var = tk.StringVar(value="—")
            self._ability_assign_vars[ability_name] = assign_var
            assign_menu = ctk.CTkOptionMenu(
                row,
                values=["—"],
                variable=assign_var,
                width=56,
                command=lambda choice, ab=ability_name: self._on_ability_assign(ab, choice),
            )
            self._ability_assign_menus[ability_name] = assign_menu
            racial_lbl = ctk.CTkLabel(row, text="", text_color="#888888", width=72, anchor="w")
            racial_lbl.pack(side="left")
            total_lbl = ctk.CTkLabel(row, text="", text_color="#aaaaaa", width=100, anchor="w")
            total_lbl.pack(side="left")
            self._ability_row_labels[ability_name] = {"racial": racial_lbl, "total": total_lbl}

        method = self.state.get("ability_method")
        if method in ("roll", "standard_array") and self.state.get("ability_score_pool"):
            self._ability_ui_mode = "assign"
            for ability_name in ABILITY_NAMES:
                self._ability_base_labels[ability_name].pack_forget()
                self._ability_assign_menus[ability_name].pack(side="left", padx=(0, 8))
                score = (self.state.get("ability_assignments") or {}).get(ability_name)
                if score is not None:
                    self._ability_assign_vars[ability_name].set(str(score))
                    self._ability_vars[ability_name].set(str(score))
                else:
                    self._ability_assign_vars[ability_name].set("—")
                    self._ability_vars[ability_name].set("—")
            self._refresh_ability_dropdowns()
        else:
            self._switch_ability_ui_mode("point_buy")

        self._refresh_ability_row_labels()

        right = ctk.CTkFrame(body, fg_color=THEME_DARK_TRACK)
        right.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(
            right, text="Generation Methods", font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 6))

        tabs = ctk.CTkTabview(right, width=360)
        tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tab_buy = tabs.add("Point Buy")
        tab_roll = tabs.add("Roll 4d6")
        tab_array = tabs.add("Standard Array")

        ctk.CTkLabel(
            tab_buy,
            text="D&D 3.5 point buy (27 points). All scores start at 8 and can go up to 18.",
            text_color="#aaaaaa", wraplength=320, justify="left",
        ).pack(anchor="w", padx=8, pady=(8, 6))
        self._point_buy_points_label = ctk.CTkLabel(
            tab_buy, text="", font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
        )
        self._point_buy_points_label.pack(anchor="w", padx=8, pady=(0, 8))

        buy_scroll = ctk.CTkScrollableFrame(tab_buy, height=220, fg_color="transparent")
        buy_scroll.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        for ability_name in ABILITY_NAMES:
            row = ctk.CTkFrame(buy_scroll, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=ABILITY_SHORT[ability_name], width=36, anchor="w").pack(side="left")
            ctk.CTkButton(
                row, text="−", width=28, fg_color="#555555",
                command=lambda ab=ability_name: self._point_buy_adjust(ab, -1),
            ).pack(side="left", padx=(4, 2))
            ctk.CTkLabel(
                row, textvariable=self._ability_vars[ability_name], width=30,
            ).pack(side="left")
            ctk.CTkButton(
                row, text="+", width=28, fg_color=primary, hover_color=hover,
                command=lambda ab=ability_name: self._point_buy_adjust(ab, 1),
            ).pack(side="left", padx=(2, 6))
        ctk.CTkButton(
            tab_buy, text="Reset to 8s", width=140, fg_color="#555555",
            command=self._reset_point_buy,
        ).pack(anchor="w", padx=8, pady=(0, 8))
        self._update_point_buy_display()

        ctk.CTkLabel(
            tab_roll,
            text="Roll 4d6 six times (drop lowest each time). Assign each result from the Base dropdowns on the left.",
            text_color="#aaaaaa", wraplength=320, justify="left",
        ).pack(anchor="w", padx=8, pady=(8, 6))
        self._roll_log_box = ctk.CTkLabel(
            tab_roll,
            text="No rolls yet. Roll all six, then assign each result from the Base dropdowns.",
            justify="left", anchor="nw", wraplength=320, text_color="#cccccc",
        )
        self._roll_log_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._update_roll_log_display()

        roll_btns = ctk.CTkFrame(tab_roll, fg_color="transparent")
        roll_btns.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(
            roll_btns, text="Roll All Six", width=110,
            fg_color=primary, hover_color=hover,
            command=self._roll_all_ability_scores,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            tab_array,
            text="Use the classic standard array and assign each value from the Base dropdowns on the left.",
            text_color="#aaaaaa", wraplength=320, justify="left",
        ).pack(anchor="w", padx=8, pady=(8, 10))
        ctk.CTkLabel(
            tab_array,
            text=", ".join(str(score) for score in STANDARD_ABILITY_ARRAY),
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=primary,
        ).pack(anchor="w", padx=8, pady=(0, 8))
        ctk.CTkButton(
            tab_array, text="Use Standard Array", width=180,
            fg_color=primary, hover_color=hover,
            command=self._activate_standard_array_pool,
        ).pack(anchor="w", padx=8, pady=(0, 8))

    def _feat_slot_labels(self):
        labels = ["General Feat (level 1)"]
        if self.state.get("race") == "Human":
            labels.append("Human Bonus Feat")
        return labels

    def _is_human_bonus_ui_slot(self, ui_idx):
        return self.state.get("race") == "Human" and ui_idx == 1

    def _feat_storage_index(self, ui_idx):
        """Map wizard feat row index to sheet general_feats array index."""
        if self.state.get("race") == "Human":
            return {0: 1, 1: 0}.get(ui_idx, ui_idx)
        return ui_idx

    def _general_feats_for_sheet(self):
        feats = list(self.state.get("general_feats") or [])
        while len(feats) < 6:
            feats.append("")
        if self.state.get("race") == "Human":
            human_bonus = str(self.state.get("human_bonus_feat") or "").strip()
            if human_bonus:
                feats[0] = human_bonus
        return feats[:6]

    def _feat_slot_values(self):
        feats = list(self.state.get("general_feats") or [])
        values = []
        for ui_idx in range(len(self._feat_slot_labels())):
            if self._is_human_bonus_ui_slot(ui_idx):
                human_bonus = str(self.state.get("human_bonus_feat") or "").strip()
                values.append(human_bonus or (feats[0] if feats else ""))
            else:
                storage_idx = self._feat_storage_index(ui_idx)
                values.append(feats[storage_idx] if storage_idx < len(feats) else "")
        return values

    def _with_temp_sheet_data(self, callback):
        old = getattr(self.sheet, "data", None)
        try:
            self.sheet.data = self._temp_character_data_for_sheet()
            return callback()
        finally:
            if old is not None:
                self.sheet.data = old

    def _temp_character_data_for_sheet(self):
        cls = self.state.get("class_name") or "Fighter"
        race_data = (getattr(self.sheet, "races", {}) or {}).get(self.state.get("race"), {})
        abilities = {}
        for ab in ABILITY_NAMES:
            base = self._resolved_ability_score(ab)
            racial = int(race_data.get(ABILITY_RACE_KEYS[ab], 0) or 0)
            total = base + racial
            abilities[ab] = {"base": base, "racial": racial, "enh": 0, "misc": 0, "total": total}
        return {
            "name": self.state.get("name", ""),
            "alignment": self.state.get("alignment", "True Neutral"),
            "race": self.state.get("race", "Human"),
            "classes": [cls, "None", "None"],
            "levels": [1, 0, 0],
            "abilities": abilities,
            "general_feats": self._general_feats_for_sheet(),
            "human_bonus_feat": self.state.get("human_bonus_feat") or "",
            "feat_specs": copy.deepcopy(self.state.get("feat_specs") or {}),
            "known_spells": list(self.state.get("known_spells") or []),
            "prepared_spells": list(self.state.get("prepared_spells") or []),
        }

    def _sync_sheet_data_for_feats(self):
        if self._sheet_data_backup is None:
            self._sheet_data_backup = getattr(self.sheet, "data", None)
        self.sheet.data = self._temp_character_data_for_sheet()

    def _feat_slot_storage_key(self, ui_idx):
        return f"general_feat_{self._feat_storage_index(ui_idx)}"

    def _get_wizard_feat_spec(self, ui_idx):
        slot_key = self._feat_slot_storage_key(ui_idx)
        return str((self.state.get("feat_specs") or {}).get(slot_key, "") or "").strip()

    def _set_wizard_feat_spec(self, ui_idx, value):
        slot_key = self._feat_slot_storage_key(ui_idx)
        specs = dict(self.state.get("feat_specs") or {})
        text = str(value or "").strip()
        if text:
            specs[slot_key] = text
        else:
            specs.pop(slot_key, None)
        self.state["feat_specs"] = specs

    def _refresh_wizard_feat_spec_field(self, ui_idx, feat_name):
        frame = self._feat_spec_frames.get(ui_idx)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        self._feat_spec_entries.pop(ui_idx, None)

        sheet = self.sheet
        base, _legacy = sheet._normalize_feat_selection(feat_name)
        if not base or not sheet._feat_needs_spec_picker(base):
            frame.pack_forget()
            self._set_wizard_feat_spec(ui_idx, "")
            return

        config = sheet._get_weapon_feat_spec_config(base) or {}
        label_text = str(config.get("label", "Weapon:") or "Weapon:").strip()
        ctk.CTkLabel(frame, text=label_text, width=110, anchor="w").pack(side="left", padx=(8, 4))
        entry = ctk.CTkEntry(frame, width=220, placeholder_text="e.g. Longsword or Slashing")
        entry.pack(side="left", fill="x", expand=True)
        saved = self._get_wizard_feat_spec(ui_idx)
        if saved:
            entry.insert(0, saved)

        def _on_change(_event=None, i=ui_idx, ent=entry):
            self._set_wizard_feat_spec(i, ent.get())

        entry.bind("<KeyRelease>", _on_change)
        entry.bind("<FocusOut>", _on_change)
        self._feat_spec_entries[ui_idx] = entry
        frame.pack(side="left", fill="x", expand=True, padx=(8, 0))

    def _set_feat_slot(self, ui_idx, feat_name):
        feat_name = str(feat_name or "").strip()
        base, legacy_spec = self.sheet._normalize_feat_selection(feat_name)
        if self._is_human_bonus_ui_slot(ui_idx):
            self.state["human_bonus_feat"] = base
            feats = list(self.state.get("general_feats") or [])
            while len(feats) <= 0:
                feats.append("")
            feats[0] = base
            self.state["general_feats"] = feats
        else:
            storage_idx = self._feat_storage_index(ui_idx)
            feats = list(self.state.get("general_feats") or [])
            while len(feats) <= storage_idx:
                feats.append("")
            feats[storage_idx] = base
            self.state["general_feats"] = feats
        if legacy_spec and not self._get_wizard_feat_spec(ui_idx):
            self._set_wizard_feat_spec(ui_idx, legacy_spec)
        elif base and not self.sheet._feat_needs_spec_picker(base):
            self._set_wizard_feat_spec(ui_idx, "")
        self._sync_sheet_data_for_feats()
        if hasattr(self, "_feat_spec_frames"):
            self._refresh_wizard_feat_spec_field(ui_idx, base)

    def _build_feats_step(self):
        self._sync_sheet_data_for_feats()
        count = len(self._feat_slot_labels())
        ctk.CTkLabel(
            self._content_frame,
            text=(
                f"Choose {count} starting feat{'s' if count > 1 else ''}. "
                "Use the searchable dropdown for each slot — type to search or click ▾ "
                "to see feats you currently qualify for. Feats that require a weapon or "
                "damage type (Weapon Focus, Weapon Specialization, Melee Weapon Mastery, etc.) "
                "show an extra field — enter the matching weapon name or damage type."
            ),
            text_color="#aaaaaa", wraplength=WIZARD_WRAPLENGTH, justify="left",
        ).pack(anchor="w", pady=(0, 12))

        values = self._feat_slot_values()
        create_combo = getattr(self.sheet, "_create_feat_combo", None)
        if not create_combo:
            ctk.CTkLabel(
                self._content_frame,
                text="Feat picker unavailable — feats database could not be loaded.",
                text_color="#cc6666",
            ).pack(anchor="w")
            return

        self._feat_combos = {}
        self._feat_spec_frames = {}
        self._feat_spec_entries = {}
        for idx, label in enumerate(self._feat_slot_labels()):
            row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
            row.pack(fill="x", pady=6)
            ctk.CTkLabel(
                row, text=label, width=220, anchor="w",
                font=ctk.CTkFont(weight="bold"),
            ).pack(side="left", padx=(0, 12))
            combo = create_combo(
                row,
                width=360,
                on_select=lambda val, i=idx: self._set_feat_slot(i, val),
                general_feat_index=self._feat_storage_index(idx),
                initial=values[idx],
            )
            combo.pack(side="left")
            combo.bind(
                "<FocusOut>",
                lambda _e, i=idx, c=combo: self._set_feat_slot(i, c.get()),
                add="+",
            )
            self._feat_combos[idx] = combo
            spec_frame = ctk.CTkFrame(row, fg_color="transparent")
            self._feat_spec_frames[idx] = spec_frame
            self._refresh_wizard_feat_spec_field(idx, values[idx])
            if hasattr(self.sheet, "show_feat_details"):
                ctk.CTkButton(
                    row, text="ℹ", width=30, height=28, fg_color="#666666",
                    command=lambda c=combo: self.sheet.show_feat_details(c.get()),
                ).pack(side="left", padx=(8, 0))

    def _effective_ability(self, ability_name):
        base = self._resolved_ability_score(ability_name)
        race = (getattr(self.sheet, "races", {}) or {}).get(self.state.get("race"), {})
        racial = int(race.get(ABILITY_RACE_KEYS[ability_name], 0) or 0)
        return base + racial

    def _sheet_get_spells_per_day(self, cls_name, class_level):
        def fetch():
            return self.sheet.get_spells_per_day(cls_name, class_level)
        return self._with_temp_sheet_data(fetch)

    def _is_caster(self):
        cls = self.state.get("class_name") or ""
        info = (getattr(self.sheet, "classes_db", {}) or {}).get(cls, {})
        sc = info.get("spellcasting") or {}
        if sc.get("advancement"):
            return False
        if cls in HALF_CASTER_CLASSES:
            return False
        return bool(sc.get("spells_per_day") or sc.get("spells_known"))

    def _needs_spell_step(self):
        if not self._is_caster():
            return False
        plan = self._compute_spell_plan()
        return bool(plan and (plan.get("pick_known") or plan.get("pick_prepared")))

    def _compute_spell_plan(self):
        cls = self.state.get("class_name") or ""
        info = (getattr(self.sheet, "classes_db", {}) or {}).get(cls, {})
        sc = info.get("spellcasting") or {}
        if not sc:
            return None

        per_day = self._sheet_get_spells_per_day(cls, 1) or []

        if cls in SPONTANEOUS_CASTERS or sc.get("casting_style") == "spontaneous":
            known_table = (sc.get("spells_known") or {}).get("1") or []
            pick_known = {i: int(c) for i, c in enumerate(known_table) if int(c) > 0}
            parts = [
                f"{count} level-{lvl} spell{'s' if count != 1 else ''}"
                for lvl, count in sorted(pick_known.items())
            ]
            return {
                "mode": "spontaneous",
                "pick_known": pick_known,
                "pick_prepared": {},
                "auto_known_level": None,
                "advice": (
                    f"As a {cls}, choose {' and '.join(parts)} you know permanently. "
                    "Selected spells are highlighted."
                ),
            }

        if cls == "Wizard":
            int_mod = _ability_mod(self._effective_ability("Intelligence"))
            book_lvl1 = max(1, 3 + int_mod)
            pick_prepared = {
                lvl: per_day[lvl]
                for lvl in range(0, 2)
                if lvl < len(per_day) and per_day[lvl] > 0
            }
            prep_parts = [
                f"{count} level-{lvl}"
                for lvl, count in sorted(pick_prepared.items())
            ]
            return {
                "mode": "wizard",
                "pick_known": {1: book_lvl1},
                "pick_prepared": pick_prepared,
                "auto_known_level": 0,
                "advice": (
                    "All 0-level wizard spells are added to your spellbook automatically. "
                    f"Choose {book_lvl1} first-level spell{'s' if book_lvl1 != 1 else ''} "
                    f"for your spellbook (3 + Int modifier). "
                    f"Then prepare {' and '.join(prep_parts)} for today from your spellbook."
                ),
            }

        pick_prepared = {
            lvl: per_day[lvl]
            for lvl in range(0, 2)
            if lvl < len(per_day) and per_day[lvl] > 0
        }
        parts = [f"{count} level-{lvl}" for lvl, count in sorted(pick_prepared.items())]
        return {
            "mode": "prepared",
            "pick_known": {},
            "pick_prepared": pick_prepared,
            "auto_known_level": None,
            "advice": (
                f"As a {cls}, you may prepare spells from your class list. "
                f"Choose {' and '.join(parts)} to prepare today. "
                "Selected spells are highlighted."
            ),
        }

    def _ensure_wizard_cantrips(self):
        if self.state.get("wizard_cantrips_added"):
            return
        plan = self._compute_spell_plan()
        if not plan or plan.get("auto_known_level") is None:
            return
        level = plan["auto_known_level"]
        known = set(self.state.get("known_spells") or [])
        for spell_name, _info in self._get_class_spells_for_level("Wizard", level):
            known.add(spell_name)
        self.state["known_spells"] = sorted(known, key=str.lower)
        self.state["wizard_cantrips_added"] = True

    def _get_class_spells_for_level(self, class_name, spell_level):
        self._ensure_spells_db_ready()
        class_key = class_name.lower()
        indexed = list(
            getattr(self.sheet, "_spells_by_class_level", {}).get((class_key, spell_level), []),
        )
        if indexed:
            return indexed
        spells_db = getattr(self.sheet, "spells_db", {}) or {}
        get_level = getattr(self.sheet, "_get_spell_level_for_class", None)
        get_classes = getattr(self.sheet, "_get_spell_classes", None)
        results = []
        for spell_name, info in spells_db.items():
            if get_level:
                level = get_level(info, class_name)
            else:
                level = int(info.get("level", 0) or 0)
            if level != spell_level:
                continue
            if get_classes:
                if class_name not in get_classes(info):
                    continue
            elif class_name not in (info.get("classes") or []):
                continue
            results.append((spell_name, info))
        return sorted(results, key=lambda item: item[0].lower())

    def _spell_level_label(self, level):
        return "Cantrips (0)" if level == 0 else f"Level {level}"

    def _spells_selected_for_level(self, spell_level, plan, context=None):
        cls = self.state["class_name"]
        if context == "known":
            return [
                s for s in self.state.get("known_spells", [])
                if self._spell_level_for_class(s, cls) == spell_level
            ]
        if context == "prepared":
            return [
                e.get("spell") for e in self.state.get("prepared_spells", [])
                if int(e.get("slot_level", e.get("base_level", -1))) == spell_level
            ]
        mode = plan.get("mode")
        if mode == "spontaneous":
            return [
                s for s in self.state.get("known_spells", [])
                if self._spell_level_for_class(s, cls) == spell_level
            ]
        if mode == "wizard" and spell_level in plan.get("pick_known", {}):
            needed = plan["pick_known"][spell_level]
            if spell_level == plan.get("auto_known_level"):
                pass
            else:
                known_at_level = [
                    s for s in self.state.get("known_spells", [])
                    if self._spell_level_for_class(s, cls) == spell_level
                ]
                if len(known_at_level) < needed:
                    return known_at_level
        return [
            e.get("spell") for e in self.state.get("prepared_spells", [])
            if int(e.get("slot_level", e.get("base_level", -1))) == spell_level
        ]

    def _default_spell_level_for_plan(self, plan):
        levels = sorted(
            set(plan.get("pick_known", {}).keys()) | set(plan.get("pick_prepared", {}).keys()),
        )
        if not levels:
            return 0
        cls = self.state["class_name"]
        for level in sorted(plan.get("pick_known", {}).keys()):
            if level == plan.get("auto_known_level"):
                continue
            needed = plan["pick_known"][level]
            count = len([
                s for s in self.state.get("known_spells", [])
                if self._spell_level_for_class(s, cls) == level
            ])
            if count < needed:
                return level
        if self._active_spell_level in levels:
            return self._active_spell_level
        return levels[0]

    def _spell_level_for_class(self, spell_name, class_name):
        info = (getattr(self.sheet, "spells_db", {}) or {}).get(spell_name, {})
        if hasattr(self.sheet, "_get_spell_level_for_class"):
            return self.sheet._get_spell_level_for_class(info, class_name)
        return int(info.get("level", 0) or 0)

    def _build_spells_step(self):
        self._ensure_spells_db_ready()
        self._spell_plan = self._compute_spell_plan()
        plan = self._spell_plan or {}
        if plan.get("auto_known_level") is not None:
            self._ensure_wizard_cantrips()

        primary = self._primary_color()
        hover = self._primary_hover()
        secondary = self._secondary_color()

        self._spell_advice_label = ctk.CTkLabel(
            self._content_frame,
            text=plan.get("advice", "Choose your starting spells."),
            text_color="#aaaaaa", wraplength=WIZARD_WRAPLENGTH, justify="left",
        )
        self._spell_advice_label.pack(anchor="w", pady=(0, 6))

        self._spell_status_label = ctk.CTkLabel(
            self._content_frame, text="",
            text_color=secondary,
            font=ctk.CTkFont(weight="bold"),
        )
        self._spell_status_label.pack(anchor="w", pady=(0, 8))

        self._spell_list_frame = ctk.CTkScrollableFrame(
            self._content_frame, height=300, fg_color=THEME_DARK_TRACK,
        )

        level_row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        level_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(level_row, text="Spell level:", width=90, anchor="w").pack(side="left")

        levels = sorted(set(plan.get("pick_known", {}).keys()) | set(plan.get("pick_prepared", {}).keys()))

        def select_spell_level(level):
            self._active_spell_level = level
            _refresh_highlighted_buttons(
                self._spell_level_buttons, level, primary, hover, unselected="#2F2F2F",
            )
            self._refresh_spell_list()

        for level in levels:
            btn = ctk.CTkButton(
                level_row, text=self._spell_level_label(level), width=110, height=28,
                fg_color=UNSELECTED_BTN, hover_color="#4a4a4a",
                command=lambda lv=level: select_spell_level(lv),
            )
            btn.pack(side="left", padx=4)
            self._spell_level_buttons[level] = btn

        if levels:
            self._active_spell_level = self._default_spell_level_for_plan(plan)
            select_spell_level(self._active_spell_level)

        if plan.get("auto_known_level") is not None:
            cantrip_count = len([
                s for s in self.state.get("known_spells", [])
                if self._spell_level_for_class(s, self.state["class_name"]) == 0
            ])
            ctk.CTkLabel(
                self._content_frame,
                text=f"Spellbook: all {cantrip_count} wizard cantrips added automatically.",
                text_color="#888888",
            ).pack(anchor="w", pady=(0, 4))

        search_row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        search_row.pack(fill="x", pady=(0, 4))
        self._spell_search_var = tk.StringVar()
        entry = ctk.CTkEntry(
            search_row, textvariable=self._spell_search_var, width=360,
            placeholder_text="Quick filter for selected level...",
        )
        entry.pack(side="left")
        self._spell_search_var.trace_add("write", lambda *_a: self._refresh_spell_list())
        ctk.CTkButton(
            search_row,
            text="Browse Spell Database",
            fg_color=secondary,
            hover_color=getattr(self.sheet, "secondary_hover_color", "#1f7f75"),
            command=self._open_spell_database_popup,
        ).pack(side="left", padx=(10, 0))

        self._spell_list_frame.pack(fill="both", expand=True, pady=(4, 0))

    def _spell_selection_context(self):
        plan = self._spell_plan or self._compute_spell_plan() or {}
        level = self._active_spell_level
        mode = plan.get("mode")
        cls = self.state["class_name"]

        if mode == "wizard" and level in plan.get("pick_known", {}):
            known_count = len([
                s for s in self.state.get("known_spells", [])
                if self._spell_level_for_class(s, cls) == level
            ])
            if known_count < plan["pick_known"][level]:
                return plan, level, "known", plan["pick_known"][level]

        if mode == "wizard" and level in plan.get("pick_prepared", {}):
            return plan, level, "prepared", plan["pick_prepared"][level]

        if mode == "spontaneous":
            return plan, level, "known", plan.get("pick_known", {}).get(level, 0)

        return plan, level, "prepared", plan.get("pick_prepared", {}).get(level, 0)

    def _spell_list_frame_alive(self):
        frame = getattr(self, "_spell_list_frame", None)
        if frame is None:
            return False
        try:
            return bool(frame.winfo_exists())
        except tk.TclError:
            return False

    def _refresh_spell_list(self):
        if not self._spell_list_frame_alive():
            return
        for w in self._spell_list_frame.winfo_children():
            w.destroy()
        self._spell_list_buttons = {}
        plan, level, context, limit = self._spell_selection_context()
        primary = self._primary_color()
        hover = self._primary_hover()
        cls = self.state["class_name"]
        selected = self._spells_selected_for_level(level, plan, context=context)
        selected_set = set(selected)
        search = (self._spell_search_var.get() if hasattr(self, "_spell_search_var") else "").strip().lower()

        if context == "prepared" and plan.get("mode") == "wizard":
            pool = list(self.state.get("known_spells") or [])
            spells = []
            for name in pool:
                if self._spell_level_for_class(name, cls) != level:
                    continue
                info = (getattr(self.sheet, "spells_db", {}) or {}).get(name, {})
                spells.append((name, info))
        else:
            spells = self._get_class_spells_for_level(cls, level)

        if search:
            spells = [
                (name, info) for name, info in spells
                if search in name.lower() or search in str(info.get("description", "")).lower()
            ]

        if context == "prepared":
            action = "Prepare"
        elif plan.get("mode") == "wizard" and level in plan.get("pick_known", {}):
            action = "Add to spellbook"
        else:
            action = "Know"
        if getattr(self, "_spell_status_label", None) is not None:
            try:
                self._spell_status_label.configure(
                    text=f"{action}: {len(selected)} / {limit} at {self._spell_level_label(level)}",
                )
            except tk.TclError:
                pass

        if not spells:
            ctk.CTkLabel(
                self._spell_list_frame,
                text=(
                    "No spells found for this level. Click Browse Spell Database "
                    "to search the full class spell list."
                ),
                text_color="#888888",
                wraplength=WIZARD_WRAPLENGTH,
                justify="left",
            ).pack(pady=20, padx=12, anchor="w")
            return

        for spell_name, info in spells[:150]:
            is_selected = spell_name in selected_set
            fg = primary if is_selected else UNSELECTED_BTN
            desc = str(info.get("description", ""))[:100]
            btn = ctk.CTkButton(
                self._spell_list_frame,
                text=f"{spell_name}\n{desc}",
                anchor="w", height=40,
                fg_color=fg, hover_color=hover,
                command=lambda n=spell_name, lv=level, ctx=context: self._toggle_spell(n, lv, ctx),
            )
            btn.pack(fill="x", padx=6, pady=2)
            self._spell_list_buttons[spell_name] = btn

    def _wizard_spell_context_for_level(self, spell_level):
        plan = self._spell_plan or self._compute_spell_plan() or {}
        mode = plan.get("mode")
        if mode == "spontaneous":
            return "known"
        if mode == "wizard":
            if spell_level in plan.get("pick_known", {}):
                known_at_level = [
                    s for s in self.state.get("known_spells", [])
                    if self._spell_level_for_class(s, self.state["class_name"]) == spell_level
                ]
                if len(known_at_level) < plan["pick_known"][spell_level]:
                    return "known"
            if spell_level in plan.get("pick_prepared", {}):
                return "prepared"
        return "prepared"

    def _wizard_spell_is_selected(self, spell_name, spell_level, context):
        plan = self._spell_plan or self._compute_spell_plan() or {}
        if context == "known":
            return spell_name in set(self.state.get("known_spells") or [])
        if context == "prepared":
            return any(
                e.get("spell") == spell_name
                and int(e.get("slot_level", e.get("base_level", -1))) == spell_level
                for e in self.state.get("prepared_spells") or []
            )
        return spell_name in self._spells_selected_for_level(spell_level, plan, context=context)

    def _wizard_add_spell_from_database(self, spell_name):
        cls = self.state["class_name"]
        spell_level = self._spell_level_for_class(spell_name, cls)
        context = self._wizard_spell_context_for_level(spell_level)
        plan = self._spell_plan or self._compute_spell_plan() or {}
        if plan.get("mode") == "wizard" and context == "prepared":
            if spell_name not in set(self.state.get("known_spells") or []):
                messagebox.showwarning(
                    "Character Wizard",
                    "Add this spell to your spellbook before preparing it.",
                    parent=self._wizard_spell_db_popup or self.popup,
                )
                return
        self._toggle_spell(spell_name, spell_level, context)
        self._refresh_spell_list()
        self._refresh_wizard_spell_db_list()

    def _wizard_spell_db_levels(self):
        plan = self._spell_plan or self._compute_spell_plan() or {}
        levels = sorted(set(plan.get("pick_known", {}).keys()) | set(plan.get("pick_prepared", {}).keys()))
        return levels or [0, 1]

    def _get_wizard_db_spells(self, selected_levels, search=""):
        cls = self.state["class_name"]
        search = str(search or "").strip().lower()
        seen = set()
        spells = []
        for level in sorted(selected_levels):
            for spell_name, info in self._get_class_spells_for_level(cls, level):
                if spell_name in seen:
                    continue
                seen.add(spell_name)
                if search:
                    desc = str(info.get("description", "")).lower()
                    if search not in spell_name.lower() and search not in desc:
                        continue
                spells.append((spell_name, info, level))
        spells.sort(key=lambda item: (item[2], item[0].lower()))
        return spells

    def _open_spell_database_popup(self):
        self._ensure_spells_db_ready()
        if self._wizard_spell_db_popup is not None:
            try:
                if self._wizard_spell_db_popup.winfo_exists():
                    self._wizard_spell_db_popup.focus_set()
                    return
            except tk.TclError:
                pass

        cls = self.state["class_name"]
        popup = ctk.CTkToplevel(self.popup)
        popup.title(f"Spell Database — {cls}")
        popup.geometry("920x620")
        popup.configure(fg_color=THEME_DARK_BG)
        popup.transient(self.popup)
        popup.grab_set()
        self._wizard_spell_db_popup = popup
        popup.protocol("WM_DELETE_WINDOW", lambda: self._close_wizard_spell_db_popup())

        ctk.CTkLabel(
            popup,
            text=f"Search {cls} spells and add them to your starting selection.",
            text_color="#aaaaaa",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(12, 6))

        level_row = ctk.CTkFrame(popup, fg_color="transparent")
        level_row.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(
            level_row, text="Spell levels:", font=ctk.CTkFont(weight="bold"),
        ).pack(side="left", padx=(0, 8))

        self._wizard_spell_db_level_vars = {}
        for level in self._wizard_spell_db_levels():
            var = tk.BooleanVar(value=True)
            self._wizard_spell_db_level_vars[level] = var
            ctk.CTkCheckBox(
                level_row,
                text=self._spell_level_label(level),
                variable=var,
                command=self._refresh_wizard_spell_db_list,
            ).pack(side="left", padx=4)

        search_row = ctk.CTkFrame(popup, fg_color="transparent")
        search_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(search_row, text="Search:").pack(side="left", padx=(0, 6))
        self._wizard_spell_db_search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(
            search_row, textvariable=self._wizard_spell_db_search_var, width=420,
            placeholder_text="Spell name or keyword...",
        )
        search_entry.pack(side="left", fill="x", expand=True)
        self._wizard_spell_db_search_var.trace_add(
            "write", lambda *_a: self._refresh_wizard_spell_db_list(),
        )

        self._wizard_spell_db_scroll = ctk.CTkScrollableFrame(
            popup, height=440, fg_color=THEME_DARK_TRACK,
        )
        self._wizard_spell_db_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        ctk.CTkButton(
            popup, text="Close", width=100, fg_color="#555555",
            command=self._close_wizard_spell_db_popup,
        ).pack(pady=(0, 12))

        self._refresh_wizard_spell_db_list()
        search_entry.focus_set()

    def _close_wizard_spell_db_popup(self):
        popup = getattr(self, "_wizard_spell_db_popup", None)
        self._wizard_spell_db_popup = None
        if popup is not None:
            try:
                popup.grab_release()
                popup.destroy()
            except tk.TclError:
                pass

    def _refresh_wizard_spell_db_list(self):
        scroll = getattr(self, "_wizard_spell_db_scroll", None)
        if scroll is None:
            return
        try:
            if not scroll.winfo_exists():
                return
        except tk.TclError:
            return

        for w in scroll.winfo_children():
            w.destroy()

        selected_levels = {
            level for level, var in getattr(self, "_wizard_spell_db_level_vars", {}).items()
            if var.get()
        }
        if not selected_levels:
            ctk.CTkLabel(
                scroll,
                text="Select one or more spell levels to browse the database.",
                text_color="#888888",
            ).pack(pady=24, padx=12, anchor="w")
            return

        search = (
            self._wizard_spell_db_search_var.get()
            if hasattr(self, "_wizard_spell_db_search_var") else ""
        )
        spells = self._get_wizard_db_spells(selected_levels, search)
        if not spells:
            ctk.CTkLabel(
                scroll,
                text="No spells match the selected levels and search text.",
                text_color="#888888",
            ).pack(pady=24, padx=12, anchor="w")
            return

        primary = self._primary_color()
        hover = self._primary_hover()
        secondary = self._secondary_color()

        for spell_name, info, spell_level in spells[:250]:
            context = self._wizard_spell_context_for_level(spell_level)
            selected = self._wizard_spell_is_selected(spell_name, spell_level, context)
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2, padx=4)

            desc = str(info.get("description", ""))[:120]
            classes = ", ".join(getattr(self.sheet, "_get_spell_classes", lambda _i: [])(info) or info.get("classes", []))
            ctk.CTkLabel(
                row,
                text=f"[{spell_level}] {spell_name}\n{classes}\n{desc}",
                anchor="w", justify="left", wraplength=620,
            ).pack(side="left", fill="x", expand=True, padx=(4, 8))

            btn_text = "Remove" if selected else "Add"
            btn_color = primary if selected else secondary
            ctk.CTkButton(
                row, text=btn_text, width=84, height=28,
                fg_color=btn_color,
                hover_color=hover if selected else getattr(self.sheet, "secondary_hover_color", "#1f7f75"),
                command=lambda n=spell_name: self._wizard_add_spell_from_database(n),
            ).pack(side="right", padx=4)

    def _toggle_spell(self, spell_name, spell_level, context):
        plan = self._spell_plan or self._compute_spell_plan() or {}
        if context == "known":
            known = list(self.state.get("known_spells") or [])
            same_level = [
                s for s in known
                if self._spell_level_for_class(s, self.state["class_name"]) == spell_level
            ]
            if spell_name in known:
                known.remove(spell_name)
            else:
                limit = plan.get("pick_known", {}).get(spell_level, 0)
                if len(same_level) >= limit:
                    messagebox.showwarning(
                        "Spells",
                        f"You can only know {limit} spell(s) at {self._spell_level_label(spell_level)}.",
                        parent=self.popup,
                    )
                    return
                known.append(spell_name)
            self.state["known_spells"] = sorted(known, key=str.lower)
        else:
            prepared = list(self.state.get("prepared_spells") or [])
            names_at_level = [
                e.get("spell") for e in prepared
                if int(e.get("slot_level", e.get("base_level", -1))) == spell_level
            ]
            if spell_name in names_at_level:
                prepared = [
                    e for e in prepared
                    if not (
                        e.get("spell") == spell_name
                        and int(e.get("slot_level", e.get("base_level", -1))) == spell_level
                    )
                ]
            else:
                limit = plan.get("pick_prepared", {}).get(spell_level, 0)
                if plan.get("mode") == "wizard" and spell_name not in self.state.get("known_spells", []):
                    messagebox.showwarning(
                        "Spells",
                        "You can only prepare spells that are in your spellbook.",
                        parent=self.popup,
                    )
                    return
                if len(names_at_level) >= limit:
                    messagebox.showwarning(
                        "Spells",
                        f"You can only prepare {limit} spell(s) at {self._spell_level_label(spell_level)}.",
                        parent=self.popup,
                    )
                    return
                prepared.append({
                    "spell": spell_name,
                    "metamagic": [],
                    "slot_level": spell_level,
                    "base_level": spell_level,
                    "prep_id": uuid.uuid4().hex[:8],
                })
            self.state["prepared_spells"] = prepared
        self._refresh_spell_list()

    def _validate_spells_step(self):
        plan = self._compute_spell_plan()
        if not plan:
            return
        cls = self.state["class_name"]
        for level, needed in (plan.get("pick_known") or {}).items():
            if plan.get("auto_known_level") == level:
                continue
            count = len([
                s for s in self.state.get("known_spells", [])
                if self._spell_level_for_class(s, cls) == level
            ])
            if count != needed:
                label = (
                    "for your spellbook"
                    if plan.get("mode") == "wizard"
                    else "to know"
                )
                raise ValueError(
                    f"Choose exactly {needed} {self._spell_level_label(level)} spell(s) "
                    f"{label} ({count} selected)."
                )
        for level, needed in (plan.get("pick_prepared") or {}).items():
            count = len([
                e for e in self.state.get("prepared_spells", [])
                if int(e.get("slot_level", e.get("base_level", -1))) == level
            ])
            if count != needed:
                raise ValueError(
                    f"Choose exactly {needed} spell(s) to prepare at {self._spell_level_label(level)} "
                    f"({count} selected)."
                )

    def _needs_invocation_step(self):
        if self.state.get("class_name") != "Warlock" or not _warlock_support:
            return False
        classes_db = getattr(self.sheet, "classes_db", {}) or {}
        pick_count = _warlock_support.invocations_known_count(1, classes_db=classes_db)
        self.state["invocation_pick_count"] = pick_count
        return pick_count > 0

    def _available_creation_invocations(self):
        if not _warlock_support:
            return []
        return _warlock_support.list_available_invocations(
            getattr(self.sheet, "invocations_db", {}) or {},
            1,
            self.state.get("known_invocations") or [],
        )

    def _build_invocations_step(self):
        pick_count = int(self.state.get("invocation_pick_count") or 0)
        picked = list(self.state.get("known_invocations") or [])
        available = self._available_creation_invocations()
        ctk.CTkLabel(
            self._content_frame,
            text=(
                f"Choose {pick_count} warlock invocation{'s' if pick_count != 1 else ''} "
                "for 1st level. Only invocations you qualify for are listed."
            ),
            text_color="#aaaaaa",
            wraplength=WIZARD_WRAPLENGTH,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        if not available:
            ctk.CTkLabel(
                self._content_frame,
                text=(
                    "No least invocations are available at 1st level. "
                    "You can choose your first invocation when you reach 2nd level."
                ),
                text_color=THEME_TEAL,
                wraplength=WIZARD_WRAPLENGTH,
                justify="left",
            ).pack(anchor="w", pady=(0, 8))
            return

        if picked:
            ctk.CTkLabel(
                self._content_frame,
                text="Selected: " + ", ".join(picked),
                text_color=THEME_TEAL,
                wraplength=WIZARD_WRAPLENGTH,
                justify="left",
            ).pack(anchor="w", pady=(0, 8))

        options = [""] + available
        row = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        combo = ctk.CTkComboBox(row, values=options, width=320)
        combo.set("")
        combo.pack(side="left", padx=(0, 8))

        def _add_invocation():
            name = combo.get().strip()
            if not name or name in picked:
                return
            if len(picked) >= pick_count:
                messagebox.showwarning(
                    "Invocation Limit",
                    f"You may only choose {pick_count} invocation(s) at 1st level.",
                    parent=self.popup,
                )
                return
            picked.append(name)
            self.state["known_invocations"] = picked
            self._render_step()

        def _remove_last():
            if picked:
                picked.pop()
                self.state["known_invocations"] = picked
                self._render_step()

        ctk.CTkButton(
            row, text="Add", width=80, fg_color=THEME_TEAL, command=_add_invocation,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row, text="Remove Last", width=110, fg_color="#666666", command=_remove_last,
        ).pack(side="left")

        list_frame = ctk.CTkScrollableFrame(
            self._content_frame, height=280, fg_color=THEME_DARK_TRACK,
        )
        list_frame.pack(fill="both", expand=True, pady=(8, 0))
        inv_db = getattr(self.sheet, "invocations_db", {}) or {}
        for name in available:
            info = inv_db.get(name, {})
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
        picked = list(self.state.get("known_invocations") or [])
        if not self._available_creation_invocations():
            return
        if len(picked) < pick_count:
            raise ValueError(
                f"Choose {pick_count} warlock invocation{'s' if pick_count != 1 else ''} "
                f"before continuing ({len(picked)} selected)."
            )

    def _level_one_skill_points(self):
        cls = self.state.get("class_name") or "Fighter"
        info = (getattr(self.sheet, "classes_db", {}) or {}).get(cls, {})
        sp_base = int(info.get("skill_points_per_level", 2) or 2)
        int_score = self._effective_ability("Intelligence")
        per_level = max(1, sp_base + _ability_mod(int_score))
        total = per_level * 4
        if self.state.get("race") == "Human":
            total += 4
        return total

    def _creation_skill_step(self, skill_key):
        cls = self.state.get("class_name") or ""
        step_fn = getattr(self.sheet, "_get_skill_rank_step", None)
        if step_fn:
            return step_fn(skill_key, leveling_class=cls)
        classes_db = getattr(self.sheet, "classes_db", {}) or {}
        return 1.0 if _is_class_skill(skill_key, cls, classes_db) else 0.5

    def _creation_skill_rank(self, skill_key):
        return float((self.state.get("skill_ranks") or {}).get(skill_key, 0) or 0)

    def _creation_max_skill_rank(self, skill_key):
        cls = self.state.get("class_name") or ""
        classes_db = getattr(self.sheet, "classes_db", {}) or {}
        cap = 4
        if _is_class_skill(skill_key, cls, classes_db):
            return float(cap)
        return float(cap // 2)

    def _format_creation_skill_rank(self, skill_key, rank):
        fmt = getattr(self.sheet, "_format_skill_rank_display", None)
        if fmt:
            return fmt(skill_key, rank)
        value = float(rank or 0)
        if value <= 0:
            return "0"
        if abs(value - round(value)) < 0.001:
            return str(int(round(value)))
        return f"{value:.1f}".rstrip("0").rstrip(".")

    def _skill_points_spent(self):
        spent = 0
        for skill_key, rank in (self.state.get("skill_ranks") or {}).items():
            rank = float(rank or 0)
            if rank <= 0:
                continue
            step = self._creation_skill_step(skill_key)
            if step > 0:
                spent += int(round(rank / step))
        return spent

    def _update_skill_budget_display(self):
        if not self._skill_budget_label:
            return
        budget = self._level_one_skill_points()
        spent = self._skill_points_spent()
        remaining = budget - spent
        color = "#d9534f" if remaining < 0 else self._secondary_color()
        self._skill_budget_label.configure(
            text=f"Skill points remaining: {remaining}  (spent {spent} / {budget})",
            text_color=color,
        )

    def _refresh_creation_skill_row(self, skill_key):
        rank_lbl = self._skill_rank_labels.get(skill_key)
        if rank_lbl:
            display = self._format_creation_skill_rank(
                skill_key, self._creation_skill_rank(skill_key),
            )
            try:
                rank_lbl.configure(text=display)
            except tk.TclError:
                pass
        minus_btn = self._skill_minus_buttons.get(skill_key)
        plus_btn = self._skill_plus_buttons.get(skill_key)
        rank = self._creation_skill_rank(skill_key)
        step = self._creation_skill_step(skill_key)
        budget = self._level_one_skill_points()
        spent = self._skill_points_spent()
        max_rank = self._creation_max_skill_rank(skill_key)
        can_minus = rank >= step - 0.001
        can_plus = spent < budget and rank + step <= max_rank + 0.001
        for btn, enabled in ((minus_btn, can_minus), (plus_btn, can_plus)):
            if not btn:
                continue
            try:
                btn.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass

    def _adjust_creation_skill_rank(self, skill_key, direction):
        """direction +1 spends one skill point; -1 refunds one."""
        step = self._creation_skill_step(skill_key)
        ranks = self.state.setdefault("skill_ranks", {})
        current = float(ranks.get(skill_key, 0) or 0)
        if direction > 0:
            if self._skill_points_spent() >= self._level_one_skill_points():
                return
            if current + step > self._creation_max_skill_rank(skill_key) + 0.001:
                return
            ranks[skill_key] = round((current + step) * 2) / 2.0
        else:
            if current < step - 0.001:
                return
            new_rank = round((current - step) * 2) / 2.0
            if new_rank <= 0:
                ranks.pop(skill_key, None)
            else:
                ranks[skill_key] = new_rank
        self._update_skill_budget_display()
        self._refresh_creation_skill_row(skill_key)

    def _build_skills_step(self):
        budget = self._level_one_skill_points()
        ctk.CTkLabel(
            self._content_frame,
            text=(
                f"Level 1 skill points available: {budget} "
                f"(class + Int mod, ×4 at 1st level"
                f"{'; +4 human' if self.state.get('race') == 'Human' else ''}). "
                "Use +/− to spend 1 point per click; class skills gain 1 rank, "
                "cross-class skills gain 0.5 rank."
            ),
            text_color="#aaaaaa", wraplength=WIZARD_WRAPLENGTH, justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self._skill_budget_label = ctk.CTkLabel(
            self._content_frame, text=f"Remaining: {budget}",
            text_color=self._secondary_color(),
            font=ctk.CTkFont(weight="bold"),
        )
        self._skill_budget_label.pack(anchor="w", pady=(0, 8))

        scroll = ctk.CTkScrollableFrame(self._content_frame, height=380, fg_color=THEME_DARK_TRACK)
        scroll.pack(fill="both", expand=True)

        classes_db = getattr(self.sheet, "classes_db", {}) or {}
        class_name = self.state.get("class_name") or ""
        for skill_key, ability_key, display_name in _iter_wizard_skill_rows(self.sheet):
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)
            is_class = _is_class_skill(skill_key, class_name, classes_db)
            label = f"{display_name}*" if is_class else display_name
            ctk.CTkLabel(row, text=label, width=180, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=ability_key, width=36, anchor="center").pack(side="left", padx=(4, 8))

            minus_btn = ctk.CTkButton(
                row, text="−", width=28, height=26,
                fg_color="#444444",
                command=lambda key=skill_key: self._adjust_creation_skill_rank(key, -1),
            )
            minus_btn.pack(side="left", padx=(0, 4))
            self._skill_minus_buttons[skill_key] = minus_btn

            rank_lbl = ctk.CTkLabel(
                row,
                text=self._format_creation_skill_rank(
                    skill_key, self._creation_skill_rank(skill_key),
                ),
                width=48,
                anchor="center",
            )
            rank_lbl.pack(side="left")
            self._skill_rank_labels[skill_key] = rank_lbl

            plus_btn = ctk.CTkButton(
                row, text="+", width=28, height=26,
                fg_color="#444444",
                command=lambda key=skill_key: self._adjust_creation_skill_rank(key, 1),
            )
            plus_btn.pack(side="left", padx=(4, 0))
            self._skill_plus_buttons[skill_key] = plus_btn

            self._refresh_creation_skill_row(skill_key)

        self._update_skill_budget_display()

    def _build_languages_step(self):
        race = self.state.get("race") or ""
        races = getattr(self.sheet, "races", {}) or {}
        needed = self._bonus_language_pick_count()
        automatic = racial_automatic_languages(race, races)
        options = bonus_language_options(race, races)
        known = set(automatic)

        if needed <= 0:
            ctk.CTkLabel(
                self._content_frame,
                text=(
                    "Your Intelligence does not grant any bonus languages at 1st level. "
                    f"You already speak: {', '.join(automatic) if automatic else '—'}."
                ),
                text_color="#aaaaaa",
                wraplength=WIZARD_WRAPLENGTH,
                justify="left",
            ).pack(anchor="w", pady=8)
            self.state["bonus_language_choices"] = []
            return

        subtitle = (
            f"Pick {needed} bonus language{'s' if needed != 1 else ''} from your race's options. "
            f"Automatic languages ({', '.join(automatic)}) are already known and cannot be selected again."
        )
        self._language_picker = build_language_picker(
            self._content_frame,
            title="Intelligence Bonus Languages",
            subtitle=subtitle,
            languages=options,
            known_languages=known,
            selected=list(self.state.get("bonus_language_choices") or []),
            max_picks=needed,
            on_change=lambda picks: self.state.__setitem__("bonus_language_choices", list(picks)),
            wraplength=WIZARD_WRAPLENGTH,
        )

    def _build_speak_language_step(self):
        needed = self._creation_speak_language_ranks()
        known = self._wizard_known_languages()
        options = speak_language_options(include_secret=False)
        subtitle = (
            f"Each rank in Speak Language grants one additional language. "
            f"Choose {needed} language{'s' if needed != 1 else ''} (any standard language). "
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

    def _init_equipment_gold(self):
        if self.state.get("starting_gold"):
            return
        cls = self.state.get("class_name") or "Fighter"
        cfg = STARTING_GOLD.get(cls) or STARTING_GOLD["Fighter"]
        rolls = [random.randint(1, cfg["sides"]) for _ in range(cfg["dice"])]
        dice_sum = sum(rolls)
        multiplier = int(cfg.get("multiplier", 1) or 1)
        gold = int(dice_sum * multiplier)
        self.state["starting_gold"] = gold
        self.state["gold_remaining"] = gold

        show_popup = getattr(self.sheet, "_show_local_dice_roll_popup", None)
        if show_popup:
            formula = cfg.get("label") or f"{cfg['dice']}d{cfg['sides']}"
            roll_result = {
                "label": "Starting Gold",
                "formula": formula,
                "groups": [{
                    "display": f"{cfg['dice']}d{cfg['sides']}",
                    "rolls": rolls,
                    "modifier": 0,
                    "total": dice_sum,
                    "min_total": cfg["dice"],
                    "max_total": cfg["dice"] * cfg["sides"],
                }],
                "result_text": str(dice_sum),
            }
            detail = f"{dice_sum} gp" if multiplier == 1 else f"{dice_sum} × {multiplier} = {gold} gp"
            try:
                show_popup(roll_result, ammo_detail=detail)
            except Exception:
                pass

        if not self.state.get("auto_gear_applied"):
            self._apply_auto_caster_gear()
            self.state["auto_gear_applied"] = True

    def _resolve_gear_item_name(self, item_name, gear_db):
        if item_name in gear_db:
            return item_name
        target = str(item_name or "").strip().lower()
        for name in gear_db:
            if str(name).strip().lower() == target:
                return name
        if "spellbook" in target and "wizard" in target:
            for name in gear_db:
                lowered = str(name).lower()
                if "spellbook" in lowered and "wizard" in lowered:
                    return name
        if "musical instrument" in target:
            for name in gear_db:
                lowered = str(name).lower()
                if "musical instrument" in lowered and "common" in lowered:
                    return name
        return item_name

    def _inventory_has_gear(self, item_name):
        resolved = self._resolve_gear_item_name(
            item_name, getattr(self.sheet, "adventuring_gear_db", {}) or {},
        )
        target = str(resolved).strip().lower()
        for entry in self.state.get("inventory") or []:
            if str(entry.get("name", "")).strip().lower() == target:
                return True
        return False

    def _add_free_gear(self, item_name, gear_db, inventory):
        resolved = self._resolve_gear_item_name(item_name, gear_db)
        if self._inventory_has_gear(resolved):
            return
        info = gear_db.get(resolved) or {}
        if not info:
            return
        inventory.append(self._inventory_entry(resolved, info))

    def _apply_auto_caster_gear(self):
        cls = self.state.get("class_name") or ""
        if not self._needs_spell_step() and cls not in {"Cleric", "Paladin", "Bard"}:
            return
        gear_db = getattr(self.sheet, "adventuring_gear_db", {}) or {}
        inventory = self.state.setdefault("inventory", [])
        if self._needs_spell_step() or cls in {"Cleric", "Paladin"}:
            for item_name in AUTO_CASTER_GEAR:
                if self._inventory_has_gear(item_name):
                    continue
                resolved = self._resolve_gear_item_name(item_name, gear_db)
                info = gear_db.get(resolved) or {}
                cost = float(info.get("cost", info.get("value", 5)) or 5)
                if self.state["gold_remaining"] >= cost:
                    self.state["gold_remaining"] -= int(cost)
                    inventory.append(self._inventory_entry(resolved, info))
        if cls == "Wizard":
            for item_name in AUTO_WIZARD_GEAR:
                self._add_free_gear(item_name, gear_db, inventory)
        if self.state.get("class_name") in {"Cleric", "Paladin"}:
            for item_name in AUTO_CLERIC_GEAR:
                if self._inventory_has_gear(item_name):
                    continue
                resolved = self._resolve_gear_item_name(item_name, gear_db)
                info = gear_db.get(resolved) or {}
                cost = float(info.get("cost", info.get("value", 1)) or 1)
                if self.state["gold_remaining"] >= cost:
                    self.state["gold_remaining"] -= int(cost)
                    inventory.append(self._inventory_entry(resolved, info))
        if cls == "Bard":
            for item_name in AUTO_BARD_GEAR:
                if self._inventory_has_gear(item_name):
                    continue
                resolved = self._resolve_gear_item_name(item_name, gear_db)
                info = gear_db.get(resolved) or {}
                cost = float(info.get("cost", info.get("value", 5)) or 5)
                if self.state["gold_remaining"] >= cost:
                    self.state["gold_remaining"] -= int(cost)
                    inventory.append(self._inventory_entry(resolved, info))

    def _inventory_entry(self, name, info):
        weight = info.get("weight", 0)
        if hasattr(self.sheet, "_parse_weight_to_lbs"):
            weight = self.sheet._parse_weight_to_lbs(weight)
        cost = info.get("cost", info.get("value", 0))
        if hasattr(self.sheet, "_parse_cost_to_gp"):
            cost = self.sheet._parse_cost_to_gp(cost)
        return {
            "name": name,
            "quantity": 1,
            "weight": weight,
            "value": cost,
            "location": "person",
            "inventory_id": str(random.randint(100000000, 999999999)),
        }

    def _build_equip_header(self, subtitle):
        self._init_equipment_gold()
        cls = self.state.get("class_name") or ""
        cfg = STARTING_GOLD.get(cls, {})
        ctk.CTkLabel(
            self._content_frame,
            text=(
                f"{subtitle}\n"
                f"Starting gold ({cfg.get('label', '')}): {self.state['starting_gold']} gp  |  "
                f"Remaining: {self.state['gold_remaining']} gp"
            ),
            text_color="#aaaaaa", wraplength=WIZARD_WRAPLENGTH, justify="left",
        ).pack(anchor="w", pady=(0, 8))
        if self._needs_spell_step() or self.state.get("class_name") in {"Cleric", "Paladin", "Wizard", "Bard"}:
            auto_notes = []
            if self._needs_spell_step() or cls in {"Cleric", "Paladin"}:
                auto_notes.append("Spell component pouch")
            if cls == "Wizard":
                gear_db = getattr(self.sheet, "adventuring_gear_db", {}) or {}
                spellbook = self._resolve_gear_item_name(AUTO_WIZARD_GEAR[0], gear_db)
                auto_notes.append(f"{spellbook} (free)")
            if cls in {"Cleric", "Paladin"}:
                auto_notes.append("Holy symbol, wooden")
            if cls == "Bard":
                gear_db = getattr(self.sheet, "adventuring_gear_db", {}) or {}
                instrument = self._resolve_gear_item_name(AUTO_BARD_GEAR[0], gear_db)
                auto_notes.append(f"{instrument} (auto-purchase)")
            ctk.CTkLabel(
                self._content_frame,
                text="Auto-added: " + "; ".join(auto_notes),
                text_color="#888888", wraplength=WIZARD_WRAPLENGTH, justify="left",
            ).pack(anchor="w", pady=(0, 6))

    def _buy_item(self, name, info):
        cost = float(info.get("cost", info.get("value", 0)) or 0)
        if hasattr(self.sheet, "_parse_cost_to_gp"):
            cost = self.sheet._parse_cost_to_gp(cost)
        cost = int(cost)
        if self.state["gold_remaining"] < cost:
            messagebox.showwarning("Buy Item", "Not enough gold.", parent=self.popup)
            return
        self.state["gold_remaining"] -= cost
        self.state.setdefault("inventory", []).append(self._inventory_entry(name, info))
        self._render_step()

    def _build_shop(self, items):
        self._shop_scroll = ctk.CTkScrollableFrame(
            self._content_frame, height=400, fg_color=THEME_DARK_TRACK,
        )
        self._shop_scroll.pack(fill="both", expand=True)
        for name, info in sorted(items, key=lambda x: x[0].lower()):
            row = ctk.CTkFrame(self._shop_scroll, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)
            cost = info.get("cost", info.get("value", 0))
            weight = info.get("weight", 0)
            ctk.CTkLabel(
                row,
                text=f"{name}  —  {cost} gp, {weight} lb",
                anchor="w", width=480,
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                row, text="Buy", width=60, fg_color="#2e7d32",
                command=lambda n=name, i=info: self._buy_item(n, i),
            ).pack(side="right", padx=4)

    def _build_equip_weapons_step(self):
        self._build_equip_header("Buy weapons for your new character.")
        db = getattr(self.sheet, "mundane_weapons_db", {}) or {}
        self._build_shop(list(db.items()))

    def _build_equip_armor_step(self):
        self._build_equip_header("Buy armor and shields.")
        db = getattr(self.sheet, "mundane_armors_shields_db", {}) or {}
        self._build_shop(list(db.items()))

    def _build_equip_gear_step(self):
        self._build_equip_header("Buy adventuring gear.")
        db = getattr(self.sheet, "adventuring_gear_db", {}) or {}
        self._build_shop(list(db.items()))

    def _collect_step_data(self):
        step = self._current_step()
        if step == "class":
            if not self.state.get("class_name"):
                raise ValueError("Select a class.")
        elif step == "race":
            if self.state["race"] not in (getattr(self.sheet, "races", {}) or {}):
                raise ValueError("Select a valid race.")
        elif step == "identity":
            name = getattr(self, "_name_var", tk.StringVar()).get().strip()
            if not name:
                raise ValueError("Enter a character name.")
            self.state["name"] = name
            align = getattr(self, "_alignment_var", tk.StringVar()).get().strip()
            if align in self._restricted_alignments():
                raise ValueError("That alignment is not allowed for your class.")
            self.state["alignment"] = align
        elif step == "abilities":
            method = self.state.get("ability_method")
            if method in ("roll", "standard_array"):
                assignments = self.state.get("ability_assignments") or {}
                if len(assignments) != len(ABILITY_NAMES):
                    raise ValueError("Assign every ability score from the pool using the Base dropdowns.")
                assigned_scores = []
                abilities = {}
                for ab in ABILITY_NAMES:
                    if ab not in assignments:
                        raise ValueError(f"Assign a score to {ab}.")
                    score = int(assignments[ab])
                    if score < 3 or score > 18:
                        raise ValueError(f"{ab} must be between 3 and 18 during creation.")
                    assigned_scores.append(score)
                    abilities[ab] = score
                pool = list(self.state.get("ability_score_pool") or [])
                if sorted(assigned_scores) != sorted(pool):
                    raise ValueError("Each rolled or array value must be assigned exactly once.")
                self.state["abilities"] = abilities
            else:
                abilities = {}
                for ab, var in getattr(self, "_ability_vars", {}).items():
                    try:
                        score = int(var.get() or POINT_BUY_MIN_SCORE)
                    except ValueError:
                        raise ValueError(f"{ab} must be a whole number.")
                    if score < 3 or score > 18:
                        raise ValueError(f"{ab} must be between 3 and 18 during creation.")
                    abilities[ab] = score
                if method == "point_buy" and self._point_buy_spent() > POINT_BUY_POOL:
                    raise ValueError(
                        f"Point buy exceeds {POINT_BUY_POOL} points. Lower a score or use another method.",
                    )
                self.state["abilities"] = abilities
        elif step == "feats":
            selected = False
            for ui_idx in range(len(self._feat_slot_labels())):
                combo = self._feat_combos.get(ui_idx)
                val = combo.get().strip() if combo else ""
                self._set_feat_slot(ui_idx, val)
                entry = self._feat_spec_entries.get(ui_idx)
                if entry is not None:
                    self._set_wizard_feat_spec(ui_idx, entry.get())
                base, _legacy = self.sheet._normalize_feat_selection(val)
                if base:
                    selected = True
                if base and self.sheet._feat_needs_spec_picker(base):
                    spec = self._get_wizard_feat_spec(ui_idx)
                    if not spec:
                        config = self.sheet._get_weapon_feat_spec_config(base) or {}
                        need = str(config.get("label", "a weapon") or "a weapon").strip().rstrip(":")
                        raise ValueError(f"{base} requires {need.lower()} — fill in the field beside it.")
                    if self.sheet._feat_needs_damage_type_spec(base):
                        normalized = self.sheet._normalize_damage_type_spec(spec)
                        if not normalized:
                            raise ValueError(
                                f"{base} requires Slashing, Piercing, or Bludgeoning.",
                            )
                        self._set_wizard_feat_spec(ui_idx, normalized)
            if not selected:
                raise ValueError("Select at least one feat.")
        elif step == "skills":
            spent = self._skill_points_spent()
            budget = self._level_one_skill_points()
            if spent > budget:
                raise ValueError(f"Too many skill points spent ({spent} spent, {budget} available).")
        elif step == "languages":
            needed = self._bonus_language_pick_count()
            picks = list(self.state.get("bonus_language_choices") or [])
            if self._language_picker:
                picks = self._language_picker["get_selected"]()
                self.state["bonus_language_choices"] = picks
            if needed > 0 and len(picks) != needed:
                raise ValueError(
                    f"Select exactly {needed} bonus language{'s' if needed != 1 else ''} "
                    f"({len(picks)} selected).",
                )
            if needed <= 0:
                self.state["bonus_language_choices"] = []
        elif step == "speak_language":
            needed = self._creation_speak_language_ranks()
            picks = list(self.state.get("speak_language_choices") or [])
            if self._speak_language_picker:
                picks = self._speak_language_picker["get_selected"]()
                self.state["speak_language_choices"] = picks
            if needed > 0 and len(picks) != needed:
                raise ValueError(
                    f"Select exactly {needed} Speak Language choice{'s' if needed != 1 else ''} "
                    f"({len(picks)} selected).",
                )
        elif step == "spells":
            if plan := self._compute_spell_plan():
                if plan.get("auto_known_level") is not None:
                    self._ensure_wizard_cantrips()
            self._validate_spells_step()
        elif step == "invocations":
            self._validate_invocations_step()

    def _go_next(self):
        try:
            self._collect_step_data()
        except ValueError as exc:
            messagebox.showwarning("Character Wizard", str(exc), parent=self.popup)
            return
        order = self._get_step_order()
        if self._step_index >= len(order) - 1:
            self._finish()
            return
        self._step_index += 1
        self._render_step()

    def _go_back(self):
        if self._step_index <= 0:
            return
        try:
            self._collect_step_data()
        except ValueError:
            pass
        self._step_index -= 1
        self._render_step()

    def _cancel(self):
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass
        try:
            self.popup.destroy()
        except tk.TclError:
            pass

    def _finish(self):
        if self._needs_spell_step():
            self._ensure_wizard_cantrips()
        payload = self._build_character_payload()
        try:
            self.popup.destroy()
        except tk.TclError:
            pass
        if self.on_complete:
            self.on_complete(payload)

    def _build_character_payload(self):
        cls = self.state["class_name"]
        race = self.state["race"]
        race_data = (getattr(self.sheet, "races", {}) or {}).get(race, {})
        classes_db = getattr(self.sheet, "classes_db", {}) or {}
        hd_sides = _parse_hit_die_sides(classes_db.get(cls, {}).get("hit_die"))
        if hd_sides <= 0:
            hd_sides = 8

        skill_budget = self._level_one_skill_points()
        abilities = {}
        for ab in ABILITY_NAMES:
            base = self._resolved_ability_score(ab)
            racial = int(race_data.get(ABILITY_RACE_KEYS[ab], 0) or 0)
            total = base + racial
            abilities[ab] = {"base": base, "racial": racial, "enh": 0, "misc": 0, "total": total}

        skill_rank_data = {}
        skill_rank_costs = {}
        classes_db = getattr(self.sheet, "classes_db", {}) or {}
        for skill_key, rank in (self.state.get("skill_ranks") or {}).items():
            rank = float(rank or 0)
            if rank > 0:
                skill_rank_data[f"skill_{skill_key}_rank"] = self._format_creation_skill_rank(
                    skill_key, rank,
                )
                skill_rank_costs[skill_key] = (
                    1 if _is_class_skill(skill_key, cls, classes_db) else 2
                )

        general_feats = self._general_feats_for_sheet()

        coins = {"PP": 0, "GP": 0, "EP": 0, "SP": 0, "CP": 0}
        remaining = int(self.state.get("gold_remaining", 0) or 0)
        coins["GP"] = max(0, remaining)
        level_adj = int(race_data.get("level_adjustment", 0) or 0)
        con_mod = _ability_mod(abilities["Constitution"]["total"])
        starting_max_hp = max(1, hd_sides + con_mod)

        return {
            "name": self.state["name"],
            "alignment": self.state["alignment"],
            "race": race,
            "size": race_data.get("size", "Medium"),
            "classes": [cls, "None", "None"],
            "levels": [1, 0, 0],
            "class_0": cls,
            "class_1": "None",
            "class_2": "None",
            "level_0": 1,
            "level_1": 0,
            "level_2": 0,
            "abilities": abilities,
            "general_feats": general_feats,
            "human_bonus_feat": self.state.get("human_bonus_feat") or "",
            "feat_specs": copy.deepcopy(self.state.get("feat_specs") or {}),
            "known_spells": list(self.state.get("known_spells") or []),
            "prepared_spells": copy.deepcopy(self.state.get("prepared_spells") or []),
            "known_invocations": list(self.state.get("known_invocations") or []),
            "current_hp": starting_max_hp,
            "health": {
                "hit_dice_rolls": [hd_sides],
                "skill_points_per_level": [skill_budget],
                "current_hp": starting_max_hp,
                "temp_hp": 0,
                "level_adjustment": level_adj,
            },
            "inventory": list(self.state.get("inventory") or []),
            "coins": {
                "person": copy.deepcopy(coins),
                "container": {"PP": 0, "GP": 0, "EP": 0, "SP": 0, "CP": 0},
                "banked": {"PP": 0, "GP": 0, "EP": 0, "SP": 0, "CP": 0},
            },
            "skill_rank_data": skill_rank_data,
            "skill_rank_costs": skill_rank_costs,
            "bonus_language_choices": list(self.state.get("bonus_language_choices") or []),
            "bonus_languages_configured": True,
            "speak_language_languages": list(self.state.get("speak_language_choices") or []),
            "wizard_class": cls,
            "wizard_starting_gold": self.state.get("starting_gold", 0),
        }