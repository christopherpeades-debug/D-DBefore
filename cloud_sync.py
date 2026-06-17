"""Supabase REST sync for shared campaign character sheets."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

SYNC_CONFIG_FILENAME = "sync_config.json"
TABLE_NAME = "campaign_characters"
DEFAULT_POLL_INTERVAL_SEC = 5
DEFAULT_PUSH_INTERVAL_SEC = 15
DEFAULT_ACTIVE_CHARACTER_MINUTES = 15
DEFAULT_DM_STATUS_POLL_INTERVAL_SEC = 5
DM_STATUS_ABILITY_KEYS = (
    "Strength", "Dexterity", "Constitution",
    "Intelligence", "Wisdom", "Charisma",
)


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value):
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class CloudSyncManager:
    """Push/pull character JSON to a shared Supabase campaign table."""

    def __init__(self, config_path, on_remote_update=None, on_status=None):
        self.config_path = config_path
        self.on_remote_update = on_remote_update
        self.on_status = on_status
        self.config = {}
        self._stop_event = threading.Event()
        self._thread = None
        self._last_seen_remote_at = None
        self._last_error = ""
        self._dm_status_stop_event = threading.Event()
        self._dm_status_thread = None
        self._dm_status_callback = None
        self._last_dm_status_signature = None

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
        self.config = dict(config or {})
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle, indent=2)
        return self.config

    def is_configured(self):
        self.load_config()
        return bool(
            self.config.get("enabled")
            and self.config.get("supabase_url")
            and self.config.get("supabase_anon_key")
            and self.config.get("campaign_id")
            and self.config.get("character_id")
        )

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
        self._last_error = message if is_error else ""
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
        if not base:
            raise RuntimeError("Supabase URL is not configured.")
        url = f"{base}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(prefer=prefer),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
                if not raw.strip():
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Cloud sync HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cloud sync network error: {exc.reason}") from exc

    def test_connection(self):
        if not self.is_configured():
            raise RuntimeError("Cloud sync is not fully configured.")
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = (
            f"/rest/v1/{TABLE_NAME}?campaign_id=eq.{campaign_id}"
            f"&select=character_id&limit=1"
        )
        self._request("GET", path)
        self._set_status("Connected to cloud campaign")
        return True

    def upsert_character(self, character_data):
        if not self.is_configured():
            return False
        payload = {
            "campaign_id": self.config["campaign_id"],
            "character_id": self.config["character_id"],
            "player_name": self.config.get("player_name", ""),
            "character_name": character_data.get("name", "New Hero"),
            "data": character_data,
            "updated_at": _utc_now_iso(),
        }
        path = (
            f"/rest/v1/{TABLE_NAME}?on_conflict=campaign_id,character_id"
        )
        result = self._request(
            "POST",
            path,
            body=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        if isinstance(result, list) and result:
            self._last_seen_remote_at = _parse_iso(result[0].get("updated_at"))
        self._set_status("Cloud save complete")
        return True

    def fetch_current_character(self):
        if not self.is_configured():
            return None
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        character_id = urllib.parse.quote(str(self.config["character_id"]), safe="")
        path = (
            f"/rest/v1/{TABLE_NAME}?campaign_id=eq.{campaign_id}"
            f"&character_id=eq.{character_id}&select=data,updated_at&limit=1"
        )
        rows = self._request("GET", path) or []
        if not rows:
            return None
        row = rows[0]
        return {
            "data": row.get("data") or {},
            "updated_at": row.get("updated_at"),
        }

    def list_campaign_characters(self):
        if not self.is_configured():
            return []
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = (
            f"/rest/v1/{TABLE_NAME}?campaign_id=eq.{campaign_id}"
            "&select=character_id,player_name,character_name,updated_at"
            "&order=player_name.asc"
        )
        return self._request("GET", path) or []

    def list_active_campaign_characters(
        self,
        exclude_character_id=None,
        active_within_minutes=DEFAULT_ACTIVE_CHARACTER_MINUTES,
    ):
        """Characters whose cloud sheet was updated recently (app open / playing now)."""
        try:
            window_minutes = max(1, int(active_within_minutes or DEFAULT_ACTIVE_CHARACTER_MINUTES))
        except (TypeError, ValueError):
            window_minutes = DEFAULT_ACTIVE_CHARACTER_MINUTES
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        exclude = str(exclude_character_id or "").strip()
        active = []
        for row in self.list_campaign_characters():
            char_id = str(row.get("character_id") or "").strip()
            if exclude and char_id == exclude:
                continue
            updated = _parse_iso(row.get("updated_at"))
            if updated and updated >= cutoff:
                active.append(row)
        return active

    def upsert_character_by_id(
        self,
        character_id,
        character_data,
        *,
        player_name="",
        character_name="",
    ):
        if not self.is_configured():
            return False
        char_id = str(character_id or "").strip()
        if not char_id:
            raise RuntimeError("Character ID is required.")
        payload = {
            "campaign_id": self.config["campaign_id"],
            "character_id": char_id,
            "player_name": player_name or "",
            "character_name": character_data.get("name", character_name or "New Hero"),
            "data": character_data,
            "updated_at": _utc_now_iso(),
        }
        path = f"/rest/v1/{TABLE_NAME}?on_conflict=campaign_id,character_id"
        self._request(
            "POST",
            path,
            body=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        return True

    def fetch_character_by_id(self, character_id):
        if not self.is_configured():
            return None
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        char_id = urllib.parse.quote(str(character_id), safe="")
        path = (
            f"/rest/v1/{TABLE_NAME}?campaign_id=eq.{campaign_id}"
            f"&character_id=eq.{char_id}&select=data,updated_at,player_name,character_name&limit=1"
        )
        rows = self._request("GET", path) or []
        if not rows:
            return None
        row = rows[0]
        return {
            "character_id": character_id,
            "player_name": row.get("player_name", ""),
            "character_name": row.get("character_name", ""),
            "data": row.get("data") or {},
            "updated_at": row.get("updated_at"),
        }

    def note_remote_character(self, remote):
        """Record the latest cloud copy so polling does not immediately re-apply it."""
        if not remote:
            return
        remote_at = _parse_iso(remote.get("updated_at"))
        if remote_at:
            self._last_seen_remote_at = remote_at

    @staticmethod
    def normalize_dm_status(data):
        """Extract DM-controlled status fields in a stable, comparable shape."""
        source = data or {}
        afflictions = {
            str(key): bool(value)
            for key, value in sorted((source.get("afflictions") or {}).items())
        }
        negative_levels = max(0, int(source.get("negative_levels", 0) or 0))
        remote_damage = source.get("ability_damage") or {}
        ability_damage = {
            ability: max(0, int(remote_damage.get(ability, 0) or 0))
            for ability in DM_STATUS_ABILITY_KEYS
        }
        return {
            "afflictions": afflictions,
            "negative_levels": negative_levels,
            "ability_damage": ability_damage,
        }

    @classmethod
    def dm_status_signature(cls, data):
        status = cls.normalize_dm_status(data)
        return (
            tuple(sorted(status["afflictions"].items())),
            status["negative_levels"],
            tuple(status["ability_damage"].items()),
        )

    def note_dm_status(self, data):
        """Record the latest applied DM status so polling only fires on real changes."""
        self._last_dm_status_signature = self.dm_status_signature(data)

    def start_dm_status_polling(self, on_dm_status_update):
        """Poll cloud every few seconds for afflictions / neg levels / ability damage."""
        self.stop_dm_status_polling()
        if not self.is_configured():
            return
        self._dm_status_callback = on_dm_status_update
        self._dm_status_stop_event.clear()
        self._dm_status_thread = threading.Thread(
            target=self._dm_status_poll_loop,
            daemon=True,
        )
        self._dm_status_thread.start()

    def stop_dm_status_polling(self):
        self._dm_status_stop_event.set()
        if self._dm_status_thread and self._dm_status_thread.is_alive():
            self._dm_status_thread.join(timeout=1.0)
        self._dm_status_thread = None
        self._dm_status_callback = None

    def _dm_status_poll_loop(self):
        interval = max(
            3,
            int(
                self.config.get(
                    "dm_status_poll_interval_sec",
                    DEFAULT_DM_STATUS_POLL_INTERVAL_SEC,
                )
                or DEFAULT_DM_STATUS_POLL_INTERVAL_SEC
            ),
        )
        while not self._dm_status_stop_event.is_set():
            try:
                remote = self.fetch_current_character()
                if remote:
                    remote_data = remote.get("data") or {}
                    signature = self.dm_status_signature(remote_data)
                    if signature != self._last_dm_status_signature:
                        self._last_dm_status_signature = signature
                        payload = self.normalize_dm_status(remote_data)
                        self._invoke_callback(self._dm_status_callback, payload)
            except Exception:
                pass
            self._dm_status_stop_event.wait(interval)

    def start(self):
        self.stop()
        if not self.is_configured() or not self.config.get("auto_sync", True):
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        self._set_status("Live cloud sync enabled")

    def stop(self):
        self.stop_dm_status_polling()
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _poll_loop(self):
        poll_interval = max(
            3,
            int(self.config.get("poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC) or DEFAULT_POLL_INTERVAL_SEC),
        )
        push_interval = max(
            5,
            int(self.config.get("push_interval_sec", DEFAULT_PUSH_INTERVAL_SEC) or DEFAULT_PUSH_INTERVAL_SEC),
        )
        last_push_check = 0.0
        while not self._stop_event.is_set():
            try:
                remote = self.fetch_current_character()
                if remote:
                    remote_at = _parse_iso(remote.get("updated_at"))
                    if remote_at and (
                        self._last_seen_remote_at is None
                        or remote_at > self._last_seen_remote_at
                    ):
                        self._last_seen_remote_at = remote_at
                        self._invoke_callback(self.on_remote_update, remote)
            except Exception as exc:
                self._set_status(str(exc), is_error=True)
            now = time.monotonic()
            if self.on_status and now - last_push_check >= push_interval:
                last_push_check = now
                self.on_status("__PUSH_TICK__", False)
            self._stop_event.wait(poll_interval)