"""
Lightweight root window helpers for D&D Beside.

Uses tk.Tk (not ctk.CTk) so Windows title-bar drags do not trigger CTk's
root-level <Configure> scaling bookkeeping on every pixel.

WndProc subclassing was removed — it caused hard crashes when restoring from
maximized.  Sizemove detection now lives in dnd_character_sheet.py via
debounced <Configure> handlers only.
"""
from __future__ import annotations

import sys
import ctypes

import tkinter as tk
import customtkinter as ctk

ROOT_BG_DARK = "#1a1a1a"
SW_MAXIMIZE = 3
_CTK_SCALING_TRACKER_PATCHED = False


def _ensure_tk_root_ctk_compat() -> None:
    """
    CustomTkinter's ScalingTracker calls block/unblock_update_dimensions_event on
    every registered window root. Those methods exist on CTk, not plain tk.Tk.
    Without them, DPI checks throw and can leave alpha=0.15 (window looks frozen).
    """
    if getattr(tk.Tk, "_dnd_beside_ctk_compat", False):
        return

    def block_update_dimensions_event(self):
        self._block_update_dimensions_event = True

    def unblock_update_dimensions_event(self):
        self._block_update_dimensions_event = False

    tk.Tk.block_update_dimensions_event = block_update_dimensions_event
    tk.Tk.unblock_update_dimensions_event = unblock_update_dimensions_event
    tk.Tk._dnd_beside_ctk_compat = True


def _patch_scaling_tracker_for_tk_root() -> None:
    """Guard CTk DPI polling so tk.Tk roots never crash or stick at alpha=0.15."""
    global _CTK_SCALING_TRACKER_PATCHED
    if _CTK_SCALING_TRACKER_PATCHED:
        return
    try:
        from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker
    except Exception:
        return

    if getattr(ScalingTracker, "_dnd_beside_tk_root_patch", False):
        _CTK_SCALING_TRACKER_PATCHED = True
        return

    @classmethod
    def _patched_check_dpi_scaling(cls):
        new_scaling_detected = False
        for window in list(cls.window_widgets_dict.keys()):
            try:
                if not window.winfo_exists() or str(window.state()) == "iconic":
                    continue
                current_dpi_scaling_value = cls.get_window_dpi_scaling(window)
                if current_dpi_scaling_value == cls.window_dpi_scaling_dict.get(window):
                    continue
                cls.window_dpi_scaling_dict[window] = current_dpi_scaling_value
                alpha_changed = False
                try:
                    if sys.platform.startswith("win"):
                        window.attributes("-alpha", 0.15)
                        alpha_changed = True
                    block = getattr(window, "block_update_dimensions_event", None)
                    if callable(block):
                        block()
                    cls.update_scaling_callbacks_for_window(window)
                    unblock = getattr(window, "unblock_update_dimensions_event", None)
                    if callable(unblock):
                        unblock()
                    new_scaling_detected = True
                finally:
                    if alpha_changed:
                        try:
                            window.attributes("-alpha", 1.0)
                        except Exception:
                            pass
            except Exception:
                try:
                    if sys.platform.startswith("win") and window.winfo_exists():
                        window.attributes("-alpha", 1.0)
                except Exception:
                    pass

        for app in list(cls.window_widgets_dict.keys()):
            try:
                delay = (
                    cls.loop_pause_after_new_scaling
                    if new_scaling_detected
                    else cls.update_loop_interval
                )
                app.after(delay, cls.check_dpi_scaling)
                return
            except Exception:
                continue
        cls.update_loop_running = False

    ScalingTracker.check_dpi_scaling = _patched_check_dpi_scaling
    ScalingTracker._dnd_beside_tk_root_patch = True
    _CTK_SCALING_TRACKER_PATCHED = True


def apply_windows_dark_titlebar(window, *, dark: bool = True) -> None:
    """Dark title bar on Windows 10/11 (same DWM attribute CTk uses)."""
    if not sys.platform.startswith("win"):
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        value = ctypes.c_int(1 if dark else 0)
        dwmapi = ctypes.windll.dwmapi
        if dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)) != 0:
            dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def create_application_root(*, ui_scale: float = 1.0, min_width: int = 880, min_height: int = 580) -> tk.Tk:
    """
    Application root window.

    Uses tk.Tk (not ctk.CTk) so Windows title-bar drags do not trigger CTk's
    root-level <Configure> scaling bookkeeping on every mouse pixel.
    All existing CTk widgets continue to work as children of this root.
    """
    _ensure_tk_root_ctk_compat()
    _patch_scaling_tracker_for_tk_root()

    ctk.set_appearance_mode("dark")
    ctk.set_widget_scaling(ui_scale)
    ctk.set_window_scaling(ui_scale)

    root = tk.Tk()
    root._block_update_dimensions_event = False
    root.configure(bg=ROOT_BG_DARK)
    root.minsize(int(min_width), int(min_height))

    if sys.platform.startswith("win"):
        root.after(200, lambda: apply_windows_dark_titlebar(root, dark=True))

    return root


def maximize_application_window(window) -> bool:
    """Maximize the application toplevel (Windows zoomed / full work area)."""
    try:
        window.update_idletasks()
    except Exception:
        pass
    try:
        if str(window.state()) == "zoomed":
            return True
    except Exception:
        pass
    try:
        if str(window.state()) != "normal":
            window.state("normal")
            window.update_idletasks()
    except Exception:
        pass
    try:
        window.state("zoomed")
        window.update_idletasks()
        if str(window.state()) == "zoomed":
            return True
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:
            hwnd = _resolve_toplevel_hwnd(window)
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
                return True
        except Exception:
            pass
    try:
        sw = int(window.winfo_screenwidth() or 1920)
        sh = int(window.winfo_screenheight() or 1080)
        window.geometry(f"{sw}x{sh}+0+0")
        return True
    except Exception:
        return False


def _resolve_toplevel_hwnd(tk_window) -> int | None:
    try:
        user32 = ctypes.windll.user32
        frame_hwnd = int(tk_window.winfo_id())
        parent = int(user32.GetParent(frame_hwnd))
        return parent or frame_hwnd
    except Exception:
        return None


def set_window_redraw(tk_window, *, enabled: bool) -> None:
    """No-op retained for API compatibility (WM_SETREDRAW caused restore crashes)."""
    return


def install_windows_drag_hooks(app) -> None:
    """No-op — sizemove is handled safely via Tk <Configure> debouncing in the app."""
    return


def reset_window_alpha(window, *, alpha: float = 1.0) -> None:
    """Undo CTk DPI-scaling flicker if a callback failed mid-flight."""
    if not sys.platform.startswith("win"):
        return
    try:
        window.attributes("-alpha", float(alpha))
    except Exception:
        pass