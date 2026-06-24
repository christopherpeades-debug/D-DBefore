"""Supabase REST sync for shared campaign dice roll logs."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from sync_http import supabase_request
from sync_intervals import (
    FOCUS_SLOW_POLL_MAX_SEC,
    ROLL_LOG_BACKGROUND_POLL_INTERVAL_SEC,
    ROLL_LOG_LIVE_POLL_INTERVAL_SEC,
    apply_focus_multiplier,
)

ROLL_LOG_TABLE = "campaign_dice_rolls"
DEFAULT_POLL_INTERVAL_SEC = ROLL_LOG_BACKGROUND_POLL_INTERVAL_SEC
DEFAULT_FETCH_LIMIT = 100


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def format_roll_log_timestamp(value):
    if not value:
        return ""
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone()
        return local.strftime("%I:%M:%S %p").lstrip("0")
    except (TypeError, ValueError):
        return str(value)


def _sidebar_roll_who(entry):
    if str(entry.get("character_id") or "") == "__dm__":
        return "DM"
    character = str(entry.get("character_name") or "").strip()
    player = str(entry.get("player_name") or "").strip()
    if character:
        return character
    if player:
        return player
    return "Unknown"


def _normalize_roll_detail(entry):
    detail = (entry or {}).get("roll_detail") or {}
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except json.JSONDecodeError:
            detail = {}
    return detail if isinstance(detail, dict) else {}


def _format_sidebar_roll_group(group):
    display = str(group.get("display") or "").strip().lower()
    try:
        total = int(group.get("total") or 0)
    except (TypeError, ValueError):
        total = 0
    if display:
        return f"{display}={total}"
    rolls = group.get("rolls") or []
    try:
        modifier = int(group.get("modifier") or 0)
    except (TypeError, ValueError):
        modifier = 0
    if rolls:
        try:
            dice_sum = sum(int(r) for r in rolls)
        except (TypeError, ValueError):
            dice_sum = total - modifier
    else:
        dice_sum = total - modifier
    if modifier > 0:
        mod_part = f"+{modifier}"
    elif modifier < 0:
        mod_part = str(modifier)
    else:
        mod_part = "+0"
    return f"{dice_sum}{mod_part}={total}"


def format_sidebar_roll_log_parts(entry):
    """Return (bold_prefix, body_suffix) for the sidebar roll chat line."""
    if not entry:
        return "", ""
    who = _sidebar_roll_who(entry)
    label = str(entry.get("roll_label") or "Roll").strip() or "Roll"
    bold = f"{who}:{label}"

    detail = _normalize_roll_detail(entry)
    groups = detail.get("groups")
    if groups:
        parts = []
        for group in groups:
            if isinstance(group, dict):
                parts.append(_format_sidebar_roll_group(group))
        if parts:
            return bold, " Rolls a " + ", ".join(parts)

    formula = str(entry.get("roll_formula") or "").strip().lower()
    result = str(entry.get("roll_result") or "").strip()
    if formula and result:
        return bold, f" Rolls a {formula}={result}"
    if formula:
        return bold, f" Rolls a {formula}"
    if result:
        return bold, f" Rolls a {result}"
    return bold, ""


def format_roll_log_line(entry, *, totals_only=False):
    if not entry:
        return ""
    ts = format_roll_log_timestamp(entry.get("created_at"))
    player = str(entry.get("player_name") or "").strip()
    character = str(entry.get("character_name") or "").strip()
    who = player or character or "Unknown"
    if player and character and player.lower() != character.lower():
        who = f"{player} ({character})"
    label = str(entry.get("roll_label") or "Roll").strip()
    formula = str(entry.get("roll_formula") or "").strip()
    result = str(entry.get("roll_result") or "").strip()
    if totals_only or not formula:
        detail = label
    else:
        detail = f"{label}: {formula}"
    prefix = f"[{ts}] {who} — " if ts else f"{who} — "
    return f"{prefix}{detail} → {result}"


class RollLogSyncClient:
    """Post and poll campaign dice rolls via Supabase REST."""

    def __init__(self, config_path, on_remote_update=None, on_status=None):
        self.config_path = config_path
        self.on_remote_update = on_remote_update
        self.on_status = on_status
        self.config = {}
        self._stop_event = threading.Event()
        self._thread = None
        self._entries = []
        self._entries_signature = None
        self._last_remote_head = None
        self._live_mode = False
        self._focus_interval_multiplier = 1

    def load_config(self):
        if not os.path.isfile(self.config_path):
            self.config = {}
            return self.config
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                self.config = json.load(handle)
        except (OSError, json.JSONDecodeError):
            self.config = {}
        return self.config

    def save_config(self, config):
        existing = {}
        if os.path.isfile(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    existing = data
            except (OSError, json.JSONDecodeError):
                pass
        self.config = dict(existing)
        if config:
            self.config.update(dict(config))
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle, indent=2)
        return self.config

    def is_configured(self):
        return bool(
            self.config.get("enabled")
            and self.config.get("supabase_url")
            and self.config.get("supabase_anon_key")
            and self.config.get("campaign_id")
        )

    def is_live_mode(self):
        return bool(self._live_mode)

    def set_live_mode(self, active):
        self._live_mode = bool(active)

    def set_focus_multiplier(self, multiplier):
        try:
            self._focus_interval_multiplier = max(1, min(8, int(multiplier or 1)))
        except (TypeError, ValueError):
            self._focus_interval_multiplier = 1

    def _invoke_callback(self, callback, *args, **kwargs):
        if callback is None or self._stop_event.is_set():
            return
        try:
            callback(*args, **kwargs)
        except RuntimeError:
            pass
        except Exception:
            pass

    def _set_status(self, message, is_error=False):
        self._invoke_callback(self.on_status, message, is_error)

    def _headers(self, prefer=None):
        key = self.config.get("supabase_anon_key", "")
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(self, method, path, body=None, prefer=None):
        base = str(self.config.get("supabase_url", "")).rstrip("/")
        try:
            return supabase_request(
                base, method, path, self._headers(prefer=prefer), body=body,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and "PGRST205" in detail:
                raise RuntimeError(
                    "The campaign_dice_rolls table is missing in Supabase.\n\n"
                    "Open Supabase → SQL Editor → New query, paste and run "
                    "supabase_roll_log_setup.sql (in your D&D Behind folder), then retry."
                ) from exc
            raise RuntimeError(f"Roll log HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Roll log network error: {exc.reason}") from exc

    def _campaign_path_prefix(self):
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        return f"/rest/v1/{ROLL_LOG_TABLE}?campaign_id=eq.{campaign_id}"

    def _head_signature(self, row):
        if not row:
            return None
        return (str(row.get("id") or ""), str(row.get("created_at") or ""))

    def _get_poll_interval_sec(self):
        if self._live_mode:
            try:
                return max(
                    1.0,
                    float(
                        self.config.get("roll_log_live_poll_interval_sec")
                        or ROLL_LOG_LIVE_POLL_INTERVAL_SEC
                    ),
                )
            except (TypeError, ValueError):
                return ROLL_LOG_LIVE_POLL_INTERVAL_SEC
        try:
            base = int(
                self.config.get("roll_log_poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC)
                or DEFAULT_POLL_INTERVAL_SEC
            )
        except (TypeError, ValueError):
            base = DEFAULT_POLL_INTERVAL_SEC
        return apply_focus_multiplier(
            max(2, base),
            multiplier=self._focus_interval_multiplier,
            max_sec=FOCUS_SLOW_POLL_MAX_SEC,
        )

    def _merge_entry_rows(self, new_rows, *, limit=DEFAULT_FETCH_LIMIT):
        if not new_rows:
            return list(self._entries)
        by_id = {
            str(row.get("id") or ""): row
            for row in (self._entries or [])
            if row.get("id")
        }
        for row in new_rows:
            row_id = str(row.get("id") or "")
            if row_id:
                by_id[row_id] = row
        merged = sorted(by_id.values(), key=lambda row: str(row.get("created_at") or ""), reverse=True)
        lim = max(1, min(int(limit or DEFAULT_FETCH_LIMIT), 200))
        if len(merged) > lim:
            merged = merged[:lim]
        self._entries = list(merged)
        self._entries_signature = self._signature_for_entries(merged)
        return list(merged)

    def _signature_for_entries(self, entries):
        return tuple(
            (
                str(row.get("id") or ""),
                str(row.get("created_at") or ""),
                str(row.get("roll_result") or ""),
            )
            for row in (entries or [])
        )

    def fetch_latest_head(self):
        if not self.is_configured():
            return None
        path = (
            f"{self._campaign_path_prefix()}"
            "&select=id,created_at&order=created_at.desc&limit=1"
        )
        rows = self._request("GET", path) or []
        return rows[0] if rows else None

    def fetch_rolls_since(self, since_created_at, *, limit=50):
        if not self.is_configured():
            return []
        encoded = urllib.parse.quote(str(since_created_at or ""), safe="")
        lim = max(1, min(int(limit or 50), 100))
        path = (
            f"{self._campaign_path_prefix()}"
            "&select=id,campaign_id,character_id,player_name,character_name,"
            "roll_label,roll_formula,roll_result,roll_detail,created_at"
            f"&created_at=gt.{encoded}&order=created_at.asc&limit={lim}"
        )
        return self._request("GET", path) or []

    def fetch_roll_log(self, limit=DEFAULT_FETCH_LIMIT):
        if not self.is_configured():
            return []
        lim = max(1, min(int(limit or DEFAULT_FETCH_LIMIT), 200))
        path = (
            f"{self._campaign_path_prefix()}"
            "&select=id,campaign_id,character_id,player_name,character_name,"
            "roll_label,roll_formula,roll_result,roll_detail,created_at"
            f"&order=created_at.desc&limit={lim}"
        )
        rows = self._request("GET", path) or []
        self._entries = list(rows)
        self._entries_signature = self._signature_for_entries(rows)
        self._last_remote_head = self._head_signature(rows[0] if rows else None)
        return list(rows)

    def poll_roll_updates(self):
        if not self.is_configured():
            return None
        head = self.fetch_latest_head()
        head_sig = self._head_signature(head)
        if head_sig and head_sig == self._last_remote_head and self._entries:
            return None
        if not self._entries:
            return self.fetch_roll_log()
        watermark = max((str(row.get("created_at") or "") for row in self._entries), default="")
        new_rows = self.fetch_rolls_since(watermark)
        if new_rows:
            merged = self._merge_entry_rows(new_rows)
            self._last_remote_head = head_sig or self._head_signature(merged[0] if merged else None)
            return merged
        if head_sig != self._last_remote_head:
            rows = self.fetch_roll_log()
            self._last_remote_head = head_sig
            return rows
        self._last_remote_head = head_sig
        return None

    def post_roll(self, roll_entry):
        if not self.is_configured():
            return None
        payload = {
            "campaign_id": self.config["campaign_id"],
            "character_id": str(roll_entry.get("character_id") or self.config.get("character_id") or ""),
            "player_name": str(roll_entry.get("player_name") or self.config.get("player_name") or ""),
            "character_name": str(roll_entry.get("character_name") or "Character"),
            "roll_label": str(roll_entry.get("roll_label") or "Roll"),
            "roll_formula": str(roll_entry.get("roll_formula") or ""),
            "roll_result": str(roll_entry.get("roll_result") or ""),
            "roll_detail": roll_entry.get("roll_detail") or {},
            "created_at": _utc_now_iso(),
        }
        path = f"/rest/v1/{ROLL_LOG_TABLE}"
        result = self._request(
            "POST", path, body=payload, prefer="return=representation",
        )
        if isinstance(result, list) and result:
            posted = result[0]
            self._last_remote_head = self._head_signature(posted)
            self._merge_entry_rows([posted])
            return posted
        return result

    def delete_campaign_roll_log(self):
        """Delete every roll row for the configured campaign."""
        if not self.is_configured():
            raise RuntimeError("Roll log is not configured.")
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = f"/rest/v1/{ROLL_LOG_TABLE}?campaign_id=eq.{campaign_id}"
        self._request("DELETE", path)
        self._entries = []
        self._entries_signature = None
        self._last_remote_head = None
        return True

    def start_polling(self):
        self.stop_polling()
        if not self.is_configured():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop_polling(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                rows = self.poll_roll_updates()
                if rows is not None:
                    self._invoke_callback(self.on_remote_update, list(rows))
            except Exception as exc:
                self._set_status(str(exc), is_error=True)
            self._stop_event.wait(self._get_poll_interval_sec())