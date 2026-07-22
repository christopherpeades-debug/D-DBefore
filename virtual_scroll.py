"""
Skills list: one Canvas, one create_window per row, explicit scrollregion.

Nested canvases (skills inside the page content canvas) break bbox-based
scrollregion on Windows — scroll stops mid-list. We never use bbox for height.
Content height is always: len(items) * row_height.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional, Any, Tuple

RowFactory = Callable[[tk.Frame, int, Any], dict]
RowBinder = Callable[[dict, int, Any], None]

SKILLS_SCROLLBAR_BUTTON_COLOR = "#555555"
SKILLS_SCROLLBAR_BUTTON_HOVER_COLOR = "#777777"


def _make_v_scrollbar(parent, command, canvas_bg: str, width: int = 16):
    try:
        from tkinter import ttk
        style = ttk.Style(parent)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Skills.Vertical.TScrollbar",
            background=SKILLS_SCROLLBAR_BUTTON_COLOR,
            troughcolor=canvas_bg,
            arrowcolor="#cccccc",
        )
        return ttk.Scrollbar(
            parent,
            orient="vertical",
            command=command,
            style="Skills.Vertical.TScrollbar",
        )
    except Exception:
        return tk.Scrollbar(
            parent,
            orient="vertical",
            command=command,
            bg=SKILLS_SCROLLBAR_BUTTON_COLOR,
            troughcolor=canvas_bg,
            activebackground=SKILLS_SCROLLBAR_BUTTON_HOVER_COLOR,
            width=max(12, int(width)),
        )


class TkScrollList(tk.Frame):
    """All skill rows as canvas windows; scrollregion = n * row_height (always)."""

    def __init__(
        self,
        parent,
        *,
        row_height: int = 28,
        canvas_bg: str = "#1a1a1a",
        scrollbar_width: int = 16,
        height: int = 200,
        **kwargs,
    ):
        kwargs.pop("fg_color", None)
        kwargs.pop("corner_radius", None)
        kwargs.pop("visible_rows", None)
        super().__init__(parent, bg=canvas_bg, highlightthickness=0, bd=0, **kwargs)
        self.row_height = max(20, int(row_height))
        self._canvas_bg = canvas_bg
        self._viewport_height = max(120, int(height or 200))
        self._items: List[Any] = []
        self._row_slots: List[dict] = []
        self._window_ids: List[int] = []
        self._row_factory: Optional[RowFactory] = None
        self._row_binder: Optional[RowBinder] = None
        self._wheel_bound_top = None
        self._scroll_region_job = None

        self.configure(height=self._viewport_height)
        try:
            self.pack_propagate(False)
            self.grid_propagate(False)
        except Exception:
            pass

        self._canvas = tk.Canvas(
            self,
            bg=canvas_bg,
            highlightthickness=0,
            bd=0,
            height=self._viewport_height,
            yscrollincrement=max(1, self.row_height),
        )
        self._v_scroll = _make_v_scrollbar(
            self, self._on_scrollbar, canvas_bg, scrollbar_width,
        )
        self._v_scroll.pack(side="right", fill="y")
        self._canvas.configure(yscrollcommand=self._v_scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True)

        self._canvas.bind("<Configure>", self._on_canvas_configure, add="+")
        self.bind("<Configure>", self._on_self_configure, add="+")
        self.bind("<Enter>", self._on_enter_bind_wheel, add="+")
        self._canvas.bind("<Enter>", self._on_enter_bind_wheel, add="+")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind(seq, self._on_mousewheel, add="+")
            self._canvas.bind(seq, self._on_mousewheel, add="+")

    # ----- public API -----

    def configure_list(
        self,
        items: List[Any],
        *,
        row_factory: RowFactory,
        row_binder: RowBinder,
        width: Optional[int] = None,
    ) -> None:
        self._row_factory = row_factory
        self._row_binder = row_binder
        _ = width
        self.set_items(items, preserve_scroll=False)

    def set_content_width(self, width: int) -> None:
        _ = width
        self._relayout_row_widths()

    def set_viewport_height(self, height: int) -> None:
        height = max(120, int(height))
        self._viewport_height = height
        try:
            self.configure(height=height)
            self.pack_propagate(False)
            self.grid_propagate(False)
            self._canvas.configure(height=height)
        except Exception:
            pass
        self._apply_scrollregion()

    def set_items(self, items: List[Any], *, preserve_scroll: bool = False) -> None:
        y_frac = 0.0
        if preserve_scroll:
            try:
                y_frac = float(self._canvas.yview()[0])
            except Exception:
                y_frac = 0.0
        self._items = list(items)
        self._rebuild_rows()
        self._apply_scrollregion()
        if preserve_scroll:
            try:
                self._canvas.yview_moveto(max(0.0, min(1.0, y_frac)))
            except Exception:
                pass

    def scroll_to_index(self, index: int) -> None:
        n = len(self._items)
        if n <= 0:
            return
        index = max(0, min(int(index), n - 1))
        total = self._content_height()
        view = max(1, int(self._canvas.winfo_height() or self._viewport_height))
        max_top = max(0, total - view)
        top = min(index * self.row_height, max_top)
        frac = (top / max_top) if max_top else 0.0
        self._canvas.yview_moveto(frac)

    def scroll_to_end(self) -> None:
        self._apply_scrollregion()
        self._canvas.yview_moveto(1.0)

    def item_count(self) -> int:
        return len(self._items)

    def winfo_children_list(self):
        rows = []
        for slot in self._row_slots:
            row = slot.get("row")
            if row is not None:
                try:
                    if row.winfo_exists():
                        rows.append(row)
                except tk.TclError:
                    pass
        return rows

    def debug_scroll_state(self) -> dict:
        try:
            return {
                "items": len(self._items),
                "slots": len(self._row_slots),
                "windows": len(self._window_ids),
                "row_height": self.row_height,
                "content_h": self._content_height(),
                "viewport_h": int(self._canvas.winfo_height() or self._viewport_height),
                "scrollregion": self._canvas.cget("scrollregion"),
                "yview": self._canvas.yview(),
                "can_scroll": self._content_height()
                > int(self._canvas.winfo_height() or self._viewport_height) + 2,
            }
        except Exception as exc:
            return {"error": str(exc)}

    # ----- internals -----

    def _content_height(self) -> int:
        n = max(len(self._items), len(self._row_slots), len(self._window_ids))
        return max(1, n * max(1, self.row_height))

    def _canvas_width(self) -> int:
        try:
            w = int(self._canvas.winfo_width() or 0)
        except Exception:
            w = 0
        return max(100, w)

    def _rebuild_rows(self) -> None:
        if self._row_factory is None or self._row_binder is None:
            return

        # Destroy previous row windows
        for wid in self._window_ids:
            try:
                self._canvas.delete(wid)
            except Exception:
                pass
        for slot in self._row_slots:
            frame = slot.get("_slot_frame") or slot.get("row")
            if frame is not None:
                try:
                    frame.destroy()
                except Exception:
                    pass
        self._window_ids = []
        self._row_slots = []

        cw = self._canvas_width()
        rh = self.row_height

        for index, item in enumerate(self._items):
            y = index * rh
            try:
                slot_frame = tk.Frame(
                    self._canvas,
                    bg=self._canvas_bg,
                    highlightthickness=0,
                    bd=0,
                    width=cw,
                    height=rh,
                )
                try:
                    slot_frame.pack_propagate(False)
                    slot_frame.grid_propagate(False)
                except Exception:
                    pass

                slot = self._row_factory(slot_frame, index, item)
                slot["row"] = slot_frame
                slot["_slot_frame"] = slot_frame
                self._row_binder(slot, index, item)

                # One canvas window per row — y position is authoritative for scroll height.
                win_id = self._canvas.create_window(
                    0,
                    y,
                    window=slot_frame,
                    anchor="nw",
                    width=cw,
                    height=rh,
                )
                self._window_ids.append(win_id)
                self._row_slots.append(slot)

                for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    try:
                        slot_frame.bind(seq, self._on_mousewheel, add="+")
                    except Exception:
                        pass
                self._bind_wheel_deep(slot_frame)
            except Exception as exc:
                # Never abort mid-list — a single bad row was cutting skills at Knowledge.
                print(f"Skill row {index} build failed: {exc}")
                continue

        if len(self._row_slots) != len(self._items):
            print(
                f"WARNING: skills built {len(self._row_slots)}/{len(self._items)} rows"
            )
        self._apply_scrollregion()

    def _bind_wheel_deep(self, widget) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                widget.bind(seq, self._on_mousewheel, add="+")
            except Exception:
                pass
        try:
            for child in widget.winfo_children():
                self._bind_wheel_deep(child)
        except Exception:
            pass

    def _relayout_row_widths(self) -> None:
        cw = self._canvas_width()
        rh = self.row_height
        for i, (wid, slot) in enumerate(zip(self._window_ids, self._row_slots)):
            try:
                self._canvas.coords(wid, 0, i * rh)
                self._canvas.itemconfigure(wid, width=cw, height=rh)
                frame = slot.get("_slot_frame")
                if frame is not None:
                    frame.configure(width=cw, height=rh)
            except Exception:
                pass
        self._apply_scrollregion()

    def _apply_scrollregion(self) -> None:
        """scrollregion height = n * row_height — never bbox()."""
        try:
            cw = self._canvas_width()
            ch = self._content_height()
            self._canvas.configure(scrollregion=(0, 0, cw, ch))
            # Keep each row window sized/positioned.
            rh = self.row_height
            for i, wid in enumerate(self._window_ids):
                try:
                    self._canvas.coords(wid, 0, i * rh)
                    self._canvas.itemconfigure(wid, width=cw, height=rh)
                except Exception:
                    pass
        except Exception:
            pass

    def _schedule_apply_scrollregion(self) -> None:
        if self._scroll_region_job is not None:
            try:
                self.after_cancel(self._scroll_region_job)
            except Exception:
                pass
        try:
            self._scroll_region_job = self.after_idle(self._run_apply_scrollregion)
        except Exception:
            self._apply_scrollregion()

    def _run_apply_scrollregion(self) -> None:
        self._scroll_region_job = None
        self._apply_scrollregion()

    def _on_self_configure(self, event=None) -> None:
        try:
            h = int(event.height) if event is not None else int(self.winfo_height() or 0)
        except Exception:
            return
        if h < 80:
            return
        if h + 4 < self._viewport_height:
            self._viewport_height = h
            try:
                self._canvas.configure(height=h)
            except Exception:
                pass
        self._schedule_apply_scrollregion()

    def _on_canvas_configure(self, event=None) -> None:
        self._schedule_apply_scrollregion()

    def _on_scrollbar(self, *args) -> None:
        """Scrollbar → canvas yview (moveto/scroll)."""
        try:
            self._canvas.yview(*args)
        except Exception:
            pass

    def _on_enter_bind_wheel(self, _event=None) -> None:
        try:
            top = self.winfo_toplevel()
        except Exception:
            return
        if self._wheel_bound_top is top:
            return
        try:
            # bind (not bind_all) first; also bind_all so wheel works over child entries
            top.bind_all("<MouseWheel>", self._on_mousewheel_global, add="+")
            top.bind_all("<Button-4>", self._on_mousewheel_global, add="+")
            top.bind_all("<Button-5>", self._on_mousewheel_global, add="+")
            self._wheel_bound_top = top
        except Exception:
            self._wheel_bound_top = None

    def _pointer_over_list(self) -> bool:
        try:
            px, py = self.winfo_pointerxy()
            widget = self.winfo_containing(px, py)
            while widget is not None:
                if widget is self or widget is self._canvas:
                    return True
                # Any skill row frame is a child of this canvas
                try:
                    if str(widget).startswith(str(self._canvas)):
                        return True
                except Exception:
                    pass
                try:
                    widget = widget.master
                except Exception:
                    break
            # Also: if pointer is over one of our row frames
            for slot in self._row_slots:
                frame = slot.get("_slot_frame")
                if frame is None:
                    continue
                try:
                    w = self.winfo_containing(px, py)
                    cur = w
                    while cur is not None:
                        if cur is frame or cur is self or cur is self._canvas:
                            return True
                        cur = cur.master
                except Exception:
                    break
        except Exception:
            return False
        return False

    def _on_mousewheel_global(self, event):
        if not self._pointer_over_list():
            return
        return self._on_mousewheel(event)

    def _on_mousewheel(self, event) -> str:
        """Pixel-based scroll so the full list (Appraise→Use Rope) is always reachable."""
        # Re-assert full scrollregion every wheel event (guards against nested-canvas reset).
        self._apply_scrollregion()
        content_h = self._content_height()
        view_h = max(1, int(self._canvas.winfo_height() or self._viewport_height))
        if content_h <= view_h:
            return "break"
        delta = 0
        if getattr(event, "delta", 0):
            delta = int(-1 * (event.delta / 120))
            if delta == 0 and event.delta:
                delta = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        if delta:
            try:
                # Move by whole rows in fraction space (reliable vs yview_scroll units).
                max_top = max(1, content_h - view_h)
                step = (3 * self.row_height) / float(max_top)
                first = float(self._canvas.yview()[0])
                self._canvas.yview_moveto(max(0.0, min(1.0, first + delta * step)))
            except Exception:
                try:
                    self._canvas.yview_scroll(delta * 3, "units")
                except Exception:
                    pass
        return "break"


class VirtualList(TkScrollList):
    """Alias used by the character sheet."""

    def __init__(self, parent, *, visible_rows: int = 16, **kwargs):
        kwargs.pop("visible_rows", None)
        super().__init__(parent, **kwargs)
        self.visible_rows = max(4, int(visible_rows))
