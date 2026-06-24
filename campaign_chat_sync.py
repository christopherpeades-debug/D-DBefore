"""Supabase REST sync for shared campaign text chat messages."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from sync_http import supabase_request
from sync_intervals import (
    CHAT_BACKGROUND_POLL_INTERVAL_SEC,
    CHAT_LIVE_POLL_INTERVAL_SEC,
    FOCUS_SLOW_POLL_MAX_SEC,
    apply_focus_multiplier,
)

CHAT_TABLE = "campaign_chat_messages"
WHISPER_TO_DM = "__dm__"
DEFAULT_POLL_INTERVAL_SEC = CHAT_BACKGROUND_POLL_INTERVAL_SEC
DEFAULT_FETCH_LIMIT = 200
CHAT_SELECT_FIELDS_LEGACY = (
    "id,campaign_id,character_id,player_name,character_name,"
    "message_text,created_at"
)
CHAT_SELECT_FIELDS = (
    "id,campaign_id,character_id,player_name,character_name,"
    "message_text,whisper_to_character_id,whisper_to_character_name,created_at"
)


def _is_missing_whisper_column_error(detail) -> bool:
    text = str(detail or "").lower()
    return "42703" in text and "whisper" in text


def _normalize_chat_rows(rows):
    normalized = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item.setdefault("whisper_to_character_id", "")
        item.setdefault("whisper_to_character_name", "")
        normalized.append(item)
    return normalized


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def chat_message_who(entry):
    if str(entry.get("character_id") or "") == "__dm__":
        return "DM"
    character = str(entry.get("character_name") or "").strip()
    if character:
        return character
    player = str(entry.get("player_name") or "").strip()
    if player:
        return player
    return "Unknown"


def is_whisper_message(entry) -> bool:
    return bool(str(entry.get("whisper_to_character_id") or "").strip())


def chat_entry_visible_to_viewer(
    entry,
    viewer_character_id,
    *,
    is_dm: bool = False,
) -> bool:
    """Return whether a chat row should appear in this client's feed."""
    if not entry:
        return False
    whisper_to = str(entry.get("whisper_to_character_id") or "").strip()
    if not whisper_to:
        return True
    sender_id = str(entry.get("character_id") or "").strip()
    viewer_id = str(viewer_character_id or "").strip()
    if sender_id and viewer_id and sender_id == viewer_id:
        return True
    if is_dm:
        if whisper_to == WHISPER_TO_DM:
            return True
        if sender_id == WHISPER_TO_DM:
            return True
        return False
    return whisper_to == viewer_id


def filter_chat_entries_for_viewer(
    entries,
    viewer_character_id,
    *,
    is_dm: bool = False,
) -> list[dict]:
    return [
        row
        for row in (entries or [])
        if chat_entry_visible_to_viewer(row, viewer_character_id, is_dm=is_dm)
    ]


def parse_chat_send_command(text, *, is_dm: bool = False) -> dict:
    """Parse /dm and /w chat commands.

    Returns a dict with message_text and optional whisper routing fields.
    On invalid command syntax, returns {"error": "..."}.
    """
    raw = str(text or "").strip()
    if not raw:
        return {"error": "Message is empty."}

    dm_match = re.match(r"^/dm(?:\s+|$)(.*)$", raw, re.IGNORECASE | re.DOTALL)
    if dm_match:
        if is_dm:
            return {"error": "DM uses /w PlayerName message to whisper to a player."}
        body = str(dm_match.group(1) or "").strip()
        if not body:
            return {"error": "Usage: /dm message"}
        return {
            "message_text": body,
            "whisper_to_character_id": WHISPER_TO_DM,
            "whisper_to_character_name": "DM",
        }

    if is_dm:
        whisper_match = re.match(r"^/w(?:\s+)(\S+)(?:\s+)(.*)$", raw, re.IGNORECASE | re.DOTALL)
        if whisper_match:
            target_name = str(whisper_match.group(1) or "").strip()
            body = str(whisper_match.group(2) or "").strip()
            if not target_name:
                return {"error": "Usage: /w PlayerName message"}
            if not body:
                return {"error": "Usage: /w PlayerName message"}
            return {
                "message_text": body,
                "whisper_target_name": target_name,
            }

    return {"message_text": raw}


