"""Wizard to convert mundane weapon/armor/shield slots into magical items."""

from __future__ import annotations

import re
from tkinter import BooleanVar
import dark_dialog as messagebox

import customtkinter as ctk

THEME_DARK_BG = "#1a1a1a"
THEME_DARK_TRACK = "#2F2F2F"
THEME_ORANGE = "#c77626"
THEME_MAGIC = "#9B59B6"
THEME_MAGIC_HOVER = "#7D3C98"
SELECT_BTN_IDLE = "#555555"
SELECT_BTN_IDLE_HOVER = "#666666"
UNSELECTED_BTN = "#3a3a3a"

WIZARD_WIDTH = 760
WIZARD_HEIGHT = 620
MAX_TOTAL_BONUS = 10

MASTERWORK_COST = {"weapon": 300, "armor": 150, "shield": 150}
BONUS_UNIT_COST = {"weapon": 2000, "armor": 1000, "shield": 1000}
CRAFT_MAGIC_ARMS_AND_ARMOR_FEAT = "Craft Magic Arms and Armor"
CRAFT_XP_PER_1000_GP = 25
CRAFT_GP_DISCOUNT = 0.5

WEAPON_ENCHANT_PRICE_BONUS = {
    "Vorpal": 5,
    "Holy": 2,
    "Unholy": 2,
    "Dancing": 4,
    "Speed": 3,
    "Spell Storing": 1,
    "Brilliant Energy": 4,
    "Disruption": 2,
    "Keen": 1,
    "Ki Focus": 1,
    "Merciful": 1,
    "Mighty Cleaving": 1,
    "Mighty Smiting": 1,
    "Seeking": 1,
    "Shock": 1,
    "Shocking Burst": 2,
    "Flaming": 1,
    "Flaming Burst": 2,
    "Frost": 1,
    "Icy Burst": 2,
    "Corrosive": 1,
    "Acidic Burst": 2,
    "Ghost Touch": 1,
    "Bane": 1,
    "Defending": 1,
    "Distance": 1,
    "Returning": 1,
    "Throwing": 1,
    "Wounding": 2,
    "Anarchic": 2,
    "Axiomatic": 2,
}


def _format_enchant_list(enchants):
    names = [str(name).strip() for name in (enchants or []) if str(name).strip()]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def resolve_gear_base_name(mundane_display_name, sheet, gear_type):
    """Return the mundane gear label widgets use inside trailing parentheses."""
    mundane = str(mundane_display_name or "").strip()
    if not mundane:
        return ""
    if sheet is not None:
        if gear_type == "weapon" and hasattr(sheet, "_resolve_weapon_display_name"):
            base, info = sheet._resolve_weapon_display_name(mundane)
            if info and base:
                return str(base).strip()
        elif gear_type == "armor" and hasattr(sheet, "_resolve_armor_display_name"):
            base, info = sheet._resolve_armor_display_name(mundane)
            if info and base:
                return str(base).strip()
        elif gear_type == "shield" and hasattr(sheet, "_resolve_shield_display_name"):
            base, info = sheet._resolve_shield_display_name(mundane)
            if info and base:
                return str(base).strip()
        if hasattr(sheet, "_extract_parenthetical_base_name"):
            base = sheet._extract_parenthetical_base_name(mundane)
            if base:
                return str(base).strip()
    match = re.search(r"\(([^)]+)\)\s*$", mundane)
    if match:
        return match.group(1).strip()
    return mundane


def ensure_gear_type_suffix(display_name, mundane_display_name, sheet, gear_type):
    """Keep a trailing (weapon/armor/shield) suffix so gear widgets can resolve the item."""
    display = str(display_name or "").strip()
    if not display:
        return display
    if re.search(r"\([^)]+\)\s*$", display):
        return display
    base = resolve_gear_base_name(mundane_display_name, sheet, gear_type)
    if not base:
        return display
    if display.lower() == base.lower():
        return display
    return f"{display} ({base})"


