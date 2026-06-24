"""Dark-themed dialog helpers replacing tkinter.messagebox."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Optional

import customtkinter as ctk

THEME_DARK_BG = "#1a1a1a"
THEME_DARK_TRACK = "#2F2F2F"
THEME_TEXT = "#e8e8e8"
THEME_ACCENT = "#c77626"
THEME_ACCENT_HOVER = "#a56b32"
THEME_MUTED_BTN = "#555555"
THEME_CANCEL_BTN = "#444444"
THEME_ERROR = "#c0392b"
THEME_WARNING = "#d68910"
THEME_INFO = "#28a99e"

MIN_DIALOG_WIDTH = 440
MIN_DIALOG_HEIGHT = 170
BTN_WIDTH = 108
BTN_HEIGHT = 36
BTN_PADX = 10
DIALOG_PAD = 24
MESSAGE_WRAP = 380

_ICON_COLORS = {
    "info": THEME_INFO,
    "warning": THEME_WARNING,
    "error": THEME_ERROR,
    "question": THEME_ACCENT,
}

_ctk_toplevel_patched = False
_theme_provider = None


def set_theme_provider(provider):
    """Register a callable returning theme color overrides for message dialogs."""
    global _theme_provider
    _theme_provider = provider


def _active_theme():
    defaults = {
        "bg": THEME_DARK_BG,
        "primary": THEME_ACCENT,
        "primary_hover": THEME_ACCENT_HOVER,
        "secondary": THEME_INFO,
        "secondary_hover": "#1f7f75",
        "question": THEME_ACCENT,
        "info": THEME_INFO,
        "warning": THEME_WARNING,
        "error": THEME_ERROR,
    }
    if _theme_provider is None:
        return defaults
    try:
        custom = _theme_provider()
        if isinstance(custom, dict):
            merged = dict(defaults)
            merged.update(custom)
            return merged
    except Exception:
        pass
    return defaults


def _resolve_parent(parent: Optional[tk.Misc]) -> Optional[tk.Misc]:
    if parent is not None:
        try:
            if parent.winfo_exists():
                return parent
        except (tk.TclError, AttributeError):
            pass
    try:
        root = tk._get_default_root()
        if root is not None:
            return root
    except Exception:
        pass
    return None


def _center_on_parent(win: ctk.CTkToplevel, parent: Optional[tk.Misc], width: int, height: int) -> None:
    win.update_idletasks()
    if parent is not None:
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = max(parent.winfo_width(), 1)
            ph = max(parent.winfo_height(), 1)
            x = px + max(0, (pw - width) // 2)
            y = py + max(0, (ph - height) // 2)
            win.geometry(f"{width}x{height}+{x}+{y}")
            return
        except tk.TclError:
            pass
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


def configure_dark_popup(
    popup: ctk.CTkToplevel,
    *,
    min_width: int = 380,
    min_height: int = 140,
    fg_color: str = THEME_DARK_BG,
) -> ctk.CTkToplevel:
    """Apply dark styling and sensible minimum size to a CTkToplevel."""
    try:
        popup.configure(fg_color=fg_color)
    except Exception:
        pass
    try:
        popup.minsize(min_width, min_height)
    except Exception:
        pass
    return popup


def install_dark_ui() -> None:
    """Patch CTkToplevel so new popups default to dark background."""
    global _ctk_toplevel_patched
    if _ctk_toplevel_patched:
        return
    _ctk_toplevel_patched = True

    _orig_init = ctk.CTkToplevel.__init__

    def _dark_init(self, *args, **kwargs):
        if "fg_color" not in kwargs:
            kwargs["fg_color"] = THEME_DARK_BG
        _orig_init(self, *args, **kwargs)
        try:
            self.configure(fg_color=kwargs.get("fg_color", THEME_DARK_BG))
        except Exception:
            pass

    ctk.CTkToplevel.__init__ = _dark_init  # type: ignore[method-assign]


def _run_dialog(
    title: str,
    message: str,
    icon: str,
    buttons: list[tuple[str, Any, str]],
    *,
    parent: Optional[tk.Misc] = None,
    default: Any = None,
) -> Any:
    parent = _resolve_parent(parent)
    result: list[Any] = [default]
    theme = _active_theme()

    dlg = ctk.CTkToplevel(parent)
    dlg.title(str(title or "Notice"))
    dlg.configure(fg_color=theme["bg"])
    dlg.resizable(False, False)
    if parent is not None:
        try:
            dlg.transient(parent)
        except tk.TclError:
            pass
    dlg.grab_set()

    outer = ctk.CTkFrame(dlg, fg_color=theme["bg"])
    outer.pack(fill="both", expand=True, padx=DIALOG_PAD, pady=DIALOG_PAD)

    accent = {
        "info": theme["info"],
        "warning": THEME_WARNING,
        "error": THEME_ERROR,
        "question": theme["question"],
    }.get(icon, theme["primary"])
    header = ctk.CTkFrame(outer, fg_color="transparent")
    header.pack(fill="x", pady=(0, 12))

    ctk.CTkLabel(
        header,
        text=str(title or "Notice"),
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color=accent,
        anchor="w",
        justify="left",
    ).pack(side="left", fill="x", expand=True)

    ctk.CTkLabel(
        outer,
        text=str(message or ""),
        font=ctk.CTkFont(size=14),
        text_color=THEME_TEXT,
        wraplength=MESSAGE_WRAP,
        justify="left",
        anchor="nw",
    ).pack(fill="x", pady=(0, 18))

    footer = ctk.CTkFrame(outer, fg_color="transparent")
    footer.pack(fill="x")

    def _close(value: Any) -> None:
        result[0] = value
        try:
            dlg.grab_release()
        except tk.TclError:
            pass
        dlg.destroy()

    for idx, (label, value, color) in enumerate(reversed(buttons)):
        if color == THEME_ACCENT:
            btn_color = theme["primary"]
            hover = theme["primary_hover"]
        elif color == THEME_INFO:
            btn_color = theme["secondary"]
            hover = theme["secondary_hover"]
        else:
            btn_color = color
            hover = "#666666"
        btn = ctk.CTkButton(
            footer,
            text=label,
            width=BTN_WIDTH,
            height=BTN_HEIGHT,
            fg_color=btn_color,
            hover_color=hover,
            command=lambda v=value: _close(v),
        )
        side = "right" if idx == 0 else "left"
        padx = (BTN_PADX, 0) if side == "right" else (0, BTN_PADX)
        btn.pack(side=side, padx=padx)

    dlg.update_idletasks()
    width = max(MIN_DIALOG_WIDTH, dlg.winfo_reqwidth() + 16)
    height = max(MIN_DIALOG_HEIGHT, dlg.winfo_reqheight() + 16)
    _center_on_parent(dlg, parent, width, height)
    dlg.minsize(width, height)

    dlg.protocol("WM_DELETE_WINDOW", lambda: _close(default))
    dlg.wait_window()
    return result[0]


def showinfo(title: str = "Info", message: str = "", **kwargs) -> None:
    _run_dialog(title, message, "info", [("OK", None, THEME_ACCENT)], parent=kwargs.get("parent"))


def showwarning(title: str = "Warning", message: str = "", **kwargs) -> None:
    _run_dialog(title, message, "warning", [("OK", None, THEME_WARNING)], parent=kwargs.get("parent"))


def showerror(title: str = "Error", message: str = "", **kwargs) -> None:
    _run_dialog(title, message, "error", [("OK", None, THEME_ERROR)], parent=kwargs.get("parent"))


def askyesno(title: str = "Confirm", message: str = "", **kwargs) -> bool:
    answer = _run_dialog(
        title,
        message,
        "question",
        [("Yes", True, THEME_ACCENT), ("No", False, THEME_MUTED_BTN)],
        parent=kwargs.get("parent"),
        default=False,
    )
    return bool(answer)


def askokcancel(title: str = "Confirm", message: str = "", **kwargs) -> bool:
    answer = _run_dialog(
        title,
        message,
        "question",
        [("OK", True, THEME_ACCENT), ("Cancel", False, THEME_CANCEL_BTN)],
        parent=kwargs.get("parent"),
        default=False,
    )
    return bool(answer)


def askyesnocancel(title: str = "Confirm", message: str = "", **kwargs) -> Optional[bool]:
    return _run_dialog(
        title,
        message,
        "question",
        [
            ("Yes", True, THEME_ACCENT),
            ("No", False, THEME_MUTED_BTN),
            ("Cancel", None, THEME_CANCEL_BTN),
        ],
        parent=kwargs.get("parent"),
        default=None,
    )


def askquestion(title: str = "Question", message: str = "", **kwargs) -> str:
    """Compatibility shim: returns 'yes' or 'no'."""
    return "yes" if askyesno(title, message, **kwargs) else "no"