def format_chat_message_parts(entry):
    """Return (bold_name, body_suffix) for **[Name]**: message display."""
    if not entry:
        return "", ""
    who = chat_message_who(entry)
    text = str(entry.get("message_text") or "").strip()
    whisper_to = str(entry.get("whisper_to_character_id") or "").strip()
    if whisper_to == WHISPER_TO_DM:
        return who, f" → DM: {text}" if text else " → DM:"
    if whisper_to:
        target = str(entry.get("whisper_to_character_name") or "").strip() or "Player"
        return who, f" → {target}: {text}" if text else f" → {target}:"
    return who, f": {text}" if text else ":"


def merge_campaign_feed(roll_entries, chat_entries, *, limit=None):
    items = []
    for row in roll_entries or []:
        items.append(("roll", str(row.get("created_at") or ""), row))
    for row in chat_entries or []:
        items.append(("chat", str(row.get("created_at") or ""), row))
    items.sort(key=lambda item: item[1])
    if limit is not None:
        items = items[-max(1, int(limit)) :]
    return [(kind, row) for kind, _ts, row in items]


class CampaignChatSyncClient:
    """Post and poll campaign chat messages via Supabase REST."""

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
        self._whisper_columns_available = None
        self._whisper_migration_warned = False

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

    def _select_fields(self):
        if self._whisper_columns_available is False:
            return CHAT_SELECT_FIELDS_LEGACY
        return CHAT_SELECT_FIELDS

    def _warn_whisper_migration_once(self):
        if self._whisper_migration_warned:
            return
        self._whisper_migration_warned = True
        self._set_status(
            "Whisper chat needs a Supabase migration — run supabase_campaign_chat_setup.sql.",
            is_error=True,
        )

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
                    "The campaign_chat_messages table is missing in Supabase.\n\n"
                    "Open Supabase → SQL Editor → New query, paste and run "
                    "supabase_campaign_chat_setup.sql, then retry."
                ) from exc
            raise RuntimeError(f"Campaign chat HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Campaign chat network error: {exc.reason}") from exc

    def _campaign_path_prefix(self):
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        return (
            f"/rest/v1/{CHAT_TABLE}?campaign_id=eq.{campaign_id}"
        )

    def _signature_for_entries(self, entries):
        return tuple(
            (
                str(row.get("id") or ""),
                str(row.get("created_at") or ""),
                str(row.get("message_text") or ""),
            )
            for row in (entries or [])
        )

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
                        self.config.get("chat_live_poll_interval_sec")
                        or CHAT_LIVE_POLL_INTERVAL_SEC
                    ),
                )
            except (TypeError, ValueError):
                return CHAT_LIVE_POLL_INTERVAL_SEC
        try:
            base = int(
                self.config.get("chat_poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC)
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
        merged = sorted(by_id.values(), key=lambda row: str(row.get("created_at") or ""))
        lim = max(1, min(int(limit or DEFAULT_FETCH_LIMIT), 500))
        if len(merged) > lim:
            merged = merged[-lim:]
        self._entries = list(merged)
        self._entries_signature = self._signature_for_entries(merged)
        return list(merged)

    def fetch_latest_head(self):
        if not self.is_configured():
            return None
        path = (
            f"{self._campaign_path_prefix()}"
            "&select=id,created_at&order=created_at.desc&limit=1"
        )
        rows = self._request("GET", path) or []
        return rows[0] if rows else None

    def _fetch_messages_since_request(self, since_created_at, *, limit, select_fields):
        encoded = urllib.parse.quote(str(since_created_at or ""), safe="")
        lim = max(1, min(int(limit or 100), 200))
        path = (
            f"{self._campaign_path_prefix()}"
            f"&select={select_fields}&created_at=gt.{encoded}"
            f"&order=created_at.asc&limit={lim}"
        )
        return self._request("GET", path) or []

    def fetch_messages_since(self, since_created_at, *, limit=100):
        if not self.is_configured():
            return []
        select_fields = self._select_fields()
        try:
            rows = self._fetch_messages_since_request(
                since_created_at, limit=limit, select_fields=select_fields,
            )
        except RuntimeError as exc:
            if select_fields == CHAT_SELECT_FIELDS and _is_missing_whisper_column_error(str(exc)):
                self._whisper_columns_available = False
                self._warn_whisper_migration_once()
                rows = self._fetch_messages_since_request(
                    since_created_at,
                    limit=limit,
                    select_fields=CHAT_SELECT_FIELDS_LEGACY,
                )
            else:
                raise
        return _normalize_chat_rows(rows)

    def _fetch_messages_request(self, *, limit, select_fields):
        lim = max(1, min(int(limit or DEFAULT_FETCH_LIMIT), 500))
        path = (
            f"{self._campaign_path_prefix()}"
            f"&select={select_fields}&order=created_at.desc&limit={lim}"
        )
        return self._request("GET", path) or []

    def fetch_messages(self, limit=DEFAULT_FETCH_LIMIT):
        if not self.is_configured():
            return []
        select_fields = self._select_fields()
        try:
            rows = self._fetch_messages_request(limit=limit, select_fields=select_fields)
            if self._whisper_columns_available is None and select_fields == CHAT_SELECT_FIELDS:
                self._whisper_columns_available = True
        except RuntimeError as exc:
            if select_fields == CHAT_SELECT_FIELDS and _is_missing_whisper_column_error(str(exc)):
                self._whisper_columns_available = False
                self._warn_whisper_migration_once()
                rows = self._fetch_messages_request(
                    limit=limit, select_fields=CHAT_SELECT_FIELDS_LEGACY,
                )
            else:
                raise
        rows = _normalize_chat_rows(list(reversed(rows)))
        self._entries = list(rows)
        self._entries_signature = self._signature_for_entries(rows)
        head = rows[-1] if rows else self.fetch_latest_head()
        self._last_remote_head = self._head_signature(head)
        return list(rows)

    def poll_chat_updates(self):
        """Cheap head check, then incremental fetch for new messages only."""
        if not self.is_configured():
            return None
        head = self.fetch_latest_head()
        head_sig = self._head_signature(head)
        if head_sig and head_sig == self._last_remote_head and self._entries:
            return None
        if not self._entries:
            return self.fetch_messages()
        watermark = max((str(row.get("created_at") or "") for row in self._entries), default="")
        new_rows = self.fetch_messages_since(watermark)
        if new_rows:
            merged = self._merge_entry_rows(new_rows)
            self._last_remote_head = head_sig or self._head_signature(merged[-1] if merged else None)
            return merged
        if head_sig != self._last_remote_head:
            rows = self.fetch_messages()
            self._last_remote_head = head_sig
            return rows
        self._last_remote_head = head_sig
        return None

    def _build_post_payload(self, message_entry, *, include_whisper=True):
        whisper_to = str(message_entry.get("whisper_to_character_id") or "").strip()
        whisper_name = str(message_entry.get("whisper_to_character_name") or "").strip()
        payload = {
            "campaign_id": self.config["campaign_id"],
            "character_id": str(
                message_entry.get("character_id") or self.config.get("character_id") or ""
            ),
            "player_name": str(
                message_entry.get("player_name") or self.config.get("player_name") or ""
            ),
            "character_name": str(message_entry.get("character_name") or "Character"),
            "message_text": str(message_entry.get("message_text") or "").strip(),
            "created_at": _utc_now_iso(),
        }
        if include_whisper:
            payload["whisper_to_character_id"] = whisper_to or None
            payload["whisper_to_character_name"] = whisper_name or None
        return payload

    def post_message(self, message_entry):
        if not self.is_configured():
            return None
        include_whisper = self._whisper_columns_available is not False
        payload = self._build_post_payload(message_entry, include_whisper=include_whisper)
        path = f"/rest/v1/{CHAT_TABLE}"
        try:
            result = self._request("POST", path, body=payload, prefer="return=representation")
        except RuntimeError as exc:
            if include_whisper and _is_missing_whisper_column_error(str(exc)):
                self._whisper_columns_available = False
                self._warn_whisper_migration_once()
                payload = self._build_post_payload(message_entry, include_whisper=False)
                result = self._request("POST", path, body=payload, prefer="return=representation")
            else:
                raise
        if isinstance(result, list) and result:
            posted = _normalize_chat_rows(result)[0]
            self._last_remote_head = self._head_signature(posted)
            merged = self._merge_entry_rows([posted])
            return posted if merged else posted
        return result

    def delete_campaign_chat(self):
        if not self.is_configured():
            raise RuntimeError("Campaign chat is not configured.")
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = f"/rest/v1/{CHAT_TABLE}?campaign_id=eq.{campaign_id}"
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
                rows = self.poll_chat_updates()
                if rows is not None:
                    self._invoke_callback(self.on_remote_update, list(rows))
            except Exception as exc:
                self._set_status(str(exc), is_error=True)
            self._stop_event.wait(self._get_poll_interval_sec())