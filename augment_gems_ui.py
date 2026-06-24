"""Magical Items tab gear sections (weapon/armor/shield enchants + augment gems)."""

from __future__ import annotations

import copy
import json
import re

import customtkinter as ctk

THEME_ORANGE = "#c77626"
THEME_TEAL = "#28a99e"


class AugmentGemsMixin:
    """Weapon/armor/shield feature cards and augment gem slots."""

    def load_weapon_gems_db(self):
        try:
            with open(self._json_path("weapon_gems.json"), "r", encoding="utf-8") as handle:
                self.weapon_gems_db = json.load(handle)
            print(f"✅ Loaded {len(self.weapon_gems_db)} weapon augment gems")
        except Exception as exc:
            print(f"⚠️ Could not load weapon_gems.json: {exc}")
            self.weapon_gems_db = {}

    def load_armor_gems_db(self):
        try:
            with open(self._json_path("armor_gems.json"), "r", encoding="utf-8") as handle:
                self.armor_gems_db = json.load(handle)
            print(f"✅ Loaded {len(self.armor_gems_db)} armor augment gems")
        except Exception as exc:
            print(f"⚠️ Could not load armor_gems.json: {exc}")
            self.armor_gems_db = {}

    def load_shield_gems_db(self):
        try:
            with open(self._json_path("shield_gems.json"), "r", encoding="utf-8") as handle:
                self.shield_gems_db = json.load(handle)
            print(f"✅ Loaded {len(self.shield_gems_db)} shield augment gems")
        except Exception as exc:
            print(f"⚠️ Could not load shield_gems.json: {exc}")
            self.shield_gems_db = {}

    def _ensure_gear_augment_gems(self):
        gems = self.data.setdefault("gear_augment_gems", {})
        if not isinstance(gems, dict):
            self.data["gear_augment_gems"] = {}
        return self.data["gear_augment_gems"]

    def _strip_parenthetical_title(self, name: str) -> str:
        cleaned = re.sub(r"\s*\([^)]*\)", "", str(name or "")).strip()
        return cleaned or str(name or "Item").strip()

    def _augment_gem_db_for_type(self, gem_type: str) -> dict:
        if gem_type == "weapon":
            return getattr(self, "weapon_gems_db", {}) or {}
        if gem_type == "armor":
            return getattr(self, "armor_gems_db", {}) or {}
        if gem_type == "shield":
            return getattr(self, "shield_gems_db", {}) or {}
        return {}

    def _inventory_owns_item_name(self, item_name: str) -> bool:
        target = str(item_name or "").strip().casefold()
        if not target:
            return False
        for row in self.data.get("inventory", []) or []:
            if str(row.get("name") or "").strip().casefold() == target:
                qty = int(row.get("qty") or row.get("quantity") or 1)
                if qty > 0:
                    return True
        return False

    def _get_owned_augment_gems(self, gem_type: str) -> list[str]:
        db = self._augment_gem_db_for_type(gem_type)
        owned = [
            name for name in db
            if self._inventory_owns_item_name(name)
        ]
        return sorted(owned, key=str.casefold)

    def _get_gear_augment_gem(self, gear_key: str) -> str:
        return str(self._ensure_gear_augment_gems().get(gear_key, "") or "").strip()

    def _set_gear_augment_gem(self, gear_key: str, gem_name: str) -> None:
        gems = self._ensure_gear_augment_gems()
        gem_name = str(gem_name or "").strip()
        if not gem_name or gem_name == "(none)":
            gems.pop(gear_key, None)
        else:
            gems[gear_key] = gem_name
        if hasattr(self, "combat_summary_scroll"):
            if gear_key.startswith("weapon_"):
                try:
                    idx = int(gear_key.split("_", 1)[1])
                    self._refresh_combat_weapon_summary(idx)
                except (TypeError, ValueError):
                    pass
        if hasattr(self, "tabview") and self._is_page_active("Feats"):
            self.refresh_feats_scope("magical_items")

    def _weapon_has_special_enchants(self, idx: int) -> bool:
        weapon = self._get_weapon_slot(idx)
        if not str(weapon.get("name") or "").strip():
            return False
        config = self._get_combat_weapon_config(idx, weapon)
        return bool(config.get("enchants"))

    def _enchant_db_for_gear_type(self, gear_type: str) -> dict:
        if gear_type == "weapon":
            return getattr(self, "weapon_enchants_db", {}) or {}
        if gear_type == "armor":
            return getattr(self, "armor_enchants_db", {}) or {}
        if gear_type == "shield":
            return getattr(self, "shield_enchants_db", {}) or {}
        return {}

    def _enchant_feature_abilities(self, enchant_name: str, enchant_db: dict) -> dict:
        info = enchant_db.get(enchant_name, {}) if enchant_db else {}
        description = str(info.get("description") or "")
        abilities = {
            "uses_per_day": int(info.get("uses_per_day") or 0),
            "max_charges": int(info.get("max_charges") or 0),
            "granted_spells": list(info.get("granted_spells") or []),
        }
        if abilities["uses_per_day"] <= 0:
            abilities["uses_per_day"] = int(self._description_grant_uses_per_day(description) or 0)
        if abilities["max_charges"] <= 0:
            match = re.search(r"(\d+)\s+charges", description, re.I)
            if match:
                abilities["max_charges"] = int(match.group(1))
        if not abilities["granted_spells"]:
            abilities["granted_spells"] = self._resolve_granted_spells_for_item(enchant_name, info)
        return abilities

    def _get_magical_items_weapon_features(self) -> list[dict]:
        features = []
        for idx in range(len(self.data.get("weapons", []) or [])):
            if not self._weapon_has_special_enchants(idx):
                continue
            weapon = self._get_weapon_slot(idx)
            config = self._get_combat_weapon_config(idx, weapon)
            enchants = list(config.get("enchants") or [])
            gear_key = f"weapon_{idx}"
            features.append({
                "gear_type": "weapon",
                "gear_key": gear_key,
                "weapon_idx": idx,
                "title": self._strip_parenthetical_title(weapon.get("name", "Weapon")),
                "enchants": enchants,
                "bane_foe": str(config.get("bane_foe") or "").strip(),
                "gem_type": "weapon",
            })
        return features

    def _get_magical_items_armor_feature(self) -> dict | None:
        armor = self.data.get("armor") or {}
        if armor.get("status") != "worn" or not str(armor.get("name") or "").strip():
            return None
        enchants = list(armor.get("enchants") or [])
        if not enchants and int(armor.get("enh") or 0) <= 0:
            return None
        return {
            "gear_type": "armor",
            "gear_key": "armor",
            "title": self._strip_parenthetical_title(armor.get("name", "Armor")),
            "enchants": enchants,
            "gem_type": "armor",
        }

    def _get_magical_items_shield_feature(self) -> dict | None:
        shield = self.data.get("shield") or {}
        if shield.get("status") != "worn" or not str(shield.get("name") or "").strip():
            return None
        enchants = list(shield.get("enchants") or [])
        if not enchants and int(shield.get("enh") or 0) <= 0:
            return None
        return {
            "gear_type": "shield",
            "gear_key": "shield",
            "title": self._strip_parenthetical_title(shield.get("name", "Shield")),
            "enchants": enchants,
            "gem_type": "shield",
        }

    def _format_enchant_display_name(self, enchant_name: str, bane_foe: str = "") -> str:
        if enchant_name == "Bane" and str(bane_foe or "").strip():
            return f"Bane vs {bane_foe.strip().lower()}"
        return enchant_name

    def _build_augment_gem_selector(self, parent, gear_key: str, gem_type: str) -> None:
        owned = self._get_owned_augment_gems(gem_type)
        current = self._get_gear_augment_gem(gear_key)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkLabel(
            row,
            text="Augment Gem:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=THEME_TEAL,
        ).pack(side="left", padx=(0, 8))

        if not owned:
            ctk.CTkLabel(
                row,
                text="No matching gems in inventory",
                font=ctk.CTkFont(size=11),
                text_color="#888888",
            ).pack(side="left")
            return

        options = ["(none)"] + owned
        initial = current if current in owned else "(none)"
        var = ctk.StringVar(value=initial)

        def on_change(choice: str, key=gear_key):
            self._set_gear_augment_gem(key, choice)

        menu = ctk.CTkOptionMenu(
            row,
            values=options,
            variable=var,
            command=on_change,
            width=280,
        )
        menu.pack(side="left", fill="x", expand=True)

    def _build_gear_enchant_feature_card(self, parent, entry: dict) -> None:
        gear_type = entry.get("gear_type", "")
        enchant_db = self._enchant_db_for_gear_type(gear_type)
        frame = ctk.CTkFrame(parent, fg_color="#2F2F2F")
        frame.pack(fill="x", pady=10, padx=8)

        ctk.CTkLabel(
            frame,
            text=entry.get("title", "Gear"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=15, pady=(12, 6))

        bane_foe = entry.get("bane_foe", "")
        enchant_names = entry.get("enchants") or []
        if not enchant_names and entry.get("gem_type") in {"armor", "shield"}:
            ctk.CTkLabel(
                frame,
                text="No special armor/shield properties beyond enhancement.",
                font=ctk.CTkFont(size=11),
                text_color="#888888",
                wraplength=540,
                justify="left",
            ).pack(anchor="w", padx=15, pady=(0, 6))
        for enchant_name in enchant_names:
            display_name = self._format_enchant_display_name(enchant_name, bane_foe)
            info = enchant_db.get(enchant_name, {})
            block = ctk.CTkFrame(frame, fg_color="#262626", corner_radius=6)
            block.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(
                block,
                text=display_name,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=THEME_ORANGE,
            ).pack(anchor="w", padx=10, pady=(6, 2))
            description = str(info.get("description") or "Special weapon property.")
            ctk.CTkLabel(
                block,
                text=description,
                wraplength=540,
                justify="left",
            ).pack(anchor="w", padx=10, pady=(0, 4))

            abilities = self._enchant_feature_abilities(enchant_name, enchant_db)
            granted = abilities.get("granted_spells") or []
            if granted:
                ctk.CTkLabel(
                    block,
                    text=f"Granted spell{'s' if len(granted) != 1 else ''}: {', '.join(granted)}",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=THEME_TEAL,
                    wraplength=520,
                    justify="left",
                ).pack(anchor="w", padx=10, pady=(0, 4))

            uses = int(abilities.get("uses_per_day") or 0)
            if uses > 0:
                tracker_key = f"gear_{entry['gear_key']}_{enchant_name}"
                self._build_magic_item_daily_tracker(block, tracker_key, uses)

            max_charges = int(abilities.get("max_charges") or 0)
            if max_charges > 0:
                tracker_key = f"gear_{entry['gear_key']}_{enchant_name}"
                self._build_magic_item_charge_tracker(block, tracker_key, max_charges)

            for dice in self._extract_simple_dice_from_description(description):
                dice_lbl = ctk.CTkLabel(
                    block,
                    text=f"({dice})",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#66b3ff",
                    fg_color="#1a2a3a",
                    corner_radius=4,
                    cursor="hand2",
                )
                dice_lbl.pack(anchor="w", padx=10, pady=(2, 6))
                builder = lambda d=dice, lbl=display_name: self._format_talespire_roll(lbl, [d])
                self._bind_talespire_click(dice_lbl, builder)

        gem = self._get_gear_augment_gem(entry["gear_key"])
        if gem:
            gem_info = self._augment_gem_db_for_type(entry["gem_type"]).get(gem, {})
            gem_block = ctk.CTkFrame(frame, fg_color="#1e3330", corner_radius=6)
            gem_block.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(
                gem_block,
                text=gem,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=THEME_TEAL,
            ).pack(anchor="w", padx=10, pady=(6, 2))
            ctk.CTkLabel(
                gem_block,
                text=str(gem_info.get("description") or ""),
                wraplength=540,
                justify="left",
            ).pack(anchor="w", padx=10, pady=(0, 6))
            uses = int(gem_info.get("uses_per_day") or 0)
            if uses > 0:
                self._build_magic_item_daily_tracker(gem_block, f"gem_{entry['gear_key']}", uses)
            max_charges = int(gem_info.get("max_charges") or 0)
            if max_charges > 0:
                self._build_magic_item_charge_tracker(gem_block, f"gem_{entry['gear_key']}", max_charges)

        if entry.get("gem_type") in {"armor", "shield"}:
            self._build_augment_gem_selector(frame, entry["gear_key"], entry["gem_type"])
        elif entry.get("gem_type") == "weapon":
            self._build_augment_gem_selector(frame, entry["gear_key"], "weapon")

        ctk.CTkLabel(frame, text="").pack(pady=2)

    def weapon_attack_gem_suffix(self, weapon_idx: int) -> str:
        gem = self._get_gear_augment_gem(f"weapon_{weapon_idx}")
        if not gem:
            return ""
        return f" — {gem}"

    def build_magical_items_tab(self):
        tab = self.tabview.tab("Magical Items")
        for widget in tab.winfo_children():
            widget.destroy()
        scroll = ctk.CTkScrollableFrame(tab)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        header_row = ctk.CTkFrame(scroll, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            header_row, text="Magical Items",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            header_row,
            text="+",
            width=34,
            height=30,
            fg_color=THEME_TEAL,
            hover_color="#1f7f75",
            font=ctk.CTkFont(size=18, weight="bold"),
            command=self._open_add_custom_magic_item_popup,
        ).pack(side="right")
        primary = getattr(self, "primary_button_color", "#c77626")
        hover_primary = getattr(self, "primary_hover_color", "#a56b32")
        ctk.CTkButton(
            header_row, text="+", width=30, height=28,
            fg_color=primary, hover_color=hover_primary,
            command=lambda: self._open_custom_feature_dialog("magic_item"),
        ).pack(side="right")

        weapon_features = self._get_magical_items_weapon_features()
        armor_feature = self._get_magical_items_armor_feature()
        shield_feature = self._get_magical_items_shield_feature()
        has_gear = bool(weapon_features or armor_feature or shield_feature)

        if weapon_features:
            ctk.CTkLabel(
                scroll, text="Weapons",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=THEME_ORANGE,
            ).pack(anchor="w", pady=(4, 6))
            for entry in weapon_features:
                self._build_gear_enchant_feature_card(scroll, entry)

        if armor_feature:
            ctk.CTkLabel(
                scroll, text="Armor",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=THEME_ORANGE,
            ).pack(anchor="w", pady=(12, 6))
            self._build_gear_enchant_feature_card(scroll, armor_feature)

        if shield_feature:
            ctk.CTkLabel(
                scroll, text="Shield",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=THEME_ORANGE,
            ).pack(anchor="w", pady=(12, 6))
            self._build_gear_enchant_feature_card(scroll, shield_feature)

        equipped = self._get_equipped_magic_items()
        custom_items = self._get_custom_magic_items()
        customs = [f for f in self.data.get("custom_features", []) if f.get("category") == "magic_item"]

        if equipped or custom_items or customs:
            ctk.CTkLabel(
                scroll, text="Gear",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=THEME_ORANGE,
            ).pack(anchor="w", pady=(12, 6))
            for item in equipped:
                self._build_magic_item_feature_card(scroll, item)
            for item in custom_items:
                self._build_magic_item_feature_card(scroll, item)
            for cf in customs:
                try:
                    gidx = self.data.get("custom_features", []).index(cf)
                except ValueError:
                    gidx = -1
                if gidx >= 0:
                    self._build_custom_feature_card(scroll, cf, "magic_item", gidx)

        if not has_gear and not equipped and not custom_items and not customs:
            ctk.CTkLabel(
                scroll,
                text="No magical items equipped. Assign items on the Inventory page, add gear enchants on Combat, or use + to create a custom item.",
                font=ctk.CTkFont(size=13),
                text_color="#888888",
                wraplength=650,
                justify="left",
            ).pack(anchor="w", padx=4, pady=8)