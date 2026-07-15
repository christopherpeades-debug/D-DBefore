"""
Virtual list for large CTk tables (skills, etc.).

A fixed pool of row widgets is recycled; the scrollbar shifts which items bind.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, List, Optional, Any

import customtkinter as ctk

RowFactory = Callable[[ctk.CTkFrame, int, Any], dict]
RowBinder = Callable[[dict, int, Any], None]

SKILLS_SCROLLBAR_BUTTON_COLOR = "#555555"
SKILLS_SCROLLBAR_BUTTON_HOVER_COLOR = "#777777"


class VirtualList(ctk.CTkFrame):
    """Vertical virtual scroll area with a recycled row pool."""

    ROW_PADY = 2

    def __init__(
        self,
        parent,
        *,
        row_height: int = 34,
        visible_rows: int = 20,
        canvas_bg: str = "#1a1a1a",
        scrollbar_width: int = 16,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.row_height = max(24, int(row_height))
        self.row_stride = self.row_height + self.ROW_PADY * 2
        self.visible_rows = max(6, int(visible_rows))
        self._items: List[Any] = []
        self._pool: List[dict] = []
        self._start_index = 0
        self._row_factory: Optional[RowFactory] = None
        self._row_binder: Optional[RowBinder] = None
        self._viewport_height = 200
        self._scroll_pending = False
        try:
            self.pack_propagate(False)
            self.grid_propagate(False)
        except Exception:
            pass

        self._row_host = ctk.CTkFrame(self, fg_color=canvas_bg, corner_radius=0)
        self._row_host.pack(side="left", fill="both", expand=True)

        self._v_scroll = ctk.CTkScrollbar(
            self,
            orientation="vertical",
            command=self._on_scrollbar,
            width=max(12, int(scrollbar_width)),
            button_color=SKILLS_SCROLLBAR_BUTTON_COLOR,
            button_hover_color=SKILLS_SCROLLBAR_BUTTON_HOVER_COLOR,
        )
        self._v_scroll.pack(side="right", fill="y")

        self.bind("<Destroy>", self._on_destroy)
        for widget in (self, self._row_host):
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(seq, self._on_mousewheel, add="+")

    def configure_list(
        self,
        items: List[Any],
        *,
        row_factory: RowFactory,
        row_binder: RowBinder,
        width: Optional[int] = None,
    ) -> None:
        self._items = list(items)
        self._row_factory = row_factory
        self._row_binder = row_binder
        _ = width
        self._ensure_pool()
        self._start_index = 0
        self._refresh_rows()
        self._sync_scrollbar()

    def set_content_width(self, width: int) -> None:
        _ = width

    def set_viewport_height(self, height: int) -> None:
        height = max(120, int(height))
        if height == self._viewport_height and self.winfo_height() > 1:
            self._sync_scrollbar()
            return
        self._viewport_height = height
        self.configure(height=height)
        try:
            self.pack_propagate(False)
            self.grid_propagate(False)
        except Exception:
            pass
        self._clamp_start_index()
        self._refresh_rows()
        self._sync_scrollbar()

    def set_items(self, items: List[Any], *, preserve_scroll: bool = False) -> None:
        top = self._start_index if preserve_scroll else 0
        self._items = list(items)
        if not preserve_scroll:
            self._start_index = 0
        else:
            self._start_index = top
        self._clamp_start_index()
        self._refresh_rows()
        self._sync_scrollbar()

    def scroll_to_index(self, index: int) -> None:
        self._start_index = max(0, min(index, self._max_start_index()))
        self._refresh_rows()
        self._sync_scrollbar()

    def winfo_children_list(self):
        rows = []
        for slot in self._pool:
            row = slot.get("row")
            if row is not None:
                try:
                    if row.winfo_exists():
                        rows.append(row)
                except tk.TclError:
                    pass
        return rows

    def _rows_in_viewport(self) -> int:
        return max(1, self._viewport_height // self.row_stride)

    def _pool_size(self) -> int:
        if not self._items:
            return self.visible_rows
        return min(self.visible_rows, len(self._items))

    def _max_start_index(self) -> int:
        if not self._items:
            return 0
        return max(0, len(self._items) - self._rows_in_viewport())

    def _clamp_start_index(self) -> None:
        self._start_index = max(0, min(self._start_index, self._max_start_index()))

    def _ensure_pool(self) -> None:
        if self._row_factory is None:
            return
        target = self._pool_size()
        while len(self._pool) < target:
            slot_frame = ctk.CTkFrame(self._row_host, fg_color="transparent")
            slot_frame.pack(fill="x", pady=self.ROW_PADY)
            slot = self._row_factory(slot_frame, -1, None)
            slot["row"] = slot_frame
            slot["_slot_frame"] = slot_frame
            self._pool.append(slot)

    def _sync_scrollbar(self) -> None:
        try:
            total = len(self._items)
            vis = self._rows_in_viewport()
            if total <= vis:
                self._v_scroll.set(0.0, 1.0)
                return
            max_start = self._max_start_index()
            top_frac = self._start_index / max_start if max_start else 0.0
            thumb = min(1.0, vis / total)
            bottom = min(1.0, top_frac + thumb)
            self._v_scroll.set(top_frac, bottom)
        except Exception:
            pass

    def _on_scrollbar(self, *args) -> None:
        if not self._items:
            return
        max_start = self._max_start_index()
        if max_start <= 0:
            self._start_index = 0
        elif args[0] == "moveto":
            self._start_index = int(float(args[1]) * max_start)
        elif args[0] == "scroll":
            step = int(args[1])
            mode = args[2] if len(args) > 2 else "units"
            delta = step * (self._rows_in_viewport() if mode == "pages" else 1)
            self._start_index += delta
        self._clamp_start_index()
        self._schedule_refresh_rows()

    def _on_mousewheel(self, event) -> str:
        if not self._items:
            return "break"
        delta = 0
        if getattr(event, "delta", 0):
            delta = int(-1 * (event.delta / 120))
        elif getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        if delta:
            self._start_index += delta
            self._clamp_start_index()
            self._schedule_refresh_rows()
        return "break"

    def _schedule_refresh_rows(self) -> None:
        if self._scroll_pending:
            return
        self._scroll_pending = True
        try:
            root = self.winfo_toplevel()
            root.after_idle(self._run_scheduled_refresh_rows)
        except Exception:
            self._scroll_pending = False
            self._refresh_rows()
            self._sync_scrollbar()

    def _run_scheduled_refresh_rows(self) -> None:
        self._scroll_pending = False
        self._refresh_rows()
        self._sync_scrollbar()

    def _refresh_rows(self) -> None:
        if self._row_binder is None:
            return
        for offset, slot in enumerate(self._pool):
            item_index = self._start_index + offset
            if item_index < len(self._items):
                item = self._items[item_index]
                slot["_slot_frame"].pack(fill="x", pady=self.ROW_PADY)
                self._row_binder(slot, item_index, item)
            else:
                slot["_slot_frame"].pack_forget()

    def _on_destroy(self, _event=None) -> None:
        pass