"""Shared animated local dice roller popup (D&D Before + D&D Behind)."""

from __future__ import annotations

import random
import re
import threading

import customtkinter as ctk

THEME_ORANGE = "#c77626"
THEME_TEAL = "#1f9d8f"


def normalize_dice_group(expr):
    """Extract an NdM(+/-X) token from a bare or labeled TaleSpire group."""
    text = str(expr or "").strip().lower().replace(" ", "")
    if not text:
        return ""
    if re.match(r"^(\d*)d(\d+)([+-]\d+)?$", text):
        return text
    match = re.search(r"(\d*d\d+(?:[+-]\d+)?)", text)
    return match.group(1) if match else text


def parse_dice_expression(expr):
    """Parse NdS(+/-M) tokens such as 1d20+5, d6, or 2d6-1."""
    text = normalize_dice_group(expr)
    match = re.match(r"^(\d*)d(\d+)([+-]\d+)?$", text)
    if not match:
        return None
    count_str, sides_str, mod_str = match.groups()
    count = int(count_str) if count_str else 1
    sides = int(sides_str)
    modifier = int(mod_str) if mod_str else 0
    return count, sides, modifier


def roll_dice_expression(expr):
    """Roll one NdM(+/-X) group and return totals plus animation bounds."""
    parsed = parse_dice_expression(expr)
    if not parsed:
        return {
            "display": str(expr or "").strip(),
            "rolls": [],
            "modifier": 0,
            "total": 0,
            "min_total": 0,
            "max_total": 0,
            "count": 0,
            "sides": 0,
        }
    count, sides, modifier = parsed
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier
    return {
        "display": normalize_dice_group(expr),
        "rolls": rolls,
        "modifier": modifier,
        "total": total,
        "min_total": count + modifier,
        "max_total": (count * sides) + modifier,
        "count": count,
        "sides": sides,
    }


def format_roll_result(group_results):
    if not group_results:
        return "—"
    if len(group_results) == 1:
        return str(group_results[0]["total"])
    return " / ".join(str(g["total"]) for g in group_results)


def random_roll_display(group_results):
    if not group_results:
        return "—"
    parts = []
    for group in group_results:
        rolls = list(group.get("rolls") or [])
        modifier = int(group.get("modifier", 0) or 0)
        lo = int(group.get("min_total", 0) or 0)
        hi = int(group.get("max_total", 0) or 0)
        if hi < lo:
            lo, hi = hi, lo
        if rolls:
            sides = max(2, int(group.get("sides", 0) or 0) or 6)
            preview = [random.randint(1, sides) for _ in rolls]
            body = "+".join(str(value) for value in preview)
            if modifier:
                body += f"{modifier:+d}"
            parts.append(body)
        elif lo == 0 and hi == 0:
            parts.append("0")
        else:
            parts.append(str(random.randint(lo, hi)))
    if len(parts) == 1:
        return parts[0]
    return " / ".join(parts)


def resolve_plain_dice_roll(expr, *, label=None):
    """Resolve a bare dice expression (statblock / BCC [roll:expr|label] clicks)."""
    display_label = str(label or expr or "Roll").strip() or "Roll"
    formula = str(expr or "").strip().lower()
    group = roll_dice_expression(formula)
    return {
        "label": display_label,
        "formula": formula,
        "groups": [group],
        "result_text": format_roll_result([group]),
    }


def parse_talespire_roll_string(roll_text, *, default_character="Character"):
    """Split a TaleSpire roll string into label and dice groups."""
    text = str(roll_text or "").strip()
    if not text.startswith("!") or ":" not in text:
        return None
    header, groups_str = text[1:].split(":", 1)
    header = header.strip()
    groups = [g.strip().lower() for g in groups_str.split("/") if g.strip()]
    if not groups:
        return None
    character = str(default_character or "Character").strip()
    label = header
    if character and header.startswith(character):
        label = header[len(character):].strip() or header
    return {
        "label": label or "Roll",
        "groups": groups,
        "formula": " / ".join(groups),
    }


def resolve_talespire_roll(roll_text, *, default_character="Character"):
    parsed = parse_talespire_roll_string(roll_text, default_character=default_character)
    if not parsed:
        return None
    group_results = [roll_dice_expression(expr) for expr in parsed["groups"]]
    return {
        "label": parsed["label"],
        "formula": parsed["formula"],
        "groups": group_results,
        "result_text": format_roll_result(group_results),
    }


