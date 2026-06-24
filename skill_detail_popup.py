"""SRD skill detail popup for the Stats page skills widget."""

from __future__ import annotations

import json
import os
import sys
import tkinter as tk

import customtkinter as ctk

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    Image = ImageDraw = ImageFont = None
    HAS_PIL = False

THEME_ORANGE = "#c77626"
THEME_TEAL = "#1f9d8f"
THEME_DARK_BG = "#1a1a1a"
THEME_PANEL = "#242424"
THEME_BORDER = "#3a3a3a"
THEME_MUTED = "#aaaaaa"

POPUP_WIDTH = 720
POPUP_HEIGHT = 640
BANNER_HEIGHT = 50

_SKILLS_SRD_CACHE: dict | None = None


def _format_modifier(value: int) -> str:
    value = int(value or 0)
    return f"+{value}" if value >= 0 else str(value)


def load_skills_srd_db(bundle_dir: str, app_dir: str) -> dict:
    global _SKILLS_SRD_CACHE
    if _SKILLS_SRD_CACHE is not None:
        return _SKILLS_SRD_CACHE
    candidates = [
        os.path.join(app_dir, "skills_srd.json"),
        os.path.join(bundle_dir, "skills_srd.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    _SKILLS_SRD_CACHE = json.load(handle)
                    return _SKILLS_SRD_CACHE
            except (OSError, json.JSONDecodeError):
                pass
    _SKILLS_SRD_CACHE = {}
    return _SKILLS_SRD_CACHE


def lookup_skill_srd(skill_base_name: str, db: dict) -> dict | None:
    if not db:
        return None
    if skill_base_name in db:
        return db[skill_base_name]
    lowered = skill_base_name.lower()
    for key, record in db.items():
        if str(key).lower() == lowered:
            return record
    return None


class SkillDetailPopup:
    """Show SRD skill text, bonus breakdown, d20 roll, and TaleSpire copy."""

    def __init__(self, sheet, skill_key: str):
        self.sheet = sheet
        self.skill_key = str(skill_key or "").strip()
        self.popup = ctk.CTkToplevel(sheet.root)
        self.popup.title(self._display_name())
        self.popup.grab_set()
        sheet._center_popup_on_root(self.popup, POPUP_WIDTH, POPUP_HEIGHT)

        self._d20_image = self._load_d20_icon()
        self._build_ui()

    def _display_name(self) -> str:
        if hasattr(self.sheet, "_resolved_skill_label"):
            return self.sheet._resolved_skill_label(self.skill_key)
        return self.skill_key

    def _skill_base_name(self) -> str:
        if hasattr(self.sheet, "_skill_base_name"):
            return self.sheet._skill_base_name(self.skill_key)
        return self.skill_key

    def _skills_srd_db(self) -> dict:
        return load_skills_srd_db(self._bundle_dir(), self._app_dir())

    def _bundle_dir(self) -> str:
        if hasattr(self.sheet, "_json_path"):
            return os.path.dirname(self.sheet._json_path("skills_srd.json"))
        return os.path.dirname(os.path.abspath(__file__))

    def _app_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return self._bundle_dir()

    def _primary_color(self) -> str:
        return getattr(self.sheet, "primary_button_color", THEME_ORANGE)

    def _secondary_color(self) -> str:
        return getattr(self.sheet, "secondary_button_color", THEME_TEAL)

    def _load_d20_icon(self, size: int = 34):
        cache = getattr(self.sheet, "_skill_d20_icon_cache", None)
        color = self._primary_color()
        cache_key = (size, color)
        if isinstance(cache, dict) and cache_key in cache:
            return cache[cache_key]

        for folder in (self._app_dir(), self._bundle_dir()):
            for name in ("d20icon.png", "d20_icon.png", "d20.png", "skill_d20.png"):
                path = os.path.join(folder, name)
                if os.path.isfile(path) and HAS_PIL:
                    try:
                        image = Image.open(path).convert("RGBA")
                        image = image.resize((size, size), Image.Resampling.LANCZOS)
                        photo = ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
                        if not isinstance(cache, dict):
                            cache = {}
                            self.sheet._skill_d20_icon_cache = cache
                        cache[cache_key] = photo
                        return photo
                    except Exception:
                        pass

        if HAS_PIL:
            image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            hex_color = str(color).lstrip("#")
            if len(hex_color) == 6:
                fill = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
            else:
                fill = (199, 118, 38)
            margin = 2
            draw.rounded_rectangle(
                (margin, margin, size - margin, size - margin),
                radius=6,
                fill=fill + (255,),
                outline=(255, 255, 255, 220),
                width=2,
            )
            text = "20"
            try:
                font = ImageFont.truetype("arial.ttf", max(10, size // 3))
            except Exception:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text(((size - tw) / 2, (size - th) / 2 - 1), text, fill=(255, 255, 255, 255), font=font)
            photo = ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
            if not isinstance(cache, dict):
                cache = {}
                self.sheet._skill_d20_icon_cache = cache
            cache[cache_key] = photo
            return photo
        return None

    def _build_ui(self):
        outer = ctk.CTkFrame(self.popup, fg_color=THEME_DARK_BG)
        outer.pack(fill="both", expand=True)

        self._build_banner(outer)

        body = ctk.CTkScrollableFrame(outer, fg_color=THEME_DARK_BG)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self._render_srd_content(body)

        footer = ctk.CTkFrame(outer, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            footer, text="Close", width=90, fg_color="#555555", command=self.popup.destroy,
        ).pack(side="right")

    def _build_banner(self, parent):
        banner = ctk.CTkFrame(parent, fg_color=THEME_PANEL, height=BANNER_HEIGHT, corner_radius=8)
        banner.pack(fill="x", padx=14, pady=(14, 8))
        banner.pack_propagate(False)

        left = ctk.CTkFrame(banner, fg_color="transparent")
        left.pack(side="left", fill="y", padx=(10, 6), pady=6)

        display = self._display_name()
        total_text, auto_fail = self._total_display()
        ctk.CTkLabel(
            left,
            text=f"{display}  {total_text}",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        breakdown_text = self._breakdown_text(auto_fail=auto_fail)
        ctk.CTkLabel(
            left,
            text=breakdown_text,
            font=ctk.CTkFont(size=11),
            text_color=THEME_MUTED,
            anchor="w",
        ).pack(anchor="w")

        actions = ctk.CTkFrame(banner, fg_color="transparent")
        actions.pack(side="right", padx=8, pady=6)

        if self._d20_image is not None:
            roll_btn = ctk.CTkButton(
                actions,
                text="",
                image=self._d20_image,
                width=38,
                height=38,
                fg_color="#333333",
                hover_color="#444444",
                command=self._roll_skill,
            )
        else:
            roll_btn = ctk.CTkButton(
                actions,
                text="d20",
                width=38,
                height=38,
                fg_color=self._primary_color(),
                command=self._roll_skill,
            )
        roll_btn.pack(side="left", padx=(0, 6))
        if hasattr(self.sheet, "_bind_hover_tooltip"):
            self.sheet._bind_hover_tooltip(roll_btn, "Roll d20 + skill modifier")

        ctk.CTkButton(
            actions,
            text="Copy",
            width=64,
            height=32,
            fg_color=self._secondary_color(),
            hover_color=getattr(self.sheet, "secondary_hover_color", "#1f7f75"),
            command=self._copy_talespire,
        ).pack(side="left")
        if hasattr(self.sheet, "_bind_hover_tooltip"):
            self.sheet._bind_hover_tooltip(actions.winfo_children()[-1], "Copy TaleSpire roll code")

    def _total_display(self) -> tuple[str, bool]:
        if hasattr(self.sheet, "_skill_auto_fails_from_afflictions"):
            if self.sheet._skill_auto_fails_from_afflictions(self.skill_key):
                return "Auto Fail", True
        if hasattr(self.sheet, "_get_skill_total_modifier"):
            total = int(self.sheet._get_skill_total_modifier(self.skill_key) or 0)
            return _format_modifier(total), False
        return "+0", False

    def _breakdown_text(self, *, auto_fail: bool) -> str:
        if auto_fail:
            return "Afflicted — skill checks automatically fail."
        if hasattr(self.sheet, "_get_skill_bonus_breakdown"):
            parts = self.sheet._get_skill_bonus_breakdown(self.skill_key)
            if not parts:
                return "No modifiers"
            return "  ·  ".join(f"{label} {_format_modifier(value)}" for label, value in parts)
        return ""

    def _build_roll_text(self):
        if hasattr(self.sheet, "_build_talespire_skill_roll"):
            return self.sheet._build_talespire_skill_roll(self.skill_key)
        return None

    def _roll_skill(self):
        roll = self._build_roll_text()
        if not roll:
            return
        if hasattr(self.sheet, "_execute_clickable_roll"):
            self.sheet._execute_clickable_roll(roll, show_copied_toast=True)
            return
        if hasattr(self.sheet, "_begin_local_dice_roll"):
            self.sheet._begin_local_dice_roll(roll)

    def _copy_talespire(self):
        roll = self._build_roll_text()
        if not roll:
            return
        if hasattr(self.sheet, "_queue_talespire_roll"):
            self.sheet._queue_talespire_roll(roll, show_copied_toast=True)

    def _render_srd_content(self, parent):
        db = self._skills_srd_db()
        record = lookup_skill_srd(self._skill_base_name(), db)
        if not record:
            ctk.CTkLabel(
                parent,
                text="SRD details are not available for this skill.",
                text_color=THEME_MUTED,
                wraplength=660,
                justify="left",
            ).pack(anchor="w", pady=8)
            url = f"https://www.d20srd.org/indexes/skills.htm"
            ctk.CTkLabel(
                parent,
                text=url,
                text_color=self._secondary_color(),
                cursor="hand2",
            ).pack(anchor="w")
            return

        title = str(record.get("title") or self._display_name()).strip()
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 8))

        url = str(record.get("srd_url") or "").strip()
        if url:
            link = ctk.CTkLabel(
                parent,
                text=url,
                font=ctk.CTkFont(size=11),
                text_color="#6fa8ff",
                cursor="hand2",
                anchor="w",
            )
            link.pack(anchor="w", pady=(0, 10))
            link.bind("<Button-1>", lambda _e: self._open_url(url))

        for section in record.get("sections") or []:
            section_title = str(section.get("title") or "").strip()
            if section_title:
                ctk.CTkLabel(
                    parent,
                    text=section_title,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=self._primary_color(),
                    anchor="w",
                ).pack(anchor="w", pady=(10, 4))

            for block in section.get("blocks") or []:
                if block.get("type") == "paragraph":
                    text = str(block.get("text") or "").strip()
                    if not text:
                        continue
                    ctk.CTkLabel(
                        parent,
                        text=text,
                        wraplength=660,
                        justify="left",
                        anchor="nw",
                    ).pack(anchor="w", pady=(0, 6))
                elif block.get("type") == "table":
                    self._render_table(parent, block.get("rows") or [])

    def _render_table(self, parent, rows: list):
        if not rows:
            return
        frame = ctk.CTkFrame(parent, fg_color=THEME_PANEL, corner_radius=6, border_width=1, border_color=THEME_BORDER)
        frame.pack(fill="x", pady=(0, 8))
        for row_index, row in enumerate(rows):
            row_frame = ctk.CTkFrame(
                frame,
                fg_color="#2f2f2f" if row_index % 2 == 0 else "#292929",
                corner_radius=0,
            )
            row_frame.pack(fill="x")
            for col_index, cell in enumerate(row):
                weight = 1 if col_index == 0 else 0
                width = 0 if col_index == 0 else 120
                font = ctk.CTkFont(weight="bold") if row_index == 0 else ctk.CTkFont(size=12)
                ctk.CTkLabel(
                    row_frame,
                    text=str(cell or ""),
                    font=font,
                    anchor="w",
                    wraplength=420 if col_index == 0 else 220,
                    justify="left",
                    width=width,
                ).grid(row=0, column=col_index, sticky="ew", padx=8, pady=4)
            columns = max(len(row), 1)
            for col in range(columns):
                row_frame.grid_columnconfigure(col, weight=1 if col == 0 else 0)

    def _open_url(self, url: str):
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:
            pass


def open_skill_detail_popup(sheet, skill_key: str):
    SkillDetailPopup(sheet, skill_key)