def format_magical_item_name(enhancement, enchants, mundane_display_name, gear_base=None):
    display = str(mundane_display_name or "").strip()
    base = str(gear_base or "").strip() or display
    enh = max(0, int(enhancement or 0))
    enchant_text = _format_enchant_list(enchants)
    if enh <= 0 and not enchant_text:
        return display
    prefix = f"+{enh} " if enh > 0 else ""
    if enchant_text:
        return f"{prefix}{base} of {enchant_text} ({base})"
    return f"{prefix}{base} ({base})"


def enchant_pricing_info(gear_type, enchant_name, enchant_db):
    """Return pricing for one special ability: flat_gp and/or bonus equivalent."""
    info = (enchant_db or {}).get(enchant_name, {})
    if isinstance(info, dict):
        if info.get("flat_gp") is not None:
            return {
                "flat_gp": max(0.0, float(info.get("flat_gp") or 0)),
                "price_bonus": 0,
            }
        if info.get("price_bonus") is not None:
            return {
                "flat_gp": 0.0,
                "price_bonus": max(0, int(info.get("price_bonus") or 0)),
            }
    if gear_type == "weapon":
        return {
            "flat_gp": 0.0,
            "price_bonus": WEAPON_ENCHANT_PRICE_BONUS.get(enchant_name, 1),
        }
    return {"flat_gp": 0.0, "price_bonus": 1}


def enchant_price_bonus(gear_type, enchant_name, enchant_db):
    return enchant_pricing_info(gear_type, enchant_name, enchant_db)["price_bonus"]


def enchant_price_label(gear_type, enchant_name, enchant_db):
    """Human-readable market-price modifier for the enchant picker."""
    info = enchant_pricing_info(gear_type, enchant_name, enchant_db)
    flat_gp = info["flat_gp"]
    if flat_gp > 0:
        if flat_gp == int(flat_gp):
            return f"+{int(flat_gp):,} gp"
        return f"+{flat_gp:,.0f} gp"
    bonus = info["price_bonus"]
    if bonus == 1:
        return "+1 bonus"
    return f"+{bonus} bonus"


def calculate_conversion_pricing(gear_type, base_value, enhancement, enchants, enchant_db):
    base_value = max(0.0, float(base_value or 0))
    enh = max(0, int(enhancement or 0))
    chosen = [str(name).strip() for name in (enchants or []) if str(name).strip()]
    ability_bonus = 0
    flat_gp_total = 0.0
    for name in chosen:
        info = enchant_pricing_info(gear_type, name, enchant_db)
        ability_bonus += info["price_bonus"]
        flat_gp_total += info["flat_gp"]
    total_equiv = enh + ability_bonus
    masterwork = MASTERWORK_COST.get(gear_type, 0)
    unit = BONUS_UNIT_COST.get(gear_type, 2000)
    magical_value = base_value + masterwork + (total_equiv ** 2) * unit + flat_gp_total
    conversion_cost = max(0.0, magical_value - base_value)
    return {
        "base_value": base_value,
        "masterwork_cost": masterwork,
        "enhancement": enh,
        "ability_bonus": ability_bonus,
        "flat_gp_total": flat_gp_total,
        "total_equiv": total_equiv,
        "magical_value": magical_value,
        "conversion_cost": conversion_cost,
    }