class DiceRoller:
    """Animated centered dice popup with click-to-dismiss after the roll is shown."""

    def __init__(self, host):
        self.host = host

    def _root(self):
        return getattr(self.host, "root", None)

    def _primary_color(self):
        return getattr(self.host, "primary_button_color", THEME_ORANGE)

    def _secondary_color(self):
        return getattr(self.host, "secondary_button_color", THEME_TEAL)

    def _center_popup(self, popup, width, height):
        center = getattr(self.host, "_center_popup_on_root", None)
        if callable(center):
            center(popup, width, height)
            return
        root = self._root()
        if root is None:
            return
        popup.update_idletasks()
        pos_x = root.winfo_rootx() + max(0, (root.winfo_width() - width) // 2)
        pos_y = root.winfo_rooty() + max(0, (root.winfo_height() - height) // 2)
        popup.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

    def close_popup(self):
        popup = getattr(self.host, "_dice_roll_popup", None)
        setattr(self.host, "_dice_roll_popup", None)
        if popup is None:
            return
        try:
            if popup.winfo_exists():
                popup.destroy()
        except Exception:
            pass

    def show_popup(
        self,
        roll_result,
        *,
        ammo_detail=None,
        on_complete=None,
        publish_roll=True,
        log_totals_only=False,
    ):
        self.close_popup()
        if not roll_result:
            return
        root = self._root()
        if root is None:
            return

        completion_applied = {"value": False}

        def _apply_on_complete():
            if completion_applied["value"] or on_complete is None:
                return
            completion_applied["value"] = True
            try:
                on_complete(roll_result)
            except Exception:
                pass

        primary = self._primary_color()
        secondary = self._secondary_color()

        popup = ctk.CTkToplevel(root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(fg_color="#141414")
        width, height = 260, (172 if ammo_detail else 150)
        self._center_popup(popup, width, height)

        frame = ctk.CTkFrame(popup, fg_color="#1e1e1e", corner_radius=10, border_width=1, border_color="#333333")
        frame.pack(fill="both", expand=True, padx=2, pady=2)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            header,
            text=roll_result["label"],
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=primary,
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            header,
            text=roll_result["formula"],
            font=ctk.CTkFont(size=12),
            text_color=primary,
            anchor="w",
        ).pack(fill="x", pady=(2, 0))
        if ammo_detail:
            ctk.CTkLabel(
                frame,
                text=ammo_detail,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=secondary,
            ).pack(pady=(4, 0))

        result_lbl = ctk.CTkLabel(
            frame,
            text="…",
            font=ctk.CTkFont(size=34, weight="bold"),
            text_color=secondary,
        )
        result_lbl.pack(pady=(8, 14))

        setattr(self.host, "_dice_roll_popup", popup)
        final_text = roll_result["result_text"]
        group_results = roll_result.get("groups") or []
        animation_ms = 500
        frame_count = 10
        frame_delay = max(20, animation_ms // frame_count)
        animation_done = {"value": False}
        auto_close_timer = {"id": None}

        def _dismiss(_event=None):
            if not animation_done["value"]:
                return
            if auto_close_timer["id"] is not None:
                try:
                    popup.after_cancel(auto_close_timer["id"])
                except Exception:
                    pass
            self.close_popup()

        popup.bind("<Button-1>", _dismiss)
        frame.bind("<Button-1>", _dismiss)
        result_lbl.bind("<Button-1>", _dismiss)
        header.bind("<Button-1>", _dismiss)

        def _on_animation_complete():
            animation_done["value"] = True
            result_lbl.configure(text=final_text)
            _apply_on_complete()
            auto_close_timer["id"] = popup.after(10000, self.close_popup)

        def _animate(frame_idx=0):
            if getattr(self.host, "_dice_roll_popup", None) is not popup:
                return
            try:
                if not popup.winfo_exists():
                    return
            except Exception:
                return
            if frame_idx >= frame_count:
                _on_animation_complete()
                return
            if frame_idx >= frame_count - 1:
                result_lbl.configure(text=final_text)
            else:
                result_lbl.configure(text=random_roll_display(group_results))
            popup.after(frame_delay, lambda: _animate(frame_idx + 1))

        if publish_roll:
            publish = getattr(self.host, "_publish_local_dice_roll", None)
            if callable(publish):
                try:
                    publish(roll_result, totals_only=log_totals_only)
                except TypeError:
                    publish(roll_result)

        _animate(0)

    def roll_plain_expression(self, expr, *, label=None, publish_roll=True, log_totals_only=False):
        result = resolve_plain_dice_roll(expr, label=label)
        self.show_popup(result, publish_roll=publish_roll, log_totals_only=log_totals_only)
        return result

    def begin_talespire_roll(self, roll_text, *, ammo_detail=None, on_complete=None, default_character="Character"):
        def _worker():
            try:
                resolved = resolve_talespire_roll(roll_text, default_character=default_character)
            except Exception:
                resolved = None
            root = self._root()
            if root is None:
                return
            root.after(
                0,
                lambda: self.show_popup(
                    resolved,
                    ammo_detail=ammo_detail,
                    on_complete=on_complete,
                    publish_roll=True,
                    log_totals_only=False,
                ),
            )

        threading.Thread(target=_worker, daemon=True).start()