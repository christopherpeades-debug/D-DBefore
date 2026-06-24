"""Mount and riding support for the D&D character sheet."""

import copy
import json
import os
import re
import sys

import customtkinter as ctk
from tkinter import simpledialog
import dark_dialog as messagebox

THEME_ORANGE = "#c77626"

MOUNT_BTN_ICON = "\u2229"  # ∩ horseshoe shape
MOUNT_RIDING_LAND_ICON = "\u2229"
MOUNT_RIDING_RUN_ICON = "\U0001f40e"  # 🐎

RIDE_TASKS = (
    ("Guide with knees", 5, "Start of turn; fail = only one hand free."),
    ("Stay in saddle", 5, "Reaction when mount rears/bolts or you take damage."),
    ("Fight with warhorse", 10, "Free action; war-trained mount attacks in battle."),
    ("Cover", 15, "Reaction; use mount as cover (no attack/spell while covered)."),
    ("Soft fall", 15, "Reaction when falling off mount; fail = 1d6 damage."),
    ("Leap", 15, "Part of mount movement; fail = fall off (1d6+)."),
    ("Spur mount", 15, "Move action; +10 ft. for 1 round (mount takes damage)."),
    ("Control mount in battle", 20, "Move action; untrained mount in battle."),
    ("Fast mount or dismount", 20, "Free action; fail = move action instead."),
)

_MOUNT_ATTACK_SEGMENT_RE = re.compile(
    r"(?:(\d+)\s+)?"
    r"([\w\s]+?)\s+"
    r"([+-]?\d+)\s+"
    r"(melee|ranged)\s+"
    r"\(([^)]+)\)",
    re.IGNORECASE,
)

PALADIN_MOUNT_ABILITY_INFO = {
    "Empathic Link": "Paladin and mount communicate telepathically (emotions and simple ideas) out to 1 mile.",
    "Improved Evasion": "On a successful Reflex save against an area effect that normally deals half damage, mount takes no damage; on failed save, takes half.",
    "Share Spells": "Paladin may cast personal-range spells on the mount (within 5 ft) as if the mount were the paladin.",
    "Speak with Master": "Mount and paladin can speak verbally using a language the paladin knows.",
    "Blood Bond": "If an attack would not normally harm the mount, the paladin may substitute her own hit points instead (within 5 ft).",
    "Spell Resistance": "Mount gains spell resistance equal to the paladin's level + 5.",
    "Devotion": "+4 morale bonus on Will saves against enchantment spells and effects.",
}

RIDE_RULES_SECTIONS = (
    (
        "Ride (Dex)",
        "If you attempt to ride a creature ill suited as a mount, you take a -5 penalty on Ride checks.\n\n"
        "Typical riding actions do not require checks. You can saddle, mount, ride, and dismount without a problem.",
    ),
    (
        "Special",
        "Bareback riding: -5 penalty on Ride checks.\n"
        "Military saddle: +2 circumstance bonus on Ride checks related to staying in the saddle.\n"
        "Animal Affinity feat: +2 bonus on Ride checks.\n"
        "Handle Animal 5+ ranks: +2 synergy bonus on Ride checks.",
    ),
    (
        "Action",
        "Mounting or dismounting normally is a move action. Other checks are a move action, "
        "free action, or no action, as noted for each task.",
    ),
)


