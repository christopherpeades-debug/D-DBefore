"""Floating modeless campaign chat window for D&D Beside and D&D Behind."""

from __future__ import annotations

import re
import tkinter as tk

import customtkinter as ctk

try:
    from dice_roller import parse_dice_expression
except ImportError:
    parse_dice_expression = None

try:
    from campaign_chat_sync import format_chat_message_parts, is_whisper_message
except ImportError:
    format_chat_message_parts = None
    is_whisper_message = None

try:
    from roll_log_sync import format_sidebar_roll_log_parts
except ImportError:
    format_sidebar_roll_log_parts = None

DICE_BUTTONS = (
    ("d4", 4),
    ("d6", 6),
    ("d8", 8),
    ("d10", 10),
    ("d12", 12),
    ("d20", 20),
    ("d%", 100),
)


class CampaignChatWindow:
    WIDTH = 375
    HEIGHT = 700

    def __init__(self, host):
        self.host = host
        self.popup = None
        self._feed_text = None
        self._entry = None
        self._hide_sidebar_on_open = False
        self._drag_offset = None

    def is_open(self):
        popup = self.popup
        if popup is None:
            return False
        try:
            return popup.winfo_exists()
        except tk.TclError:
            return False

    def open(self, *, hide_sidebar=False):
        if self.is_open():
            try:
                self.popup.lift()
            except tk.TclError:
                pass
            return
        self._hide_sidebar_on_open = bool(hide_sidebar)
        if hide_sidebar and hasattr(self.host, "_hide_sidebar_roll_log"):
            self.host._hide_sidebar_roll_log()
        self._build_popup()
        self._make_modeless()
        self._refresh_feed()
        set_live = getattr(self.host, "_set_campaign_chat_live_mode", None)
        if callable(set_live):
            set_live(True)

    def close(self):
        popup = self.popup
        self.popup = None
        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except tk.TclError:
                pass
        if self._hide_sidebar_on_open:
            if hasattr(self.host, "_show_sidebar_roll_log"):
                self.host._show_sidebar_roll_log()
            refresh = getattr(self.host, "_refresh_sidebar_roll_log", None)
            if callable(refresh):
                refresh()
        self._hide_sidebar_on_open = False
        set_live = getattr(self.host, "_set_campaign_chat_live_mode", None)
        if callable(set_live):
            set_live(False)

    def refresh_feed(self):
        self._refresh_feed()

    def _make_modeless(self):
        """Non-modal: clicks and keyboard work in the chat and main app at the same time."""
        if not self.is_open():
            return
        popup = self.popup
        root = getattr(self.host, "root", None)
        try:
            popup.grab_release()
        except tk.TclError:
            pass
        try:
            if root is not None:
                popup.transient(root)
        except tk.TclError:
            pass
        try:
            popup.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _accent_color(self):
        return getattr(self.host, "primary_button_color", "#c77626")

    def _secondary_color(self):
        return getattr(self.host, "secondary_button_color", "#28a99e")

    def _font_family(self):
        fn = getattr(self.host, "_markdown_font_family", None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
        return "Segoe UI"

    def _build_popup(self):
        root = getattr(self.host, "root", None)
        if root is None:
            return
        accent = self._accent_color()

        popup = ctk.CTkToplevel(root)
        popup.title("Campaign Chat")
        popup.configure(fg_color="#141414")
        popup.protocol("WM_DELETE_WINDOW", self.close)

        width, height = self.WIDTH, self.HEIGHT
        center = getattr(self.host, "_center_popup_on_root", None)
        if callable(center):
            popup.geometry(f"{width}x{height}")
            center(popup, width, height)
        else:
            popup.geometry(f"{width}x{height}")

        title = ctk.CTkFrame(popup, fg_color="#1e1e1e", height=34, corner_radius=0)
        title.pack(fill="x")
        title.pack_propagate(False)
        ctk.CTkLabel(
            title,
            text="Campaign Chat",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=accent,
        ).pack(side="left", padx=10, pady=6)
        ctk.CTkLabel(
            title,
            text="Modeless — use chat and sheet together",
            font=ctk.CTkFont(size=10),
            text_color="#777777",
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            title, text="✕", width=28, height=24,
            fg_color="#555555", hover_color="#777777",
            command=self.close,
        ).pack(side="right", padx=8, pady=4)

        for widget in title.winfo_children():
            widget.bind("<ButtonPress-1>", self._start_drag, add="+")
            widget.bind("<B1-Motion>", self._do_drag, add="+")
        title.bind("<ButtonPress-1>", self._start_drag)
        title.bind("<B1-Motion>", self._do_drag)

        body = ctk.CTkFrame(popup, fg_color="#141414")
        body.pack(fill="both", expand=True)

        self._feed_text = ctk.CTkTextbox(
            body,
            fg_color="#141414",
            text_color="#ffffff",
            font=ctk.CTkFont(size=11),
            wrap="word",
            activate_scrollbars=True,
        )
        self._feed_text.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self._feed_text.configure(state="disabled")

        dice_row = ctk.CTkFrame(body, fg_color="transparent")
        dice_row.pack(fill="x", padx=8, pady=4)
        for label, sides in DICE_BUTTONS:
            ctk.CTkButton(
                dice_row,
                text=label,
                width=44,
                height=28,
                fg_color="#333333",
                hover_color=accent,
                command=lambda s=sides, lb=label: self._roll_die(s, lb),
            ).pack(side="left", padx=2)

        input_row = ctk.CTkFrame(body, fg_color="transparent")
        input_row.pack(fill="x", padx=8, pady=(4, 10))
        self._entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Message, /dm text, or /roll:1d20+5",
            fg_color="#1e1e1e",
            border_color="#333333",
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._entry.bind("<Return>", lambda _event: self._send_message())
        ctk.CTkButton(
            input_row,
            text="Send",
            width=64,
            fg_color=accent,
            command=self._send_message,
        ).pack(side="right")

        self.popup = popup
        self._configure_feed_tags()

    def _start_drag(self, event):
        if not self.is_open():
            return
        self._drag_offset = (
            event.x_root - self.popup.winfo_x(),
            event.y_root - self.popup.winfo_y(),
        )

    def _do_drag(self, event):
        if not self.is_open() or not self._drag_offset:
            return
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.popup.geometry(f"+{x}+{y}")

    def _feed_inner_text(self):
        if self._feed_text is None:
            return None
        return getattr(self._feed_text, "_textbox", self._feed_text)

    def _configure_feed_tags(self):
        tw = self._feed_inner_text()
        if tw is None:
            return
        accent = self._accent_color()
        secondary = self._secondary_color()
        family = self._font_family()
        tw.tag_configure("feed_bold", foreground=accent, font=(family, 11, "bold"))
        tw.tag_configure("feed_body", foreground="#ffffff", font=(family, 11, "normal"))
        tw.tag_configure("feed_muted", foreground="#888888", font=(family, 11, "normal"))
        tw.tag_configure("feed_whisper_bold", foreground=secondary, font=(family, 11, "bold"))
        tw.tag_configure("feed_whisper_body", foreground=secondary, font=(family, 11, "normal"))

    def _refresh_feed(self):
        if not self.is_open() or self._feed_text is None:
            return
        self._configure_feed_tags()
        box = self._feed_text
        tw = self._feed_inner_text()
        if tw is None:
            return
        box.configure(state="normal")
        tw.delete("1.0", "end")

        merge_fn = getattr(self.host, "get_merged_campaign_feed", None)
        if not callable(merge_fn):
            tw.insert("end", "Chat unavailable.", ("feed_muted",))
        else:
            items, configured = merge_fn(limit=200)
            if not configured:
                tw.insert("end", "Enable cloud sync to use campaign chat.", ("feed_muted",))
            elif not items:
                tw.insert("end", "No messages yet. Say hello or roll dice!", ("feed_muted",))
            else:
                for index, (kind, row) in enumerate(items):
                    if index:
                        tw.insert("end", "\n")
                    self._insert_feed_line(tw, kind, row)

        box.configure(state="disabled")
        try:
            tw.see("end")
        except tk.TclError:
            pass

    def _is_whisper_row(self, row):
        if callable(is_whisper_message):
            return is_whisper_message(row)
        return bool(str(row.get("whisper_to_character_id") or "").strip())

    def _insert_feed_line(self, tw, kind, row):
        if kind == "chat":
            whisper = self._is_whisper_row(row)
            bold_tag = "feed_whisper_bold" if whisper else "feed_bold"
            body_tag = "feed_whisper_body" if whisper else "feed_body"
            if format_chat_message_parts:
                bold, body = format_chat_message_parts(row)
            else:
                bold = str(row.get("character_name") or "Unknown")
                body = f": {str(row.get('message_text') or '').strip()}"
            tw.insert("end", bold, (bold_tag,))
            tw.insert("end", body, (body_tag,))
            return
        if format_sidebar_roll_log_parts:
            bold, body = format_sidebar_roll_log_parts(row)
        else:
            bold = str(row.get("roll_label") or "Roll")
            body = ""
        tw.insert("end", bold, ("feed_bold",))
        if body:
            tw.insert("end", body, ("feed_body",))

    def _parse_roll_command(self, text):
        match = re.match(r"^/roll:\s*(.+)$", str(text or "").strip(), re.IGNORECASE)
        if not match:
            return None
        expr = re.sub(r"\s+", "", match.group(1).strip().lower())
        if not expr:
            return None
        parse_fn = getattr(self.host, "_parse_dice_expression", None) or parse_dice_expression
        if not parse_fn or not parse_fn(expr):
            return ""
        return expr

    def _send_roll_command(self, expr):
        ensure = getattr(self.host, "_ensure_dice_roller", None)
        if not callable(ensure):
            return
        roller = ensure()
        if roller is None:
            return
        if self._entry is not None:
            self._entry.delete(0, "end")
        try:
            roller.roll_plain_expression(expr, label=expr, publish_roll=True)
        except Exception:
            pass

    def _send_message(self):
        text = ""
        if self._entry is not None:
            text = str(self._entry.get() or "").strip()
        if not text:
            return
        roll_expr = self._parse_roll_command(text)
        if roll_expr is not None:
            if roll_expr == "":
                publish = getattr(self.host, "_publish_campaign_chat_message", None)
                if callable(publish):
                    publish("Invalid roll — use /roll:1d20+5")
                if self._entry is not None:
                    self._entry.delete(0, "end")
                return
            self._send_roll_command(roll_expr)
            return
        publish = getattr(self.host, "_publish_campaign_chat_message", None)
        if callable(publish):
            publish(text)
        if self._entry is not None:
            self._entry.delete(0, "end")

    def _roll_die(self, sides, label):
        ensure = getattr(self.host, "_ensure_dice_roller", None)
        if not callable(ensure):
            return
        roller = ensure()
        if roller is None:
            return
        expr = f"1d{sides}"
        try:
            roller.roll_plain_expression(expr, label=label)
        except Exception:
            pass