def calculate_craft_payment(pricing):
    magical_value = float(pricing.get("magical_value", 0) or 0)
    conversion_cost = float(pricing.get("conversion_cost", 0) or 0)
    craft_gp = conversion_cost * CRAFT_GP_DISCOUNT
    craft_xp = int(magical_value // 1000) * CRAFT_XP_PER_1000_GP
    return craft_gp, craft_xp


class MagicalItemConversionWizard:
    STEPS = ("select", "enhancement", "enchants", "review")

    def __init__(self, sheet, gear_type, on_complete):
        self.sheet = sheet
        self.gear_type = str(gear_type or "weapon").strip().lower()
        if self.gear_type not in ("weapon", "armor", "shield"):
            raise ValueError(f"Unsupported gear type: {gear_type}")
        self.on_complete = on_complete
        self.popup = ctk.CTkToplevel(sheet.root)
        self.popup.title("Convert to Magical Item")
        self.popup.configure(fg_color=THEME_DARK_BG)
        self.popup.grab_set()
        self.popup.minsize(WIZARD_WIDTH, WIZARD_HEIGHT)
        sheet._center_popup_on_root(self.popup, WIZARD_WIDTH, WIZARD_HEIGHT)

        self.step_index = 0
        self.selected_slot = None
        self.enhancement_var = ctk.StringVar(value="1")
        self.enhancement_var.trace_add("write", lambda *_args: self._update_cost_total())
        self.payment_var = ctk.StringVar(value="pay")
        self.name_var = ctk.StringVar(value="")
        self.enchant_vars = {}
        self._enchant_checkboxes = {}
        self._bonus_total_label = None
        self._detail_label = None
        self._price_label = None
        self._name_entry = None
        self._cost_total_label = None
        self._content = ctk.CTkFrame(self.popup, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=20, pady=(16, 8))

        cost_bar = ctk.CTkFrame(self.popup, fg_color="#2a2a2a", corner_radius=6)
        cost_bar.pack(fill="x", padx=20, pady=(0, 8))
        self._cost_total_label = ctk.CTkLabel(
            cost_bar,
            text="Conversion cost: — gp",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#888888",
            anchor="w",
        )
        self._cost_total_label.pack(fill="x", padx=12, pady=8)

        footer = ctk.CTkFrame(self.popup, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 16))
        self._back_btn = ctk.CTkButton(
            footer, text="Back", width=108, height=36, fg_color="#555555",
            hover_color="#666666", command=self._go_back,
        )
        self._back_btn.pack(side="left")
        self._next_btn = ctk.CTkButton(
            footer, text="Next", width=108, height=36,
            fg_color=getattr(sheet, "primary_button_color", THEME_ORANGE),
            hover_color=getattr(sheet, "primary_hover_color", "#a56b32"),
            command=self._go_next,
        )
        self._next_btn.pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=108, height=36, fg_color="#555555",
            hover_color="#666666", command=self._cancel,
        ).pack(side="right", padx=(0, 8))

        self._render_step()

    def _cancel(self):
        self.popup.destroy()

    def _has_craft_magic_arms_and_armor(self):
        if hasattr(self.sheet, "_get_all_selected_feats"):
            return CRAFT_MAGIC_ARMS_AND_ARMOR_FEAT in self.sheet._get_all_selected_feats()
        feats = set()
        for feat in self.sheet.data.get("general_feats", []):
            if feat and str(feat).strip():
                feats.add(str(feat).strip())
        for feat in (self.sheet.data.get("bonus_feats") or {}).values():
            if feat and str(feat).strip():
                feats.add(str(feat).strip())
        human = str(self.sheet.data.get("human_bonus_feat", "") or "").strip()
        if human:
            feats.add(human)
        return CRAFT_MAGIC_ARMS_AND_ARMOR_FEAT in feats

    def _enchant_db(self):
        if self.gear_type == "weapon":
            return getattr(self.sheet, "weapon_enchants_db", {}) or {}
        if self.gear_type == "armor":
            return getattr(self.sheet, "armor_enchants_db", {}) or {}
        return getattr(self.sheet, "shield_enchants_db", {}) or {}

    def _filled_slots(self):
        if self.gear_type == "weapon":
            slots = []
            for idx in range(5):
                weapon = self.sheet._get_weapon_slot(idx)
                name = str(weapon.get("name", "")).strip()
                if name:
                    slots.append({
                        "slot_index": idx,
                        "display_name": name,
                        "value": float(weapon.get("value", 0) or 0),
                        "enh": int(weapon.get("enh", 0) or 0),
                        "inventory_id": str(weapon.get("inventory_id", "") or "").strip(),
                    })
            return slots
        if self.gear_type == "armor":
            armor = dict(self.sheet.data.get("armor") or {})
            if hasattr(self.sheet, "armor_vars"):
                try:
                    armor["name"] = self.sheet.armor_vars["name"].get()
                    armor["value"] = float(self.sheet.armor_vars.get("value", ctk.StringVar(value="0")).get() or 0)
                    armor["enh"] = int(self.sheet.armor_vars.get("enh", ctk.StringVar(value="0")).get() or 0)
                    armor["inventory_id"] = str(self.sheet.data.get("armor", {}).get("inventory_id", "") or "")
                except Exception:
                    pass
            name = str(armor.get("name", "")).strip()
            if not name:
                return []
            return [{
                "slot_index": None,
                "display_name": name,
                "value": float(armor.get("value", 0) or 0),
                "enh": int(armor.get("enh", 0) or 0),
                "inventory_id": str(armor.get("inventory_id", "") or "").strip(),
            }]
        shield = dict(self.sheet.data.get("shield") or {})
        if hasattr(self.sheet, "shield_vars"):
            try:
                shield["name"] = self.sheet.shield_vars["name"].get()
                shield["value"] = float(self.sheet.shield_vars.get("value", ctk.StringVar(value="0")).get() or 0)
                shield["enh"] = int(self.sheet.shield_vars.get("enh", ctk.StringVar(value="0")).get() or 0)
                shield["inventory_id"] = str(self.sheet.data.get("shield", {}).get("inventory_id", "") or "")
            except Exception:
                pass
        name = str(shield.get("name", "")).strip()
        if not name:
            return []
        return [{
            "slot_index": None,
            "display_name": name,
            "value": float(shield.get("value", 0) or 0),
            "enh": int(shield.get("enh", 0) or 0),
            "inventory_id": str(shield.get("inventory_id", "") or "").strip(),
        }]

    def _gear_base_name(self, mundane_display_name):
        return resolve_gear_base_name(mundane_display_name, self.sheet, self.gear_type)

    def _selected_enchants(self):
        return sorted(name for name, var in self.enchant_vars.items() if var.get())

    def _enchant_counts_toward_bonus_cap(self, enchant_name):
        info = enchant_pricing_info(self.gear_type, enchant_name, self._enchant_db())
        return int(info.get("price_bonus") or 0) > 0

    def _bonus_total_with_selection(self, enchant_name=None, *, include_enchant=False):
        try:
            enh = max(0, int(self.enhancement_var.get() or 0))
        except (TypeError, ValueError):
            enh = 0
        total = enh
        for name, var in self.enchant_vars.items():
            selected = bool(var.get())
            if enchant_name is not None and name == enchant_name:
                selected = include_enchant
            if not selected:
                continue
            if self._enchant_counts_toward_bonus_cap(name):
                total += enchant_pricing_info(self.gear_type, name, self._enchant_db())["price_bonus"]
        return total

    def _current_bonus_equivalent(self):
        return self._bonus_total_with_selection()

    def _enchant_cap_blocks_adding(self, enchant_name):
        if not self._enchant_counts_toward_bonus_cap(enchant_name):
            return False
        return (
            self._bonus_total_with_selection(enchant_name, include_enchant=True)
            > MAX_TOTAL_BONUS
        )

    def _refresh_enchant_checkbox_states(self):
        for enchant_name, cb in (self._enchant_checkboxes or {}).items():
            var = self.enchant_vars.get(enchant_name)
            if var is None:
                continue
            if var.get():
                cb.configure(state="normal")
                continue
            if self._enchant_cap_blocks_adding(enchant_name):
                cb.configure(state="disabled")
            else:
                cb.configure(state="normal")
        if self._bonus_total_label is not None:
            self._bonus_total_label.configure(
                text=(
                    f"Equivalent bonus: +{self._current_bonus_equivalent()} / +{MAX_TOTAL_BONUS} "
                    "(enhancement + special abilities; gold-only abilities do not count)"
                ),
            )

    def _on_enchant_toggle(self, enchant_name):
        var = self.enchant_vars.get(enchant_name)
        if var is None:
            return
        if var.get() and self._enchant_cap_blocks_adding(enchant_name):
            var.set(False)
            messagebox.showwarning(
                "Bonus Limit",
                (
                    f"Cannot add {enchant_name}: total equivalent bonus cannot exceed "
                    f"+{MAX_TOTAL_BONUS} (enhancement + special abilities).\n\n"
                    "Gold-only special abilities can still be added at the cap."
                ),
                parent=self.popup,
            )
            return
        self._update_default_name()
        self._refresh_enchant_checkbox_states()

    def _current_pricing(self):
        slot = self.selected_slot or {}
        try:
            enh = max(0, int(self.enhancement_var.get() or 0))
        except (TypeError, ValueError):
            enh = 0
        return calculate_conversion_pricing(
            self.gear_type,
            slot.get("value", 0),
            enh,
            self._selected_enchants(),
            self._enchant_db(),
        )

    def _update_default_name(self):
        slot = self.selected_slot or {}
        try:
            enh = max(0, int(self.enhancement_var.get() or 0))
        except (TypeError, ValueError):
            enh = 0
        mundane = slot.get("display_name", "")
        default_name = format_magical_item_name(
            enh,
            self._selected_enchants(),
            mundane,
            gear_base=self._gear_base_name(mundane),
        )
        if self._name_entry is not None:
            if not str(self.name_var.get() or "").strip():
                self.name_var.set(default_name)
        else:
            self.name_var.set(default_name)
        if self._price_label is not None:
            pricing = self._current_pricing()
            gifted = getattr(self, "payment_var", None) and self.payment_var.get() == "gifted"
            if gifted:
                payment_lines = "Gifted — no coin payment on convert"
            else:
                payment_lines = (
                    f"Purchase price: {pricing['conversion_cost']:,.0f} gp "
                    f"(paid via coin popup on convert)"
                )
            flat_line = ""
            if pricing.get("flat_gp_total", 0) > 0:
                flat_line = (
                    f"Flat ability cost: +{pricing['flat_gp_total']:,.0f} gp\n"
                )
            self._price_label.configure(
                text=(
                    f"Base value: {pricing['base_value']:,.0f} gp\n"
                    f"Masterwork: +{pricing['masterwork_cost']:,.0f} gp\n"
                    f"Equivalent bonus: +{pricing['total_equiv']} "
                    f"(+{pricing['enhancement']} enhancement, +{pricing['ability_bonus']} abilities)\n"
                    f"{flat_line}"
                    f"Magical market value: {pricing['magical_value']:,.0f} gp\n"
                    f"{payment_lines}"
                )
            )
        self._update_cost_total()

    def _slot_is_selected(self, slot):
        if not self.selected_slot or not slot:
            return False
        selected = self.selected_slot
        slot_id = str(slot.get("inventory_id") or "").strip()
        selected_id = str(selected.get("inventory_id") or "").strip()
        if slot_id and selected_id:
            return slot_id == selected_id
        if self.gear_type == "weapon":
            return selected.get("slot_index") == slot.get("slot_index")
        return selected.get("display_name") == slot.get("display_name")

    def _update_cost_total(self):
        if self._cost_total_label is None:
            return
        if not self.selected_slot:
            self._cost_total_label.configure(
                text="Conversion cost: — gp",
                text_color="#888888",
            )
            return
        pricing = self._current_pricing()
        gifted = getattr(self, "payment_var", None) and self.payment_var.get() == "gifted"
        if gifted:
            cost_note = "Gifted (no charge)"
        else:
            cost_note = f"Purchase price: {pricing['conversion_cost']:,.0f} gp"
        bonus_note = f"   •   Bonus +{self._current_bonus_equivalent()}/{MAX_TOTAL_BONUS}"
        self._cost_total_label.configure(
            text=(
                f"{cost_note}"
                f"   •   Market value: {pricing['magical_value']:,.0f} gp"
                f"{bonus_note}"
            ),
            text_color="#7fd6c7",
        )

    def _clear_content(self):
        for child in self._content.winfo_children():
            child.destroy()
        self._detail_label = None
        self._price_label = None
        self._name_entry = None
        self._enchant_checkboxes = {}
        self._bonus_total_label = None

    def _render_step(self):
        self._clear_content()
        step = self.STEPS[self.step_index]
        titles = {
            "select": "Select Item",
            "enhancement": "Enhancement Bonus",
            "enchants": "Special Abilities",
            "review": "Review & Convert",
        }
        ctk.CTkLabel(
            self._content,
            text=titles.get(step, step.title()),
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w", pady=(0, 8))

        if step == "select":
            self._render_select_step()
        elif step == "enhancement":
            self._render_enhancement_step()
        elif step == "enchants":
            self._render_enchants_step()
        else:
            self._render_review_step()

        self._back_btn.configure(state="normal" if self.step_index > 0 else "disabled")
        if step == "review":
            gifted = getattr(self, "payment_var", None) and self.payment_var.get() == "gifted"
            pricing = self._current_pricing() if self.selected_slot else {}
            cost = float(pricing.get("conversion_cost", 0) or 0)
            self._next_btn.configure(
                text="Convert" if gifted or cost <= 0.001 else "Purchase & Convert",
            )
        else:
            self._next_btn.configure(text="Next")
        self._update_cost_total()

    def _render_select_step(self):
        gear_label = {"weapon": "weapon slot", "armor": "armor", "shield": "shield"}[self.gear_type]
        ctk.CTkLabel(
            self._content,
            text=f"Choose an item already assigned in your {gear_label}.",
            text_color="#aaaaaa",
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        slots = self._filled_slots()
        if not slots:
            ctk.CTkLabel(
                self._content,
                text="No filled slots found. Assign a mundane item first.",
                text_color="#d9534f",
            ).pack(anchor="w", pady=12)
            self._next_btn.configure(state="disabled")
            return

        self._next_btn.configure(state="normal")
        scroll = ctk.CTkScrollableFrame(self._content, height=380)
        scroll.pack(fill="both", expand=True)
        for slot in slots:
            label = slot["display_name"]
            if self.gear_type == "weapon":
                label = f"Slot {slot['slot_index'] + 1}: {label}"
            row = ctk.CTkFrame(scroll, fg_color="#2F2F2F")
            row.pack(fill="x", pady=4)
            is_selected = self._slot_is_selected(slot)
            ctk.CTkLabel(
                row, text=label, anchor="w",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#7fd6c7" if is_selected else ("#DCE4EE", "#DCE4EE"),
            ).pack(side="left", padx=12, pady=8)
            ctk.CTkButton(
                row,
                text="Selected" if is_selected else "Select",
                width=88,
                fg_color=THEME_MAGIC if is_selected else SELECT_BTN_IDLE,
                hover_color=THEME_MAGIC_HOVER if is_selected else SELECT_BTN_IDLE_HOVER,
                command=lambda s=slot: self._choose_slot(s),
            ).pack(side="right", padx=10, pady=6)

    def _choose_slot(self, slot):
        self.selected_slot = dict(slot)
        self._render_step()

    def _render_enhancement_step(self):
        ctk.CTkLabel(
            self._content,
            text="What is the enhancement bonus for this magical item?",
            text_color="#aaaaaa",
        ).pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(self._content, text="Enhancement bonus (+0 to +5):").pack(anchor="w")
        ctk.CTkComboBox(
            self._content,
            values=[str(i) for i in range(0, 6)],
            variable=self.enhancement_var,
            width=120,
            command=lambda _val: self._update_default_name(),
        ).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(
            self._content,
            text=(
                f"Enhancement plus special-ability bonuses cannot exceed +{MAX_TOTAL_BONUS} total. "
                "Gold-only abilities (flat gp price) do not count toward that limit."
            ),
            text_color="#888888",
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _render_enchants_step(self):
        db = self._enchant_db()
        if not db:
            ctk.CTkLabel(
                self._content,
                text="No enchantment database loaded for this item type.",
                text_color="#d9534f",
            ).pack(anchor="w", pady=12)
            return

        detail = ctk.CTkFrame(self._content, fg_color="#2F2F2F", height=52, corner_radius=6)
        detail.pack(fill="x", pady=(0, 8))
        detail.pack_propagate(False)
        self._detail_label = ctk.CTkLabel(
            detail,
            text="Select special abilities to add. Hover or click to preview.",
            wraplength=680,
            justify="left",
            text_color="#aaaaaa",
            anchor="nw",
        )
        self._detail_label.pack(fill="both", expand=True, padx=10, pady=8)

        self._bonus_total_label = ctk.CTkLabel(
            self._content,
            text=(
                f"Equivalent bonus: +{self._current_bonus_equivalent()} / +{MAX_TOTAL_BONUS} "
                "(enhancement + special abilities; gold-only abilities do not count)"
            ),
            text_color="#aaaaaa",
            wraplength=700,
            justify="left",
        )
        self._bonus_total_label.pack(anchor="w", pady=(0, 6))

        scroll = ctk.CTkScrollableFrame(self._content, height=330)
        scroll.pack(fill="both", expand=True)

        self.enchant_vars = {}
        self._enchant_checkboxes = {}
        for enchant_name in sorted(db.keys()):
            info = db.get(enchant_name, {})
            row = ctk.CTkFrame(scroll)
            row.pack(fill="x", pady=3, padx=4)
            var = BooleanVar(value=False)
            self.enchant_vars[enchant_name] = var
            price_tag = enchant_price_label(self.gear_type, enchant_name, db)
            cb = ctk.CTkCheckBox(
                row,
                text=f"{enchant_name}  ({price_tag})",
                variable=var,
                width=420,
                command=lambda name=enchant_name: self._on_enchant_toggle(name),
            )
            cb.pack(side="left", padx=8, pady=6)
            self._enchant_checkboxes[enchant_name] = cb

            def show_detail(_event=None, name=enchant_name, record=info):
                desc = str(record.get("description", "") or "").strip() or "No description."
                if self._detail_label is not None:
                    blocked = self._enchant_cap_blocks_adding(name)
                    prefix = ""
                    if blocked and not var.get():
                        prefix = f"[At +{MAX_TOTAL_BONUS} bonus cap] "
                    self._detail_label.configure(text=f"{prefix}{name}: {desc}")

            cb.bind("<Enter>", show_detail)
            cb.bind("<Button-1>", show_detail, add="+")

        self._refresh_enchant_checkbox_states()

    def _render_review_step(self):
        self._update_default_name()
        ctk.CTkLabel(
            self._content,
            text=(
                "Confirm the magical item name. When you convert, the standard "
                "inventory purchase popup will collect coins (Person / Container / Banked)."
            ),
            text_color="#aaaaaa",
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        self._price_label = ctk.CTkLabel(
            self._content,
            text="",
            justify="left",
            anchor="nw",
            text_color="#cccccc",
        )
        self._price_label.pack(anchor="w", pady=(0, 12))
        self._update_default_name()

        pay_row = ctk.CTkFrame(self._content, fg_color="transparent")
        pay_row.pack(fill="x", pady=(0, 10))
        ctk.CTkRadioButton(
            pay_row,
            text="Pay conversion cost",
            variable=self.payment_var,
            value="pay",
            command=self._update_cost_total,
        ).pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(
            pay_row,
            text="Gifted (no cost)",
            variable=self.payment_var,
            value="gifted",
            command=self._update_cost_total,
        ).pack(side="left")

        ctk.CTkLabel(self._content, text="Magical item name:").pack(anchor="w")
        self._name_entry = ctk.CTkEntry(self._content, textvariable=self.name_var, width=620)
        self._name_entry.pack(anchor="w", pady=(4, 12))
        ctk.CTkButton(
            self._content, text="Reset Default Name", width=160, fg_color="#555555",
            command=lambda: self.name_var.set(
                format_magical_item_name(
                    int(self.enhancement_var.get() or 0),
                    self._selected_enchants(),
                    (self.selected_slot or {}).get("display_name", ""),
                    gear_base=self._gear_base_name((self.selected_slot or {}).get("display_name", "")),
                )
            ),
        ).pack(anchor="w", pady=(0, 12))

    def _go_back(self):
        if self.step_index <= 0:
            return
        self.step_index -= 1
        self._render_step()

    def _go_next(self):
        step = self.STEPS[self.step_index]
        if step == "select":
            if not self.selected_slot:
                messagebox.showwarning("Select Item", "Choose an item to convert.", parent=self.popup)
                return
        elif step == "enhancement":
            try:
                enh = int(self.enhancement_var.get() or 0)
            except (TypeError, ValueError):
                messagebox.showwarning("Enhancement", "Enter a valid enhancement bonus.", parent=self.popup)
                return
            if enh < 0 or enh > 5:
                messagebox.showwarning("Enhancement", "Enhancement bonus must be between +0 and +5.", parent=self.popup)
                return
        elif step == "enchants":
            try:
                enh = int(self.enhancement_var.get() or 0)
            except (TypeError, ValueError):
                enh = 0
            if enh <= 0 and not self._selected_enchants():
                messagebox.showwarning(
                    "Enchantments",
                    "Choose at least a +1 enhancement bonus or one special ability.",
                    parent=self.popup,
                )
                return
            if self._current_bonus_equivalent() > MAX_TOTAL_BONUS:
                messagebox.showwarning(
                    "Bonus Limit",
                    f"Total equivalent bonus cannot exceed +{MAX_TOTAL_BONUS}.",
                    parent=self.popup,
                )
                return
        elif step == "review":
            self._finish()
            return

        self.step_index += 1
        self._render_step()

    def _finish(self):
        slot = self.selected_slot or {}
        try:
            enh = max(0, int(self.enhancement_var.get() or 0))
        except (TypeError, ValueError):
            messagebox.showwarning("Enhancement", "Enter a valid enhancement bonus.", parent=self.popup)
            return
        enchants = self._selected_enchants()
        if enh <= 0 and not enchants:
            messagebox.showwarning(
                "Enchantments",
                "Choose at least a +1 enhancement bonus or one special ability.",
                parent=self.popup,
            )
            return
        if self._current_bonus_equivalent() > MAX_TOTAL_BONUS:
            messagebox.showwarning(
                "Bonus Limit",
                f"Total equivalent bonus cannot exceed +{MAX_TOTAL_BONUS}.",
                parent=self.popup,
            )
            return

        mundane_display_name = slot.get("display_name", "")
        display_name = str(self.name_var.get() or "").strip()
        if not display_name:
            display_name = format_magical_item_name(
                enh,
                enchants,
                mundane_display_name,
                gear_base=self._gear_base_name(mundane_display_name),
            )
        display_name = ensure_gear_type_suffix(
            display_name, mundane_display_name, self.sheet, self.gear_type,
        )

        pricing = self._current_pricing()
        cost_gp = float(pricing.get("conversion_cost", 0) or 0)
        gifted = self.payment_var.get() == "gifted"
        if not messagebox.askyesno(
            "Confirm Conversion",
            (
                f"Convert to:\n{display_name}\n\n"
                + (
                    "Gifted — no coin payment.\n\n"
                    if gifted
                    else (
                        f"Purchase price: {cost_gp:,.0f} gp (coin popup opens next).\n\n"
                        if cost_gp > 0.001
                        else ""
                    )
                )
                + "This cannot be undone."
            ),
            parent=self.popup,
        ):
            return

        result = {
            "gear_type": self.gear_type,
            "slot_index": slot.get("slot_index"),
            "inventory_id": slot.get("inventory_id", ""),
            "mundane_display_name": slot.get("display_name", ""),
            "display_name": display_name,
            "enhancement": enh,
            "enchants": enchants,
            "magical_value": pricing["magical_value"],
            "cost_gp": cost_gp,
            "cost_xp": 0,
            "gifted": gifted,
            "crafted": False,
        }
        self.popup.destroy()
        if callable(self.on_complete):
            self.on_complete(result)