class MountsMixin:
    """Mixin providing mount selection, stat block, riding rules, and movement integration."""

    def _mounts_data_paths(self):
        if getattr(sys, "frozen", False):
            bundle_dir = sys._MEIPASS
            app_dir = os.path.dirname(sys.executable)
        else:
            bundle_dir = os.path.dirname(os.path.abspath(__file__))
            app_dir = bundle_dir
        return [
            os.path.join(app_dir, "mounts.json"),
            os.path.join(bundle_dir, "mounts.json"),
        ]

    def load_mounts_db(self):
        paths = self._mounts_data_paths()
        for path in paths:
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    self.MOUNTS = json.load(f)
                print(f"Loaded {len(self.MOUNTS)} mounts from {path}")
                return
            except Exception as e:
                print(f"Error reading mounts.json at {path}: {e}")
        print("No mounts.json found. Mount selection will be empty.")
        self.MOUNTS = {}

    def _has_mount(self):
        mount = self.data.get("mount", {})
        base = (mount.get("base") or "").strip()
        return bool(base and base in getattr(self, "MOUNTS", {}))

    def _get_mount_attack_string(self):
        """Attack line from mount popup or base stat block."""
        if not self._has_mount():
            return ""
        mount = self._get_mount_data()
        stats = mount.get("stats", {}) or {}
        return str(mount.get("attack") or stats.get("attack") or "").strip()

    def _get_mount_summary_name(self):
        if not self._has_mount():
            return ""
        mount = self._get_mount_data()
        return str(mount.get("name") or mount.get("base") or "Mount").strip()

    def _parse_mount_damage_in_parens(self, dmg_raw):
        text = str(dmg_raw or "").strip().replace("*", "")
        match = re.match(r"^(\d+d\d+)([+-]\d+)?", text, re.IGNORECASE)
        if not match:
            return "1d4", 0
        die = match.group(1).lower()
        dmg_mod = int(match.group(2) or 0)
        return die, dmg_mod

    def _parse_mount_attack_components(self, attack_str):
        """Parse SRD-style mount attack lines into structured attack parts."""
        text = str(attack_str or "").strip()
        if not text:
            return []
        components = []
        for segment in re.split(r"\s+and\s+", text, flags=re.IGNORECASE):
            segment = segment.strip()
            if not segment:
                continue
            match = _MOUNT_ATTACK_SEGMENT_RE.search(segment)
            if not match:
                continue
            die, dmg_mod = self._parse_mount_damage_in_parens(match.group(5))
            components.append({
                "name": match.group(2).strip().title(),
                "count": max(1, int(match.group(1) or 1)),
                "attack_bonus": int(match.group(3)),
                "reach": str(match.group(4) or "melee").strip().lower(),
                "damage_die": die,
                "damage_mod": dmg_mod,
            })
        return components

    def _format_mount_attack_bonus_display(self, components):
        bonuses = []
        for comp in components or []:
            for _ in range(int(comp.get("count", 1) or 1)):
                bonuses.append(self._format_modifier(int(comp.get("attack_bonus", 0) or 0)))
        if not bonuses:
            return ""
        return f"[{'/'.join(bonuses)}]"

    def _format_mount_damage_display(self, components):
        parts = []
        seen = set()
        for comp in components or []:
            die = str(comp.get("damage_die") or "1d4")
            mod = int(comp.get("damage_mod", 0) or 0)
            text = f"{die}{self._format_modifier(mod)}" if mod else die
            key = (comp.get("name"), text)
            if key in seen:
                continue
            seen.add(key)
            parts.append(text)
        return " ".join(parts)

    def _build_talespire_mount_attack_roll(self):
        mount_name = self._get_mount_summary_name() or "Mount"
        components = self._parse_mount_attack_components(self._get_mount_attack_string())
        if not components:
            return self._build_talespire_mount_fallback_roll(attack_only=True)
        groups = []
        for comp in components:
            bonus = int(comp.get("attack_bonus", 0) or 0)
            for _ in range(int(comp.get("count", 1) or 1)):
                groups.append(self._format_talespire_dice_with_modifier("1d20", bonus))
        return self._format_talespire_roll(mount_name, groups)

    def _build_talespire_mount_damage_roll(self):
        mount_name = self._get_mount_summary_name() or "Mount"
        components = self._parse_mount_attack_components(self._get_mount_attack_string())
        if not components:
            return self._build_talespire_mount_fallback_roll(damage_only=True)
        groups = []
        seen = set()
        for comp in components:
            label = self._sanitize_talespire_label(str(comp.get("name") or "Attack"))
            dmg = self._format_talespire_dice_with_modifier(
                comp.get("damage_die", "1d4"),
                int(comp.get("damage_mod", 0) or 0),
            )
            group = f"{label}:{dmg}"
            if group in seen:
                continue
            seen.add(group)
            groups.append(group)
        return self._format_talespire_roll(f"{mount_name} Damage", groups)

    def _build_talespire_mount_full_roll(self):
        mount_name = self._get_mount_summary_name() or "Mount"
        components = self._parse_mount_attack_components(self._get_mount_attack_string())
        if not components:
            return self._build_talespire_mount_fallback_roll()
        groups = []
        seen_damage = set()
        for comp in components:
            bonus = int(comp.get("attack_bonus", 0) or 0)
            for _ in range(int(comp.get("count", 1) or 1)):
                groups.append(self._format_talespire_dice_with_modifier("1d20", bonus))
        for comp in components:
            label = self._sanitize_talespire_label(str(comp.get("name") or "Attack"))
            dmg = self._format_talespire_dice_with_modifier(
                comp.get("damage_die", "1d4"),
                int(comp.get("damage_mod", 0) or 0),
            )
            group = f"{label}:{dmg}"
            if group in seen_damage:
                continue
            seen_damage.add(group)
            groups.append(group)
        return self._format_talespire_roll(mount_name, groups)

    def _build_talespire_mount_fallback_roll(self, *, attack_only=False, damage_only=False):
        """Best-effort Talespire roll when the mount attack line is not fully structured."""
        text = self._get_mount_attack_string()
        mount_name = self._get_mount_summary_name() or "Mount"
        if not text:
            return None
        groups = []
        atk_match = re.search(r"([+-]?\d+)\s+(?:melee|ranged)", text, re.IGNORECASE)
        dmg_match = re.search(r"\((\d+d\d+)([+-]\d+)?", text, re.IGNORECASE)
        if atk_match and not damage_only:
            groups.append(
                self._format_talespire_dice_with_modifier("1d20", int(atk_match.group(1))),
            )
        if dmg_match and not attack_only:
            groups.append(
                self._format_talespire_dice_with_modifier(
                    dmg_match.group(1),
                    int(dmg_match.group(2) or 0),
                ),
            )
        if not groups:
            return None
        label = mount_name
        if damage_only:
            label = f"{mount_name} Damage"
        elif attack_only:
            label = mount_name
        return self._format_talespire_roll(label, groups)

    def _bind_talespire_mount_summary_clicks(self, widgets, *, include_damage=True, include_full=True):
        attack_builder = lambda: self._build_talespire_mount_attack_roll()
        for widget in widgets or []:
            if widget is not None:
                self._bind_talespire_click(widget, attack_builder)
        if include_damage:
            dmg_lbl = getattr(self, "_combat_mount_summary_damage_label", None)
            if dmg_lbl is not None:
                self._bind_talespire_click(
                    dmg_lbl,
                    lambda: self._build_talespire_mount_damage_roll(),
                )
        if include_full:
            card = getattr(self, "_combat_mount_summary_card", None)
            if card is not None:
                self._bind_talespire_click(
                    card,
                    lambda: self._build_talespire_mount_full_roll(),
                )

    def _refresh_mount_attack_summary(self):
        """Show or hide the mount attack card in Combat Attack Summaries."""
        if not hasattr(self, "combat_summary_scroll"):
            return
        for widget in getattr(self, "_combat_mount_summary_widgets", []) or []:
            try:
                if widget and widget.winfo_exists():
                    widget.destroy()
            except Exception:
                pass
        self._combat_mount_summary_widgets = []
        self._combat_mount_summary_card = None
        self._combat_mount_summary_damage_label = None
        if not self._has_mount():
            return
        attack_str = self._get_mount_attack_string()
        if not attack_str:
            return
        mount_name = self._get_mount_summary_name()
        components = self._parse_mount_attack_components(attack_str)
        atk_suffix = self._format_mount_attack_bonus_display(components)
        dmg_display = self._format_mount_damage_display(components)
        header = ctk.CTkFrame(self.combat_summary_scroll, fg_color="#3a2f2a", height=22)
        header.pack(fill="x", pady=(6, 1), padx=4)
        header.pack_propagate(False)
        ctk.CTkLabel(
            header,
            text="Mount",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=THEME_ORANGE,
        ).pack(side="left", padx=6)
        card = ctk.CTkFrame(self.combat_summary_scroll, fg_color="#2f2a1f", height=50)
        card.pack(fill="x", pady=2, padx=6)
        card.pack_propagate(False)
        name_lbl = ctk.CTkLabel(
            card,
            text=f"{mount_name}:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=THEME_ORANGE,
            cursor="hand2",
        )
        name_lbl.pack(side="left", padx=(8, 4), pady=2)
        atk_row = ctk.CTkFrame(card, fg_color="transparent")
        atk_row.pack(side="left", padx=(0, 2), pady=2)
        if atk_suffix:
            suffix_lbl = ctk.CTkLabel(
                atk_row,
                text=atk_suffix,
                font=ctk.CTkFont(size=12),
                cursor="hand2",
            )
            suffix_lbl.pack(side="left")
            atk_lbl = suffix_lbl
        else:
            atk_lbl = ctk.CTkLabel(
                atk_row,
                text=attack_str,
                wraplength=420,
                justify="left",
                anchor="w",
                font=ctk.CTkFont(size=12),
                cursor="hand2",
            )
            atk_lbl.pack(side="left")
            suffix_lbl = atk_lbl
        dmg_lbl = None
        if dmg_display:
            dmg_lbl = ctk.CTkLabel(
                card,
                text=" " + dmg_display,
                wraplength=420,
                justify="left",
                anchor="w",
                font=ctk.CTkFont(size=12),
                cursor="hand2",
            )
            dmg_lbl.pack(side="left", padx=(2, 8), pady=2)
        mount = self._get_mount_data()
        special = str(mount.get("special") or (mount.get("stats") or {}).get("special") or "").strip()
        tooltip_lines = [
            mount_name,
            f"Attack: {attack_str}",
            "Click name/attack for attack roll; click damage for damage roll; click card for full roll.",
        ]
        if special:
            tooltip_lines.append(special)
        self._bind_hover_tooltip(card, "\n".join(tooltip_lines), wraplength=420)
        self._combat_mount_summary_widgets = [header, card]
        self._combat_mount_summary_attack_label = atk_lbl
        self._combat_mount_summary_name_label = name_lbl
        self._combat_mount_summary_card = card
        self._combat_mount_summary_damage_label = dmg_lbl
        self._bind_talespire_mount_summary_clicks(
            [name_lbl, atk_lbl],
            include_damage=bool(dmg_display),
            include_full=True,
        )

    def _refresh_mount_related_displays(self):
        self._refresh_mount_button_appearance()
        self._refresh_mount_movement_if_needed()
        refresh_summary = getattr(self, "_refresh_mount_attack_summary", None)
        if callable(refresh_summary):
            try:
                refresh_summary()
            except Exception:
                pass

    def _get_mount_button_colors(self):
        riding = bool(self._get_mount_data().get("riding")) and self._has_mount()
        accent = getattr(self, "primary_button_color", THEME_ORANGE)
        hover = getattr(self, "primary_hover_color", "#e08a3a")
        if riding:
            return accent, hover
        return "#888888", "#aaaaaa"

    def _refresh_mount_button_appearance(self):
        idle, _hover = self._get_mount_button_colors()
        buttons = getattr(self, "_mount_overlay_buttons", None) or []
        live = []
        for btn in buttons:
            try:
                if btn and btn.winfo_exists():
                    btn.configure(text_color=idle)
                    live.append(btn)
            except Exception:
                pass
        self._mount_overlay_buttons = live

    def _build_paladin_mount_selector(self, parent):
        """Paladin Special Mount selector in the class features tab."""
        mount = self._get_mount_data()
        current_base = mount.get("base", "") or ""
        pal_level = self._get_paladin_level()
        if current_base and current_base in getattr(self, "MOUNTS", {}):
            self._update_mount(current_base, mount.get("name"))
            mount = self._get_mount_data()
            current_base = mount.get("base", "") or ""

        sel_frame = ctk.CTkFrame(parent, fg_color="#1F1F1F")
        sel_frame.pack(fill="x", padx=15, pady=(4, 10))

        accent = getattr(self, "primary_button_color", THEME_ORANGE)
        ctk.CTkLabel(
            sel_frame,
            text="Select Special Mount:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=accent,
        ).pack(anchor="w", padx=10, pady=(6, 2))

        ctk.CTkLabel(
            sel_frame,
            text=(
                f"Paladin level {pal_level} — mount gains bonus HD, ability increases, "
                "and special abilities (same sheet as the ∩ horseshoe button)."
            ),
            font=ctk.CTkFont(size=10),
            text_color="#aaaaaa",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 4))

        bases = [""] + list(getattr(self, "MOUNTS", {}).keys())
        combo = ctk.CTkComboBox(
            sel_frame,
            values=bases,
            width=280,
            command=lambda val: self._on_paladin_mount_selected(val),
        )
        combo.set(current_base if current_base in bases else "")
        combo.pack(anchor="w", padx=10, pady=(0, 4))

        preview_text = self._get_paladin_mount_preview_text(current_base, pal_level)
        self.paladin_mount_preview = ctk.CTkLabel(
            sel_frame,
            text=preview_text,
            justify="left",
            font=ctk.CTkFont(size=10),
            wraplength=520,
        )
        self.paladin_mount_preview.pack(anchor="w", padx=10, pady=(0, 4))

        btn_row = ctk.CTkFrame(sel_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(2, 6))

        def open_mount_sheet():
            if self._has_mount():
                self._open_mount_window()
            else:
                messagebox.showinfo("Special Mount", "Select a mount from the list first.")

        ctk.CTkButton(
            btn_row,
            text="∩ Open Mount Sheet (HP, tack, barding, abilities, attack)",
            width=420,
            command=open_mount_sheet,
            fg_color=accent,
        ).pack(side="left")

    def _on_paladin_mount_selected(self, val):
        base = (val or "").strip()
        mount = self._get_mount_data()
        if not base:
            mount["base"] = ""
            mount["paladin_mount"] = False
            if hasattr(self, "paladin_mount_preview") and self.paladin_mount_preview.winfo_exists():
                try:
                    self.paladin_mount_preview.configure(text="No special mount selected.")
                except Exception:
                    pass
            self._refresh_mount_related_displays()
            self._mark_cloud_sync_dirty()
            return
        self._update_mount(base, mount.get("name") or base)
        mount = self._get_mount_data()
        preview_text = self._get_paladin_mount_preview_text(base, self._get_paladin_level())
        if hasattr(self, "paladin_mount_preview") and self.paladin_mount_preview.winfo_exists():
            try:
                self.paladin_mount_preview.configure(text=preview_text)
            except Exception:
                pass
        self._mark_cloud_sync_dirty()

    def _get_mount_data(self):
        return self.data.setdefault("mount", {})

    def _get_paladin_level(self):
        return int(self._get_class_level("Paladin") or 0)

    def _qualifies_for_paladin_special_mount(self):
        return self._get_paladin_level() >= 5

    def _get_paladin_mount_advancement(self, pal_level=None):
        """SRD special mount advancement by paladin level."""
        if pal_level is None:
            pal_level = self._get_paladin_level()
        if pal_level < 5:
            return None
        if pal_level <= 7:
            return {
                "bonus_hd": 2, "nat_armor": 4, "str_adj": 4, "dex_adj": 1, "int_score": 6,
            }
        if pal_level <= 10:
            return {
                "bonus_hd": 4, "nat_armor": 6, "str_adj": 4, "dex_adj": 2, "int_score": 7,
            }
        if pal_level <= 14:
            return {
                "bonus_hd": 6, "nat_armor": 8, "str_adj": 5, "dex_adj": 2, "int_score": 8,
            }
        return {
            "bonus_hd": 8, "nat_armor": 10, "str_adj": 5, "dex_adj": 2, "int_score": 9,
        }

    def _get_level_based_paladin_mount_abilities(self, pal_level=None):
        if pal_level is None:
            pal_level = self._get_paladin_level()
        abilities = []
        if pal_level >= 5:
            abilities.extend([
                "Empathic Link", "Improved Evasion", "Share Spells", "Speak with Master",
            ])
        if pal_level >= 8:
            abilities.append("Blood Bond")
        if pal_level >= 11:
            abilities.append(f"Spell Resistance ({pal_level + 5})")
        if pal_level >= 15:
            abilities.append("Devotion")
        return abilities

    def _apply_paladin_mount_scaling(self, mount, base_stats):
        """Apply paladin special mount advancement on top of the base mount stat block."""
        if not self._qualifies_for_paladin_special_mount():
            mount["paladin_mount"] = False
            return base_stats
        adv = self._get_paladin_mount_advancement()
        if not adv:
            mount["paladin_mount"] = False
            return base_stats
        mount["paladin_mount"] = True
        mount["paladin_level"] = self._get_paladin_level()
        base_hd = int(base_stats.get("hd", 1) or 1)
        base_stats["hd"] = base_hd + adv["bonus_hd"]
        base_stats["str"] = int(base_stats.get("str", 10) or 10) + adv["str_adj"]
        base_stats["dex"] = int(base_stats.get("dex", 10) or 10) + adv["dex_adj"]
        base_stats["int"] = adv["int_score"]
        base_stats["ac"] = int(base_stats.get("ac", 10) or 10) + adv["nat_armor"]
        return base_stats

    def _get_paladin_mount_preview_text(self, base, pal_level=None):
        if pal_level is None:
            pal_level = self._get_paladin_level()
        if not base or base not in getattr(self, "MOUNTS", {}):
            return "Select a mount from the list."
        stats = self.MOUNTS[base]
        adv = self._get_paladin_mount_advancement(pal_level)
        if not adv:
            return (
                f"Base: HD {stats.get('hd', 1)} {stats.get('size', 'Large')} | "
                f"AC {stats.get('ac', 10)} | {stats.get('attack', '')}"
            )
        scaled_hd = int(stats.get("hd", 1) or 1) + adv["bonus_hd"]
        scaled_ac = int(stats.get("ac", 10) or 10) + adv["nat_armor"]
        abils = ", ".join(self._get_level_based_paladin_mount_abilities(pal_level))
        return (
            f"Paladin level {pal_level}: HD {scaled_hd}, AC ~{scaled_ac}, "
            f"Int {adv['int_score']}\n"
            f"Special: {abils}\n"
            f"Use the ∩ horseshoe on Stats/Combat movement for the full mount sheet."
        )

    def _sync_paladin_mount(self):
        """Re-apply paladin mount advancement when paladin level changes."""
        if not self._has_mount():
            return
        mount = self._get_mount_data()
        base = (mount.get("base") or "").strip()
        if not base:
            return
        self._update_mount(base, mount.get("name"))

    def _update_mount(self, base, name=None):
        if not base or base not in getattr(self, "MOUNTS", {}):
            return
        base_stats = copy.deepcopy(self.MOUNTS[base])
        mount = self._get_mount_data()
        mount["base"] = base
        if name is not None:
            mount["name"] = name or base
        elif not mount.get("name"):
            mount["name"] = base
        base_stats = self._apply_paladin_mount_scaling(mount, base_stats)
        mount["stats"] = base_stats
        if mount.get("attack"):
            mount["stats"]["attack"] = mount["attack"]
        if mount.get("special"):
            mount["stats"]["special"] = mount["special"]
        mount.setdefault("stat_bonuses", {k: 0 for k in ("str", "dex", "con", "int", "wis", "cha")})
        mount.setdefault("ac_bonuses", {})
        mount.setdefault("barding", "")
        mount.setdefault("saddle", "Riding")
        mount.setdefault("riding", bool(mount.get("riding", False)))
        mount.setdefault("bareback", False)
        self._recalc_mount_max_hp(mount, base_stats)
        max_hp = int(base_stats.get("max_hp") or base_stats.get("hp") or 10)
        base_stats["max_hp"] = max_hp
        if "current_hp" not in mount:
            mount["current_hp"] = max_hp
        if "temp_hp" not in mount:
            mount["temp_hp"] = 0
        if "skills" not in mount:
            mount["skills"] = dict(base_stats.get("skills", {}))
        if "feats" not in mount:
            mount["feats"] = list(base_stats.get("feats", []))
        self._refresh_mount_related_displays()

    def _get_barding_armor_options(self):
        db = getattr(self, "mundane_armors_shields_db", {}) or {}
        options = [""]
        for name, info in sorted(db.items()):
            if (info or {}).get("kind") == "armor":
                options.append(name)
        return options

    def _mount_encumbrance_load_effects(self):
        import dnd_character_sheet as sheet
        return sheet.ENCUMBRANCE_LOAD_EFFECTS

    def _get_mount_barding_details(self, mount=None):
        """Barding name, category, and armor bonus for the active mount."""
        mount = mount or self._get_mount_data()
        barding_name = (mount.get("barding") or "").strip()
        result = {"name": barding_name, "armor_bonus": 0, "category": ""}
        if not barding_name:
            return result
        db = getattr(self, "mundane_armors_shields_db", {}) or {}
        if not db:
            self.load_mundane_armors_shields_db()
            db = getattr(self, "mundane_armors_shields_db", {}) or {}
        armor = db.get(barding_name) or {}
        if not armor:
            return result
        result["armor_bonus"] = int(armor.get("armor_bonus", 0) or 0)
        result["category"] = (armor.get("category") or "").strip().lower()
        return result

    def _get_mount_rider_burden_weight(self, mount=None):
        """Weight on the mount when Riding: rider body + rider carried gear (+ container if Mount mode)."""
        mount = mount or self._get_mount_data()
        if not mount.get("riding"):
            return 0.0
        burden = self._get_character_description_weight_lbs() + self._get_total_carried_weight()
        if self._effective_carrying_container_mode() == "mount":
            burden += self._get_container_encumbrance_weight(for_mount=True)
        return burden

    def _get_mount_encumbrance_load_state(self, mount=None):
        """Load tier from rider burden vs. mount carrying capacity (same effects as characters)."""
        mount = mount or self._get_mount_data()
        stats = mount.get("stats", {})
        cap = stats.get("carrying_capacity") or {}
        carried = float(self._get_mount_rider_burden_weight(mount))
        light_max = float(cap.get("light", 0) or 0)
        medium_max = float(cap.get("medium", 0) or 0)
        heavy_max = float(cap.get("heavy", 0) or 0)
        load_effects = self._mount_encumbrance_load_effects()
        if heavy_max <= 0:
            load = "light"
        elif carried <= light_max:
            load = "light"
        elif carried <= medium_max:
            load = "medium"
        elif carried <= heavy_max:
            load = "heavy"
        else:
            load = "overloaded"
        effects = dict(load_effects.get(load, load_effects["light"]))
        return {
            "carried": carried,
            "light_max": light_max,
            "medium_max": medium_max,
            "heavy_max": heavy_max,
            "load": load,
            "load_label": load.capitalize(),
            **effects,
        }

    def _get_mount_barding_land_speed(self, before_armor, armor_cat):
        """Land speed from medium/heavy barding (armor speed table, same as characters)."""
        before_armor = int(before_armor or 0)
        if armor_cat in ("medium", "heavy"):
            return self._lookup_armor_reduced_speed(before_armor)
        return before_armor

    def _get_mount_load_land_speed(self, before_armor, load_state):
        """Land speed from encumbrance load (same rules as characters)."""
        before_armor = int(before_armor or 0)
        if load_state.get("uses_armor_speed_table"):
            return self._lookup_armor_reduced_speed(before_armor)
        load_cap = load_state.get("land_speed")
        if load_cap is None:
            return before_armor
        return int(load_cap)

    def _get_mount_run_multiplier(self, mount, armor_cat, load_state):
        """Worst-of mount Run feat, barding, and load (mirrors character armor/load run caps)."""
        stats = mount.get("stats", {})
        base_run = int(stats.get("run_multiplier", 4) or 4)
        if armor_cat == "heavy":
            armor_run = 3
        elif armor_cat == "medium":
            armor_run = 4
        else:
            armor_run = base_run
        run_mult = min(base_run, armor_run)
        load_run = load_state.get("run_multiplier")
        if load_run is not None:
            run_mult = min(run_mult, int(load_run))
        return run_mult

    def _resolve_mount_land_speed_penalties(self, mount=None):
        """
        3.5 SRD: mount land speed uses the armor speed table for medium/heavy barding
        and medium/heavy load; apply the worse of barding vs. load (do not stack).
        """
        mount = mount or self._get_mount_data()
        stats = mount.get("stats", {})
        before_armor = int(stats.get("speed", 30) or 30)
        barding = self._get_mount_barding_details(mount)
        armor_cat = barding["category"]
        load_state = self._get_mount_encumbrance_load_state(mount)

        armor_speed = self._get_mount_barding_land_speed(before_armor, armor_cat)
        load_speed = self._get_mount_load_land_speed(before_armor, load_state)
        final_land = min(armor_speed, load_speed)

        lines = []
        barding_name = barding["name"]
        wearing_barding = armor_cat in ("medium", "heavy")
        load_label = load_state.get("load_label", "Load")
        has_load_cap = bool(
            load_state.get("uses_armor_speed_table") or load_state.get("land_speed") is not None
        )

        if barding.get("armor_bonus"):
            if wearing_barding and armor_speed < before_armor:
                cat_label = armor_cat.replace("_", " ").title()
                lines.append(
                    f"Barding ({barding_name}): +{barding['armor_bonus']} AC, "
                    f"{before_armor} -> {armor_speed} ft. ({cat_label}, armor speed table)",
                )
            else:
                lines.append(f"Barding ({barding_name}): +{barding['armor_bonus']} AC, no speed loss (light).")
            if armor_cat in ("medium", "heavy"):
                lines.append("Medium/heavy barding: -1 on mount attack rolls and Reflex saves.")

        if wearing_barding and has_load_cap:
            if armor_speed <= load_speed:
                cat_label = armor_cat.replace("_", " ").title()
                lines.append(
                    f"{cat_label} barding limits speed to {final_land} ft. "
                    f"(worse than {load_label.lower()} load {load_speed} ft.)",
                )
            else:
                lines.append(
                    f"{load_label} load ({load_state.get('carried', 0):g} lb.): "
                    f"{before_armor} -> {final_land} ft. "
                    f"(worse than {armor_cat} barding {armor_speed} ft.)",
                )
        elif has_load_cap and load_speed < before_armor:
            lines.append(
                f"{load_label} load ({load_state.get('carried', 0):g} lb.): "
                f"{before_armor} -> {load_speed} ft.",
            )

        run_mult = self._get_mount_run_multiplier(mount, armor_cat, load_state)
        run_speed = final_land * run_mult

        return {
            "name": barding_name,
            "armor_bonus": barding["armor_bonus"],
            "category": armor_cat,
            "base_speed": before_armor,
            "speed": final_land,
            "before_armor": before_armor,
            "armor_speed": armor_speed,
            "load_speed": load_speed,
            "final_land": final_land,
            "run_multiplier": run_mult,
            "run_speed": run_speed,
            "load_state": load_state,
            "lines": lines,
        }

    def _get_mount_barding_info(self, mount=None):
        """Compatibility wrapper returning barding + resolved land/run speeds."""
        resolved = self._resolve_mount_land_speed_penalties(mount)
        return {
            "name": resolved["name"],
            "armor_bonus": resolved["armor_bonus"],
            "category": resolved["category"],
            "base_speed": resolved["base_speed"],
            "speed": resolved["speed"],
            "run_multiplier": resolved["run_multiplier"],
            "lines": resolved["lines"],
        }

    def _calc_mount_ac(self, mount, stats):
        ability_bon = mount.get("stat_bonuses", {})
        ac_bon = mount.get("ac_bonuses", {})
        eff_dex = stats.get("dex", 10) + ability_bon.get("dex", 0)
        dex_mod = (eff_dex - 10) // 2
        base_dex_mod = (stats.get("dex", 10) - 10) // 2
        dex_delta = dex_mod - base_dex_mod
        base = int(stats.get("ac", 10) or 10)
        barding = self._get_mount_barding_info(mount)
        armor = int(ac_bon.get("armor", 0) or 0) + barding["armor_bonus"]
        shield = int(ac_bon.get("shield", 0) or 0)
        natural = int(ac_bon.get("natural", 0) or 0)
        defl = int(ac_bon.get("deflection", 0) or 0)
        dodge = int(ac_bon.get("dodge", 0) or 0)
        insight = int(ac_bon.get("insight", 0) or 0)
        other = sum(int(ac_bon.get(k, 0) or 0) for k in ("morale", "sacred", "profane", "luck", "misc"))
        total = base + dex_delta + armor + shield + natural + defl + dodge + insight + other
        flat = base + armor + shield + natural + defl + insight + other
        touch = 10 + dex_mod + defl + dodge + insight + other
        return int(total), int(flat), int(touch)

    def _recalc_mount_max_hp(self, mount, stats):
        bonuses = mount.get("stat_bonuses", {})
        eff_con = stats.get("con", 10) + bonuses.get("con", 0)
        con_mod = (eff_con - 10) // 2
        hd = int(stats.get("hd") or 1)
        stored = int(stats.get("hp") or stats.get("max_hp") or 0)
        if stored > 0 and bonuses.get("con", 0) == 0:
            new_max = stored
        else:
            new_max = int(hd * 4.5) + con_mod * hd
        stats["max_hp"] = new_max
        if mount.get("current_hp", new_max) > new_max:
            mount["current_hp"] = new_max
        return new_max

    def _get_mount_movement_breakdown(self):
        mount = self._get_mount_data()
        if not mount.get("riding") or not self._has_mount():
            return None
        resolved = self._resolve_mount_land_speed_penalties(mount)
        land = int(resolved["final_land"])
        run_mult = int(resolved["run_multiplier"])
        run_speed = int(resolved["run_speed"])
        name = mount.get("name", mount.get("base", "Mount"))
        lines = [f"Riding {name} ({mount.get('base', '')})"]
        lines.append(f"Mount base land speed: {resolved['base_speed']} ft.")
        load_state = resolved.get("load_state") or {}
        if mount.get("riding") and load_state.get("load") not in (None, "light"):
            lines.append(
                f"Rider burden: {load_state.get('carried', 0):g} lb. "
                f"({load_state.get('load_label', 'Load')} load)",
            )
        lines.extend(resolved["lines"])
        base_run = int((mount.get("stats") or {}).get("run_multiplier", 4) or 4)
        if run_mult != base_run:
            lines.append(f"Run multiplier: x{run_mult} (base x{base_run}, barding/load caps applied)")
        elif run_mult != 4:
            lines.append(f"Run multiplier: x{run_mult}")
        land_tooltip = "Land Speed (Mounted)\n" + "\n".join(lines)
        run_tooltip = (
            f"Run (Mounted)\nRun: {run_speed} ft.\n"
            f"Land speed {land} ft. x {run_mult}"
        )
        return {
            "base_land": resolved["base_speed"],
            "before_armor": resolved["before_armor"],
            "after_armor": land,
            "final_land": land,
            "run_speed": run_speed,
            "run_multiplier": run_mult,
            "lines": lines,
            "riding_active": True,
            "modes": {
                "land": {"speed": land, "tooltip": land_tooltip, "icon": MOUNT_RIDING_LAND_ICON},
                "run": {"speed": run_speed, "tooltip": run_tooltip, "icon": MOUNT_RIDING_RUN_ICON},
                "fly": {"speed": 0, "tooltip": "Fly\nNo fly speed while mounted"},
                "swim": {"speed": 0, "tooltip": "Swim\nUse dismounted swim speed"},
                "climb": {"speed": 0, "tooltip": "Climb\nUse dismounted climb speed"},
                "burrow": {"speed": 0, "tooltip": "Burrow\nNo burrow speed while mounted"},
            },
        }

    def _refresh_mount_movement_if_needed(self):
        if hasattr(self, "movement_mode_widgets") or hasattr(self, "stats_movement_mode_widgets"):
            try:
                self.refresh_movement_display()
            except Exception:
                pass

    def _clear_mount_container_carry_mode(self):
        """Revert container carry to No when mount selection is cleared."""
        if self._get_carrying_container_mode() != "mount":
            return
        self._set_carrying_container_mode("no")
        seg = getattr(self, "carrying_container_seg", None)
        if seg is not None:
            try:
                if seg.winfo_exists():
                    seg.set("No")
            except Exception:
                pass

    def _get_ride_circumstance_bonus(self, mount=None):
        mount = mount or self._get_mount_data()
        bonus = 0
        if mount.get("bareback"):
            bonus -= 5
        saddle = (mount.get("saddle") or "").strip().lower()
        if "military" in saddle:
            bonus += 2
        return bonus

    def _build_ride_task_roll(self, task_name, dc):
        modifier = self._get_skill_total_modifier("Ride") + self._get_ride_circumstance_bonus()
        label = f"Ride {task_name} DC{dc}"
        return self._format_talespire_roll(
            self._sanitize_talespire_label(label),
            [self._format_talespire_dice_with_modifier("1d20", modifier)],
        )

    def _bind_mount_button(self, widget):
        def on_click(event=None):
            shift = bool(event and (getattr(event, "state", 0) & 0x0001))
            if shift:
                self._open_riding_rules_window()
            else:
                self._open_mount_window()

        def on_enter(_event):
            _idle, hover = self._get_mount_button_colors()
            try:
                widget.configure(text_color=hover)
            except Exception:
                pass

        def on_leave(_event):
            idle, _hover = self._get_mount_button_colors()
            try:
                widget.configure(text_color=idle)
            except Exception:
                pass

        widget.bind("<Button-1>", on_click)
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def _place_mount_button_overlay(self, parent, *, compact=False):
        """Borderless horseshoe control floated over the movement widget (no layout squeeze)."""
        idle, _hover = self._get_mount_button_colors()
        riding = bool(self._get_mount_data().get("riding")) and self._has_mount()
        tip = "Mounts (Shift+click: Riding rules)"
        if riding:
            tip = "Riding — mount speed active (Shift+click: Riding rules)"
        font_size = 12 if compact else 14
        btn = ctk.CTkLabel(
            parent,
            text=MOUNT_BTN_ICON,
            font=ctk.CTkFont(size=font_size, weight="bold"),
            text_color=idle,
            cursor="hand2",
            fg_color="transparent",
            width=18,
            height=16,
        )
        btn.place(relx=1.0, rely=0.0, x=-3, y=2, anchor="ne")
        btn.lift()
        self._bind_mount_button(btn)
        if not hasattr(self, "_mount_overlay_buttons"):
            self._mount_overlay_buttons = []
        self._mount_overlay_buttons.append(btn)
        if hasattr(self, "_bind_hover_tooltip"):
            self._bind_hover_tooltip(btn, tip, delay_ms=400)
        return btn

    def _open_riding_rules_window(self):
        popup = ctk.CTkToplevel(self.root)
        popup.title("Ride Skill — Rules & Checks")
        popup.grab_set()
        self._size_and_center_popup_to_content(popup, min_width=720, min_height=640)

        primary = getattr(self, "primary_button_color", THEME_ORANGE)
        hover = getattr(self, "primary_hover_color", "#a56b32")
        mount = self._get_mount_data()
        ride_mod = self._get_skill_total_modifier("Ride")
        circ = self._get_ride_circumstance_bonus(mount)
        total = ride_mod + circ

        main = ctk.CTkFrame(popup, fg_color="#1F1F1F")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        hdr = ctk.CTkFrame(main, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            hdr,
            text=f"Ride modifier: {total:+d}  (skill {ride_mod:+d}, circumstance {circ:+d})",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=primary,
        ).pack(side="left")
        ride_roll_btn = ctk.CTkButton(hdr, text="Roll Ride", width=90, fg_color=primary, hover_color=hover)
        ride_roll_btn.pack(side="right", padx=4)
        self._bind_talespire_click(ride_roll_btn, lambda: self._build_talespire_skill_roll("Ride"))

        scroll = ctk.CTkScrollableFrame(main, fg_color="#2A2A2A")
        scroll.pack(fill="both", expand=True)

        for title, body in RIDE_RULES_SECTIONS:
            ctk.CTkLabel(scroll, text=title, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(
                fill="x", padx=8, pady=(10, 2),
            )
            ctk.CTkLabel(
                scroll, text=body, justify="left", wraplength=660,
                font=ctk.CTkFont(size=11), anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 4))

        ctk.CTkLabel(
            scroll, text="Ride Checks (click to roll vs DC)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=primary,
        ).pack(fill="x", padx=8, pady=(12, 4))

        for task, dc, note in RIDE_TASKS:
            row = ctk.CTkFrame(scroll, fg_color="#333333", corner_radius=6)
            row.pack(fill="x", padx=6, pady=3)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=8, pady=6)
            roll_lbl = ctk.CTkLabel(
                inner,
                text=f"{task}  (DC {dc})",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=THEME_ORANGE,
                cursor="hand2",
            )
            roll_lbl.pack(anchor="w")
            ctk.CTkLabel(inner, text=note, font=ctk.CTkFont(size=10), text_color="#bbbbbb", wraplength=640, justify="left").pack(anchor="w")
            self._bind_talespire_click(roll_lbl, lambda t=task, d=dc: self._build_ride_task_roll(t, d))

        ctk.CTkButton(main, text="Close", fg_color=primary, hover_color=hover, command=popup.destroy).pack(pady=(8, 0))

    def _open_mount_window(self):
        mount = self._get_mount_data()
        popup = ctk.CTkToplevel(self.root)
        title_kind = "Paladin Mount" if mount.get("paladin_mount") else "Mount"
        popup.title(title_kind)
        popup.grab_set()
        self._size_and_center_popup_to_content(popup, min_width=980, min_height=720)

        primary = getattr(self, "primary_button_color", THEME_ORANGE)
        hover = getattr(self, "primary_hover_color", "#a56b32")
        accent = primary

        main = ctk.CTkFrame(popup, fg_color="#1F1F1F")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        sel = ctk.CTkFrame(main, fg_color="#2F2F2F", corner_radius=8)
        sel.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(sel, text="Select Mount", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(
            anchor="w", padx=10, pady=(8, 4),
        )
        bases = [""] + list(getattr(self, "MOUNTS", {}).keys())
        current = mount.get("base", "") or ""
        if current and current in getattr(self, "MOUNTS", {}):
            self._update_mount(current, mount.get("name"))
            mount = self._get_mount_data()

        combo_row = ctk.CTkFrame(sel, fg_color="transparent")
        combo_row.pack(fill="x", padx=10, pady=4)
        combo = ctk.CTkComboBox(combo_row, values=bases, width=280, command=lambda v: self._on_mount_selected(v, popup))
        combo.set(current if current in bases else "")
        combo.pack(side="left")

        riding_var = ctk.BooleanVar(value=bool(mount.get("riding")))
        riding_sw = ctk.CTkSwitch(
            combo_row,
            text="Riding (use mount speed on sheet)",
            variable=riding_var,
            command=lambda: self._set_mount_riding(riding_var.get(), riding_var),
        )
        riding_sw.pack(side="left", padx=16)

        rules_btn = ctk.CTkButton(
            combo_row, text="Ride Rules", width=90, fg_color=primary, hover_color=hover,
            command=self._open_riding_rules_window,
        )
        rules_btn.pack(side="right", padx=4)

        if not self._has_mount():
            ctk.CTkLabel(
                main,
                text="Choose a mount from the list to edit its stat block.",
                font=ctk.CTkFont(size=12),
                text_color="#888888",
            ).pack(pady=20)
            ctk.CTkButton(main, text="Close", fg_color=primary, hover_color=hover, command=popup.destroy).pack(pady=8)
            return

        mount.setdefault("stat_bonuses", {k: 0 for k in ("str", "dex", "con", "int", "wis", "cha")})
        stats = mount.get("stats", {})
        self._recalc_mount_max_hp(mount, stats)
        max_hp = stats.get("max_hp", 10)
        barding = self._get_mount_barding_info(mount)

        cols_frame = ctk.CTkFrame(main, fg_color="transparent")
        cols_frame.pack(fill="both", expand=True)
        cols_frame.grid_columnconfigure(0, weight=1, minsize=230)
        cols_frame.grid_columnconfigure(1, weight=1, minsize=200)
        cols_frame.grid_columnconfigure(2, weight=1, minsize=280)
        col1 = ctk.CTkFrame(cols_frame, fg_color="#1F1F1F", corner_radius=6)
        col1.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        col2 = ctk.CTkFrame(cols_frame, fg_color="#1F1F1F", corner_radius=6)
        col2.grid(row=0, column=1, sticky="nsew", padx=2)
        col3 = ctk.CTkFrame(cols_frame, fg_color="#1F1F1F", corner_radius=6)
        col3.grid(row=0, column=2, sticky="nsew", padx=(3, 0))

        # Column 1 — identity & combat
        name_row = ctk.CTkFrame(col1, fg_color="transparent")
        name_row.pack(fill="x", pady=4, padx=6)
        ctk.CTkLabel(name_row, text="Name:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=4)
        name_var = ctk.StringVar(value=mount.get("name", ""))
        name_entry = ctk.CTkEntry(name_row, textvariable=name_var, width=160)
        name_entry.pack(side="left", padx=4)

        def save_name(*_a):
            mount["name"] = name_var.get().strip() or mount.get("base", "Mount")
            kind = "Paladin Mount" if mount.get("paladin_mount") else "Mount"
            popup.title(f"{kind}: {mount['name']}")

        name_entry.bind("<FocusOut>", save_name)

        eff_speed = barding["speed"]
        core_text = (
            f"HD:{stats.get('hd', 1)}  Size:{stats.get('size', 'Large')}  "
            f"Spd:{eff_speed} ft. (base {barding['base_speed']})\n"
            f"BAB:+{stats.get('bab', 0)}  Run:x{barding['run_multiplier']}"
        )
        ctk.CTkLabel(col1, text=core_text, justify="left", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=8, pady=2)

        tack_f = ctk.CTkFrame(col1, fg_color="#2F2F2F")
        tack_f.pack(fill="x", pady=3, padx=6)
        ctk.CTkLabel(tack_f, text="Tack & Barding", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(
            anchor="w", padx=6, pady=(4, 2),
        )
        saddle_row = ctk.CTkFrame(tack_f, fg_color="transparent")
        saddle_row.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(saddle_row, text="Saddle:", width=55).pack(side="left")
        saddle_var = ctk.StringVar(value=mount.get("saddle", "Riding"))
        saddle_combo = ctk.CTkComboBox(
            saddle_row, values=["Riding", "Military", "Exotic"], width=140, variable=saddle_var,
        )
        saddle_combo.pack(side="left", padx=4)

        def save_saddle(*_a):
            mount["saddle"] = saddle_var.get().strip()

        saddle_combo.configure(command=lambda _v: save_saddle())
        bareback_var = ctk.BooleanVar(value=bool(mount.get("bareback")))
        ctk.CTkCheckBox(
            saddle_row, text="Bareback (-5 Ride)", variable=bareback_var,
            command=lambda: mount.__setitem__("bareback", bareback_var.get()),
        ).pack(side="left", padx=8)

        barding_row = ctk.CTkFrame(tack_f, fg_color="transparent")
        barding_row.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(barding_row, text="Barding:", width=55).pack(side="left")
        barding_var = ctk.StringVar(value=mount.get("barding", ""))
        barding_combo = ctk.CTkComboBox(barding_row, values=self._get_barding_armor_options(), width=200, variable=barding_var)
        barding_combo.pack(side="left", padx=4)

        def refresh_speed_label():
            resolved = self._resolve_mount_land_speed_penalties(mount)
            load_state = resolved.get("load_state") or {}
            load_note = ""
            if load_state.get("load") not in (None, "light"):
                load_note = f", {load_state.get('load_label', 'load')} encumbrance"
            spd_lbl.configure(
                text=f"Effective speed: {resolved['speed']} ft.{load_note}",
            )

        def save_barding(choice=None):
            mount["barding"] = (choice if choice is not None else barding_var.get()).strip()
            self._refresh_mount_movement_if_needed()
            refresh_ac_display()
            refresh_speed_label()

        barding_combo.configure(command=save_barding)

        load_row = ctk.CTkFrame(tack_f, fg_color="transparent")
        load_row.pack(fill="x", padx=6, pady=(4, 0))
        ctk.CTkLabel(load_row, text="Load:", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(side="left")
        mount_load_lbl = ctk.CTkLabel(load_row, text="", font=ctk.CTkFont(size=12, weight="bold"))
        mount_load_lbl.pack(side="left", padx=(8, 0))
        mount_load_detail = ctk.CTkLabel(
            tack_f, text="", font=ctk.CTkFont(size=9), text_color="#888888",
            justify="left", wraplength=220,
        )
        mount_load_detail.pack(anchor="w", padx=6, pady=(0, 2))

        spd_lbl = ctk.CTkLabel(tack_f, text=f"Effective speed: {eff_speed} ft.", font=ctk.CTkFont(size=10), text_color="#aaaaaa")
        spd_lbl.pack(anchor="w", padx=6, pady=(0, 4))

        def refresh_mount_load_display():
            import dnd_character_sheet as sheet
            colors = sheet.ENCUMBRANCE_LOAD_COLORS
            load_state = self._get_mount_encumbrance_load_state(mount)
            cap = stats.get("carrying_capacity", {})
            heavy_max = float(cap.get("heavy", 0) or 0)
            carried = float(load_state.get("carried", 0) or 0)
            load = load_state.get("load", "light")
            if not mount.get("riding"):
                mount_load_lbl.configure(text="— (not riding)", text_color="#888888")
                mount_load_detail.configure(
                    text="Enable Riding to burden the mount with your body weight and carried gear.",
                )
            else:
                carried_txt = self._format_encumbrance_weight(carried)
                heavy_txt = self._format_encumbrance_weight(heavy_max) if heavy_max else "?"
                mount_load_lbl.configure(
                    text=f"{carried_txt}/{heavy_txt} ({load_state.get('load_label', 'Light')})",
                    text_color=colors.get(load, "#aaaaaa"),
                )
                body = self._get_character_description_weight_lbs()
                gear = self._get_total_carried_weight()
                parts = [
                    f"Body {self._format_encumbrance_weight(body)} lb.",
                    f"Gear {self._format_encumbrance_weight(gear)} lb.",
                ]
                if self._effective_carrying_container_mode() == "mount":
                    cont = self._get_container_encumbrance_weight(for_mount=True)
                    if cont > 0:
                        parts.append(f"Container {self._format_encumbrance_weight(cont)} lb.")
                mount_load_detail.configure(text=" + ".join(parts))
            refresh_speed_label()

        self._mount_popup_refresh_load = refresh_mount_load_display
        refresh_mount_load_display()

        atk_f = ctk.CTkFrame(col1, fg_color="#2F2F2F")
        atk_f.pack(fill="x", pady=3, padx=6)
        ctk.CTkLabel(atk_f, text="Attack", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(anchor="w", padx=6, pady=2)
        current_atk = mount.get("attack") or stats.get("attack", "")
        atk_var = ctk.StringVar(value=current_atk)
        atk_entry = ctk.CTkEntry(atk_f, textvariable=atk_var, width=210)
        atk_entry.pack(fill="x", padx=6, pady=(0, 4))

        def save_atk(*_a):
            val = atk_var.get().strip()
            mount["attack"] = val
            stats["attack"] = val
            self._refresh_mount_attack_summary()

        atk_entry.bind("<FocusOut>", save_atk)

        spec_f = ctk.CTkFrame(col1, fg_color="#2F2F2F")
        spec_f.pack(fill="x", pady=3, padx=6)
        if mount.get("paladin_mount"):
            pal_level = mount.get("paladin_level", self._get_paladin_level())
            level_abils = self._get_level_based_paladin_mount_abilities(pal_level)
            ctk.CTkLabel(
                spec_f, text="Paladin Special Abilities",
                font=ctk.CTkFont(weight="bold"), text_color=accent,
            ).pack(anchor="w", padx=6, pady=(2, 0))
            for ab in level_abils:
                row = ctk.CTkFrame(spec_f, fg_color="transparent")
                row.pack(fill="x", padx=6, pady=1)
                ab_key = ab.split(" (", 1)[0]
                ctk.CTkLabel(row, text=f"{ab}:", font=ctk.CTkFont(weight="bold", size=11)).pack(side="left")
                desc = PALADIN_MOUNT_ABILITY_INFO.get(ab_key, "")
                if desc:
                    ctk.CTkLabel(
                        row, text=desc, font=ctk.CTkFont(size=9),
                        wraplength=210, justify="left",
                    ).pack(side="left", padx=4, fill="x", expand=True)
        else:
            ctk.CTkLabel(spec_f, text="Special", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(
                anchor="w", padx=6, pady=2,
            )
        ctk.CTkLabel(spec_f, text="Extra / Notes", font=ctk.CTkFont(weight="bold", size=10), text_color=accent).pack(
            anchor="w", padx=6, pady=(4, 0),
        )
        spec_var = ctk.StringVar(value=mount.get("special", stats.get("special", "")))
        spec_e = ctk.CTkEntry(spec_f, textvariable=spec_var, width=210)
        spec_e.pack(fill="x", padx=6, pady=(0, 4))

        def save_special(*_a):
            val = spec_var.get().strip()
            mount["special"] = val
            stats["special"] = val

        spec_e.bind("<FocusOut>", save_special)

        # Column 2 — HP, abilities, AC
        health_f = ctk.CTkFrame(col2, fg_color="#2F2F2F")
        health_f.pack(fill="x", pady=4, padx=6)
        ctk.CTkLabel(health_f, text="Health", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(anchor="w", padx=6)
        cur = ctk.IntVar(value=min(max_hp, mount.get("current_hp", max_hp)))
        tmp = ctk.IntVar(value=mount.get("temp_hp", 0))
        hp_lbl = ctk.CTkLabel(health_f, text=f"HP: {cur.get()}/{max_hp} (+{tmp.get()})")
        hp_lbl.pack(anchor="w", padx=6)

        def upd_hp():
            if cur.get() > max_hp:
                cur.set(max_hp)
            hp_lbl.configure(text=f"HP: {cur.get()}/{max_hp} (+{tmp.get()})")
            mount["current_hp"] = cur.get()
            mount["temp_hp"] = tmp.get()

        btn_row = ctk.CTkFrame(health_f, fg_color="transparent")
        btn_row.pack(fill="x", padx=6, pady=2)
        for txt, cmd in (
            ("+1", lambda: (cur.set(min(max_hp, cur.get() + 1)), upd_hp())),
            ("-1", lambda: (cur.set(max(0, cur.get() - 1)), upd_hp())),
            ("Full", lambda: (cur.set(max_hp), upd_hp())),
            ("T+", lambda: (tmp.set(tmp.get() + 1), upd_hp())),
            ("T-", lambda: (tmp.set(max(0, tmp.get() - 1)), upd_hp())),
        ):
            ctk.CTkButton(btn_row, text=txt, width=32, fg_color=primary, hover_color=hover, command=cmd).pack(side="left", padx=1)

        ab_f = ctk.CTkFrame(col2, fg_color="#2F2F2F")
        ab_f.pack(fill="x", pady=4, padx=6)
        ab_hdr = ctk.CTkFrame(ab_f, fg_color="transparent")
        ab_hdr.pack(fill="x", padx=6)
        ctk.CTkLabel(ab_hdr, text="Abilities", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(side="left")
        ctk.CTkButton(
            ab_hdr, text="+", width=22, height=22, fg_color=primary, hover_color=hover,
            command=lambda: self._open_companion_ability_bonuses_popup(
                mount, stats, refresh_ability_scores, refresh_ac_display, primary, hover, "Mount",
            ),
        ).pack(side="left", padx=5)
        values_container = ctk.CTkFrame(ab_f, fg_color="transparent")
        values_container.pack(fill="x", padx=6, pady=2)

        def refresh_ability_scores():
            for w in values_container.winfo_children():
                w.destroy()
            bonuses = mount.get("stat_bonuses", {})
            for abn in ["Str", "Dex", "Con", "Int", "Wis", "Cha"]:
                short = abn[:3].lower()
                total = stats.get(short, 10) + bonuses.get(short, 0)
                mod = (total - 10) // 2
                ctk.CTkLabel(values_container, text=f"{abn}:{total}({mod:+})", width=66, font=ctk.CTkFont(size=10)).pack(
                    side="left", padx=1,
                )

        refresh_ability_scores()

        saves_f = ctk.CTkFrame(col2, fg_color="#2F2F2F")
        saves_f.pack(fill="x", pady=4, padx=6)
        ctk.CTkLabel(saves_f, text="Saving Throws", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(anchor="w", padx=6)
        saves_row = ctk.CTkFrame(saves_f, fg_color="transparent")
        saves_row.pack(fill="x", padx=6, pady=2)
        for sname, sval in [("Fort", stats.get("fort", 0)), ("Ref", stats.get("ref", 0)), ("Will", stats.get("will", 0))]:
            box = ctk.CTkFrame(saves_row, fg_color="#2F2F2F", corner_radius=6)
            box.pack(side="left", fill="both", expand=True, padx=2)
            ctk.CTkLabel(box, text=f"{sname}\n+{sval}", font=ctk.CTkFont(size=11, weight="bold"), text_color=accent).pack(pady=3)

        ac_f = ctk.CTkFrame(col2, fg_color="#2F2F2F")
        ac_f.pack(fill="x", pady=4, padx=6)
        ac_hdr = ctk.CTkFrame(ac_f, fg_color="transparent")
        ac_hdr.pack(fill="x", padx=6)
        ctk.CTkLabel(ac_hdr, text="Armor Class", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(side="left")
        ctk.CTkLabel(
            ac_hdr,
            text=f"(barding +{barding['armor_bonus']})" if barding["armor_bonus"] else "",
            font=ctk.CTkFont(size=9), text_color="#888888",
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            ac_hdr, text="+", width=22, height=22, fg_color=primary, hover_color=hover,
            command=lambda: self._open_companion_ac_bonuses_popup(
                mount, stats, refresh_ac_display, primary, hover, "Mount",
            ),
        ).pack(side="left", padx=5)
        ac_row = ctk.CTkFrame(ac_f, fg_color="transparent")
        ac_row.pack(fill="x", padx=6, pady=2)
        mount_ac_lbl = ctk.CTkLabel(ac_row, text="10", font=ctk.CTkFont(size=18, weight="bold"))
        mount_flat_lbl = ctk.CTkLabel(ac_row, text="10", font=ctk.CTkFont(size=16, weight="bold"))
        mount_touch_lbl = ctk.CTkLabel(ac_row, text="10", font=ctk.CTkFont(size=16, weight="bold"))

        def refresh_ac_display():
            total, flat, touch = self._calc_mount_ac(mount, stats)
            mount_ac_lbl.configure(text=str(total))
            mount_flat_lbl.configure(text=str(flat))
            mount_touch_lbl.configure(text=str(touch))

        ctk.CTkLabel(ac_row, text="AC", font=ctk.CTkFont(size=14), text_color=accent).pack(side="left", padx=4)
        mount_ac_lbl.pack(side="left", padx=4)
        ctk.CTkLabel(ac_row, text="FF", font=ctk.CTkFont(size=12), text_color=accent).pack(side="left", padx=(12, 2))
        mount_flat_lbl.pack(side="left", padx=2)
        ctk.CTkLabel(ac_row, text="T", font=ctk.CTkFont(size=12), text_color=accent).pack(side="left", padx=(12, 2))
        mount_touch_lbl.pack(side="left", padx=2)
        refresh_ac_display()

        # Column 3 — skills & feats
        sk_f = ctk.CTkFrame(col3, fg_color="#2F2F2F")
        sk_f.pack(fill="both", expand=True, pady=3, padx=6)
        ctk.CTkLabel(sk_f, text="Skills", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(anchor="w", padx=6)
        sk_scroll = ctk.CTkScrollableFrame(sk_f, height=110)
        sk_scroll.pack(fill="both", expand=True, padx=6, pady=2)
        mount_sk = mount.setdefault("skills", dict(stats.get("skills", {})))
        for sk_name, rank in list(mount_sk.items()):
            r = ctk.CTkFrame(sk_scroll, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=sk_name, width=75).pack(side="left")
            rvar = ctk.IntVar(value=rank)
            e = ctk.CTkEntry(r, textvariable=rvar, width=40)
            e.pack(side="left", padx=2)
            e.bind("<FocusOut>", lambda _e, s=sk_name, v=rvar: mount_sk.__setitem__(s, v.get()))

        ft_f = ctk.CTkFrame(col3, fg_color="#2F2F2F")
        ft_f.pack(fill="x", pady=3, padx=6)
        ctk.CTkLabel(ft_f, text="Feats", font=ctk.CTkFont(weight="bold"), text_color=accent).pack(anchor="w", padx=6)
        mount_ft = mount.setdefault("feats", list(stats.get("feats", [])))
        feats_list = ctk.CTkFrame(ft_f, fg_color="transparent")
        feats_list.pack(fill="x", padx=6, pady=1)

        def refresh_mount_feats():
            for child in feats_list.winfo_children():
                child.destroy()
            for feat in list(mount_ft):
                row = ctk.CTkFrame(feats_list, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=feat, font=ctk.CTkFont(size=10), width=160, anchor="w").pack(side="left")

        refresh_mount_feats()

        def close_mount_popup():
            self._mount_popup_refresh_load = None
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", close_mount_popup)

        def do_save():
            save_name()
            save_atk()
            save_special()
            save_saddle()
            save_barding()
            self._refresh_mount_related_displays()
            self._mark_cloud_sync_dirty()
            close_mount_popup()

        ctk.CTkButton(col3, text="Save Mount", fg_color=primary, hover_color=hover, command=do_save).pack(
            pady=8, padx=6, fill="x",
        )

    def _on_mount_selected(self, val, popup=None):
        base = (val or "").strip()
        mount = self._get_mount_data()
        if not base:
            mount["base"] = ""
            self._set_mount_riding(False)
            self._clear_mount_container_carry_mode()
            self._refresh_mount_related_displays()
            if popup and popup.winfo_exists():
                popup.destroy()
                self._open_mount_window()
            self._mark_cloud_sync_dirty()
            return
        self._update_mount(base, mount.get("name") or base)
        self._refresh_mount_related_displays()
        self._mark_cloud_sync_dirty()
        if popup and popup.winfo_exists():
            popup.destroy()
            self._open_mount_window()

    def _set_mount_riding(self, active, riding_var=None):
        mount = self._get_mount_data()
        if active and not self._has_mount():
            messagebox.showinfo("Mount", "Select a mount before enabling Riding.")
            mount["riding"] = False
            if riding_var is not None:
                riding_var.set(False)
            return
        mount["riding"] = bool(active)
        self._refresh_mount_related_displays()
        refresh_load = getattr(self, "_mount_popup_refresh_load", None)
        if callable(refresh_load):
            try:
                refresh_load()
            except Exception:
                pass
        self._mark_cloud_sync_dirty()