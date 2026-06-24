"""Shared polling interval helpers for Supabase sync clients."""

from __future__ import annotations

CHAT_LIVE_POLL_INTERVAL_SEC = 1.5
CHAT_BACKGROUND_POLL_INTERVAL_SEC = 8
ROLL_LOG_LIVE_POLL_INTERVAL_SEC = 1.5
ROLL_LOG_BACKGROUND_POLL_INTERVAL_SEC = 8
FOCUS_SLOW_POLL_MULTIPLIER = 4
FOCUS_SLOW_POLL_MAX_SEC = 60


def apply_focus_multiplier(interval_sec, *, multiplier=1, max_sec=FOCUS_SLOW_POLL_MAX_SEC):
    try:
        base = max(1, float(interval_sec or 1))
    except (TypeError, ValueError):
        base = 1.0
    try:
        mult = max(1, int(multiplier or 1))
    except (TypeError, ValueError):
        mult = 1
    try:
        cap = max(base, float(max_sec or FOCUS_SLOW_POLL_MAX_SEC))
    except (TypeError, ValueError):
        cap = float(FOCUS_SLOW_POLL_MAX_SEC)
    return min(cap, base * mult)