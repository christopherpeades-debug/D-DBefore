"""Feat and spell description lookup for statblock hover tooltips."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_DATA_DIR = _SCRIPT_DIR / "data"

FEAT_ALIASES = {
    "combat expertis": "Combat Expertise",
    "weapon finess": "Weapon Finesse",
    "weapon finesse": "Weapon Finesse",
    "whirlwhind attack": "Whirlwind Attack",
    "greater weapon specializtion": "Greater Weapon Specialization",
    "greater spell focus": "Greater Spell Focus",
    "greater spell focus": "Greater Spell Focus",
    "shield profciency": "Shield Proficiency",
    "exotic weapon prof": "Exotic Weapon Proficiency",
    "blind fight": "Blind-Fight",
    "blind-fight": "Blind-Fight",
}

FEAT_PAREN_ALIASES = {
    "armor proficiency light": "Armor Proficiency (Light)",
    "armor proficiency medium": "Armor Proficiency (Medium)",
    "armor proficiency heavy": "Armor Proficiency (Heavy)",
    "tower shield proficiency": "Tower Shield Proficiency",
}

_SPELL_NOISE_RE = re.compile(
    r"\[roll:[^\]]+\]|\[c[^\]]*\]|\[[^\]]*\]|\([^)]*\)",
    re.IGNORECASE,
)


def _read_json_dict(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


@lru_cache(maxsize=1)
def load_feats_db() -> dict:
    candidates = [
        _DATA_DIR / "feats.json",
        _DATA_DIR / "Feats.json",
        _SCRIPT_DIR / "Feats.json",
        Path(r"D:\OneDrive\DnD Beside\Feats.json"),
        Path(r"D:\OneDrive\D&D Behind\Feats.json"),
        _SCRIPT_DIR.parent / "DnD Beside" / "Feats.json",
    ]
    for path in candidates:
        if path.is_file():
            data = _read_json_dict(path)
            if data:
                return data
    return {}


@lru_cache(maxsize=1)
def load_spells_db() -> dict:
    candidates = [
        _DATA_DIR / "spells.json",
        Path(r"D:\OneDrive\DnD Beside\spells.json"),
        Path(r"D:\OneDrive\D&D Behind\spells.json"),
        _SCRIPT_DIR.parent / "DnD Beside" / "spells.json",
    ]
    for path in candidates:
        if path.is_file():
            data = _read_json_dict(path)
            if data:
                return data
    return {}


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def normalize_feat_name(name: str) -> str:
    text = re.sub(r"^[\s•\u2022]+", "", str(name or "").strip())
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    text = re.sub(r"\s*\[[^\]]*\]\s*$", "", text).strip()
    return text


def lookup_feat_entry(name: str, db: dict | None = None) -> dict | None:
    db = db if db is not None else load_feats_db()
    if not db:
        return None
    base = normalize_feat_name(name)
    if not base:
        return None
    if base in db:
        return db[base]
    lower_index = {_norm_key(k): k for k in db}
    hit = lower_index.get(_norm_key(base))
    if hit:
        return db[hit]
    alias = FEAT_ALIASES.get(_norm_key(base))
    if alias and alias in db:
        return db[alias]
    paren_alias = FEAT_PAREN_ALIASES.get(_norm_key(base))
    if paren_alias and paren_alias in db:
        return db[paren_alias]
    return None


def format_feat_tooltip(name: str, db: dict | None = None) -> str:
    entry = lookup_feat_entry(name, db=db)
    if not entry:
        return ""
    title = normalize_feat_name(name) or str(name or "").strip()
    prereq = str(entry.get("prerequisites") or "").strip()
    desc = str(entry.get("description") or "").strip()
    if not desc and not prereq:
        return ""
    lines = [title]
    if prereq and prereq.lower() != "none":
        lines.append(f"Prerequisites: {prereq}")
    if desc:
        if len(lines) > 1:
            lines.append("")
        lines.append(desc)
    return "\n".join(lines)


def _clean_spell_token(token: str) -> str:
    text = _SPELL_NOISE_RE.sub("", str(token or ""))
    return re.sub(r"\s+", " ", text).strip(" ,")


def lookup_spell_entry(name: str, db: dict | None = None) -> dict | None:
    db = db if db is not None else load_spells_db()
    if not db:
        return None
    clean = _clean_spell_token(name)
    if not clean:
        return None
    if clean in db:
        return db[clean]
    lower_index = {_norm_key(k): k for k in db}
    hit = lower_index.get(_norm_key(clean))
    if hit:
        return db[hit]
    return None


def format_spell_tooltip(name: str, db: dict | None = None) -> str:
    entry = lookup_spell_entry(name, db=db)
    if not entry:
        return ""
    title = _clean_spell_token(name) or str(name or "").strip()
    desc = str(entry.get("description") or "").strip()
    if not desc:
        return ""
    level = entry.get("level")
    if level is not None and str(level).strip() != "":
        return f"{title} (level {level})\n\n{desc}"
    return f"{title}\n\n{desc}"


def bind_delayed_tooltip(widget, text_or_fn, *, delay_ms: int = 450):
    """Attach a delayed dark tooltip to a widget. text_or_fn may be a string or callable."""
    import tkinter as tk

    import customtkinter as ctk

    state = {"after": None, "top": None}

    def _resolve_text():
        try:
            return str(text_or_fn() if callable(text_or_fn) else text_or_fn or "")
        except Exception:
            return ""

    def _cancel():
        after_id = state.get("after")
        if after_id is not None:
            try:
                widget.after_cancel(after_id)
            except Exception:
                pass
            state["after"] = None

    def _hide(_evt=None):
        _cancel()
        top = state.get("top")
        if top is not None:
            try:
                top.destroy()
            except Exception:
                pass
            state["top"] = None

    def _show(_evt=None):
        state["after"] = None
        if state.get("top"):
            return
        text = _resolve_text().strip()
        if not text:
            return
        try:
            top = tk.Toplevel(widget)
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            frm = ctk.CTkFrame(top, fg_color="#1f1f1f", border_width=1, border_color="#444", corner_radius=5)
            frm.pack()
            ctk.CTkLabel(
                frm, text=text, font=ctk.CTkFont(size=9), text_color="#ccc",
                wraplength=320, justify="left", anchor="nw",
            ).pack(padx=8, pady=6)
            top.update_idletasks()
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height() + 2
            top.geometry(f"+{x}+{y}")
            state["top"] = top
        except Exception:
            pass

    def _schedule(_evt=None):
        _hide()
        state["after"] = widget.after(delay_ms, _show)

    try:
        widget.bind("<Enter>", _schedule, add="+")
        widget.bind("<Leave>", _hide, add="+")
        widget.bind("<Button-1>", _hide, add="+")
    except Exception:
        pass


def split_spell_line(text: str) -> tuple[str, list[str]]:
    raw = str(text or "").strip()
    if not raw:
        return "", []
    prefix = ""
    body = raw
    if " — " in raw:
        prefix, body = raw.split(" — ", 1)
        prefix = prefix.strip()
        body = body.strip()
    tokens = [part.strip() for part in body.split(",") if part.strip()]
    return prefix, tokens