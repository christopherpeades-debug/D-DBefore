"""Supabase REST sync for shared campaign character sheets."""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from sync_http import supabase_request
from sync_intervals import FOCUS_SLOW_POLL_MAX_SEC, apply_focus_multiplier

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
SURVIVAL_DAY_KEYS = ("starvation", "thirst", "exhaustion")
AFFLICTIONS_UPDATED_AT_KEY = "afflictions_updated_at"
_AFFLICTION_EPOCH = datetime.min.replace(tzinfo=timezone.utc)

DM_STATUS_DATA_KEYS = (
    "afflictions",
    "afflictions_updated_at",
    "negative_levels",
    "ability_damage",
    "dm_weather",
    "survival_days",
    "forced_rest",
    "dm_forced_rest",
    "dm_pending_nonlethal",
    "pending_nonlethal",
    "dm_xp_award",
)
DM_STATUS_SELECT_FIELDS = (
    "afflictions:data->afflictions",
    "afflictions_updated_at:data->afflictions_updated_at",
    "negative_levels:data->negative_levels",
    "ability_damage:data->ability_damage",
    "dm_weather:data->dm_weather",
    "survival_days:data->survival_days",
    "forced_rest:data->forced_rest",
    "dm_forced_rest:data->dm_forced_rest",
    "dm_pending_nonlethal:data->dm_pending_nonlethal",
    "pending_nonlethal:data->pending_nonlethal",
    "dm_xp_award:data->dm_xp_award",
)


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def read_sync_config_file(config_path):
    if not config_path or not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def merge_sync_config_file(config_path, updates):
    """Apply updates on top of the on-disk config without dropping unrelated keys."""
    merged = read_sync_config_file(config_path)
    if updates:
        merged.update(dict(updates))
    return merged


def _parse_iso(value):
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def normalize_afflictions_updated_at(source):
    """Return {affliction_name: iso_timestamp} with only valid timestamps."""
    raw = (source or {}).get(AFFLICTIONS_UPDATED_AT_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, val in raw.items():
        if str(key).startswith("_"):
            continue
        parsed = _parse_iso(val)
        if parsed:
            out[str(key)] = parsed.isoformat()
    return out


def stamp_affliction(data, name, checked, *, when=None):
    """Record an affliction toggle and its UTC timestamp (newer wins on sync)."""
    when_iso = when or _utc_now_iso()
    target = data if isinstance(data, dict) else {}
    target.setdefault("afflictions", {})[str(name)] = bool(checked)
    target.setdefault(AFFLICTIONS_UPDATED_AT_KEY, {})[str(name)] = when_iso
    return when_iso


def backfill_affliction_timestamps(data, *, when=None):
    """Legacy sheets (e.g. cloud Jeramiah) may lack per-key timestamps — seed them."""
    if not isinstance(data, dict):
        return
    when_iso = when or _utc_now_iso()
    afflictions = data.get("afflictions") or {}
    if not isinstance(afflictions, dict):
        return
    ts_map = data.setdefault(AFFLICTIONS_UPDATED_AT_KEY, {})
    if not isinstance(ts_map, dict):
        ts_map = {}
        data[AFFLICTIONS_UPDATED_AT_KEY] = ts_map
    for key in afflictions:
        if str(key).startswith("_"):
            continue
        if not _parse_iso(ts_map.get(key)):
            ts_map[str(key)] = when_iso


def merge_afflictions_by_timestamp(local_data, remote_data, *, protect_local=False):
    """Merge affliction booleans per key; the side with the newer timestamp wins."""
    local_aff = {
        str(key): bool(value)
        for key, value in ((local_data or {}).get("afflictions") or {}).items()
    }
    local_ts = normalize_afflictions_updated_at(local_data)
    if protect_local:
        return dict(local_aff), dict(local_ts)

    remote_aff = {
        str(key): bool(value)
        for key, value in ((remote_data or {}).get("afflictions") or {}).items()
    }
    remote_ts = normalize_afflictions_updated_at(remote_data)

    merged_aff = {}
    merged_ts = {}
    for key in set(local_aff) | set(remote_aff) | set(local_ts) | set(remote_ts):
        local_val = bool(local_aff.get(key, False))
        remote_val = bool(remote_aff.get(key, False))
        local_at = _parse_iso(local_ts.get(key)) or _AFFLICTION_EPOCH
        remote_at = _parse_iso(remote_ts.get(key)) or _AFFLICTION_EPOCH

        if remote_at > local_at:
            merged_aff[key] = remote_val
            merged_ts[key] = remote_ts.get(key) or remote_at.isoformat()
        elif local_at > remote_at:
            merged_aff[key] = local_val
            merged_ts[key] = local_ts.get(key) or local_at.isoformat()
        else:
            merged_aff[key] = local_val
            if local_ts.get(key):
                merged_ts[key] = local_ts[key]
            elif remote_ts.get(key):
                merged_ts[key] = remote_ts[key]

    return merged_aff, merged_ts


def merge_afflictions_into(target_data, remote_data, *, protect_local=False):
    """Write timestamp-merged afflictions into target_data. Returns True if values changed."""
    if not isinstance(target_data, dict):
        return False
    old_aff = {
        str(key): bool(value)
        for key, value in (target_data.get("afflictions") or {}).items()
    }
    merged_aff, merged_ts = merge_afflictions_by_timestamp(
        target_data, remote_data, protect_local=protect_local,
    )
    target_data["afflictions"] = merged_aff
    target_data[AFFLICTIONS_UPDATED_AT_KEY] = merged_ts
    return merged_aff != old_aff


def prepare_character_data_for_cloud_upsert(local_data, remote_data, *, protect_local=False):
    """Merge afflictions into outgoing data so cloud writes never stomp newer edits."""
    payload = copy.deepcopy(local_data) if isinstance(local_data, dict) else {}
    if isinstance(remote_data, dict):
        merge_afflictions_into(payload, remote_data, protect_local=protect_local)
    return payload


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
        self._last_dm_remote_updated_at = None
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
        self.config = merge_sync_config_file(self.config_path, config)
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
        try:
            return supabase_request(
                base, method, path, self._headers(prefer=prefer), body=body,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Cloud sync HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cloud sync network error: {exc.reason}") from exc

    def set_focus_multiplier(self, multiplier):
        try:
            self._focus_interval_multiplier = max(1, min(8, int(multiplier or 1)))
        except (TypeError, ValueError):
            self._focus_interval_multiplier = 1

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

    def upsert_character(self, character_data, *, protect_local_afflictions=False):
        if not self.is_configured():
            return False
        merged_data = character_data
        try:
            remote = self.fetch_current_character()
            if remote and isinstance(remote.get("data"), dict):
                merged_data = prepare_character_data_for_cloud_upsert(
                    character_data,
                    remote["data"],
                    protect_local=protect_local_afflictions,
                )
        except Exception:
            merged_data = character_data
        payload = {
            "campaign_id": self.config["campaign_id"],
            "character_id": self.config["character_id"],
            "player_name": self.config.get("player_name", ""),
            "character_name": merged_data.get("name", "New Hero"),
            "data": merged_data,
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

    stamp_affliction = staticmethod(stamp_affliction)
    merge_afflictions_into = staticmethod(merge_afflictions_into)
    merge_afflictions_by_timestamp = staticmethod(merge_afflictions_by_timestamp)
    backfill_affliction_timestamps = staticmethod(backfill_affliction_timestamps)

    def _character_lookup_path(self):
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        character_id = urllib.parse.quote(str(self.config["character_id"]), safe="")
        return (
            f"/rest/v1/{TABLE_NAME}?campaign_id=eq.{campaign_id}"
            f"&character_id=eq.{character_id}"
        )

    @staticmethod
    def _row_to_dm_status_data(row):
        data = {}
        for key in DM_STATUS_DATA_KEYS:
            value = row.get(key)
            if value is not None:
                data[key] = value
        return data

    def fetch_character_revision(self):
        """Lightweight fetch of updated_at only (for remote-version bookkeeping)."""
        if not self.is_configured():
            return None
        path = f"{self._character_lookup_path()}&select=updated_at&limit=1"
        rows = self._request("GET", path) or []
        if not rows:
            return None
        return {"updated_at": rows[0].get("updated_at")}

    def _fetch_dm_status_fields(self):
        select = ",".join((*DM_STATUS_SELECT_FIELDS, "updated_at"))
        path = f"{self._character_lookup_path()}&select={select}&limit=1"
        try:
            rows = self._request("GET", path) or []
        except Exception:
            return self.fetch_current_character()
        if not rows:
            return None
        row = rows[0]
        return {
            "data": self._row_to_dm_status_data(row),
            "updated_at": row.get("updated_at"),
        }

    def fetch_dm_status(self, *, force=False):
        """Fetch only DM-controlled fields; skips download when updated_at is unchanged."""
        if not self.is_configured():
            return None
        revision = self.fetch_character_revision()
        if not revision:
            return None
        updated_at = revision.get("updated_at")
        if (
            not force
            and updated_at
            and self._last_dm_remote_updated_at
            and updated_at == self._last_dm_remote_updated_at
        ):
            return {"data": None, "updated_at": updated_at, "unchanged": True}
        remote = self._fetch_dm_status_fields()
        if remote:
            self._last_dm_remote_updated_at = remote.get("updated_at") or updated_at
        return remote

    def fetch_current_character(self):
        if not self.is_configured():
            return None
        path = f"{self._character_lookup_path()}&select=data,updated_at&limit=1"
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

    def delete_character_by_id(self, character_id):
        if not self.is_configured():
            return False
        char_id = str(character_id or "").strip()
        if not char_id:
            raise RuntimeError("Character ID is required.")
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        encoded_char_id = urllib.parse.quote(char_id, safe="")
        path = (
            f"/rest/v1/{TABLE_NAME}?campaign_id=eq.{campaign_id}"
            f"&character_id=eq.{encoded_char_id}"
        )
        self._request("DELETE", path)
        if str(self.config.get("character_id", "")).strip() == char_id:
            self._last_seen_remote_at = None
            self._last_dm_status_signature = None
        self._set_status(f"Deleted character {char_id} from cloud")
        return True

    def note_remote_character(self, remote):
        """Record the latest cloud copy so polling does not immediately re-apply it."""
        if not remote:
            return
        remote_at = _parse_iso(remote.get("updated_at"))
        if remote_at:
            self._last_seen_remote_at = remote_at

    @staticmethod
    def _normalize_dm_weather(source):
        raw = source.get("dm_weather") if isinstance(source, dict) else None
        if not isinstance(raw, dict) or not raw.get("active"):
            return {"active": False}
        return {
            "active": True,
            "summary": str(raw.get("summary") or "").strip(),
            "ranged_attack": int(raw.get("ranged_attack", 0) or 0),
            "ranged_attack_impossible": bool(raw.get("ranged_attack_impossible", False)),
            "melee_attack": int(raw.get("melee_attack", 0) or 0),
            "spot": int(raw.get("spot", 0) or 0),
            "search": int(raw.get("search", 0) or 0),
            "listen": int(raw.get("listen", 0) or 0),
        }

    @staticmethod
    def _normalize_survival_days(source):
        base = {key: 0 for key in SURVIVAL_DAY_KEYS}
        raw = source.get("survival_days") if isinstance(source, dict) else None
        if not isinstance(raw, dict):
            return base
        merged = dict(base)
        for key in SURVIVAL_DAY_KEYS:
            try:
                merged[key] = max(0, int(raw.get(key, 0) or 0))
            except (TypeError, ValueError):
                merged[key] = 0
        return merged

    @staticmethod
    def _normalize_dm_pending_nonlethal(source):
        if not isinstance(source, dict):
            return 0
        raw = source.get("dm_pending_nonlethal", source.get("pending_nonlethal", 0))
        try:
            return max(0, int(raw or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_forced_rest(source):
        if not isinstance(source, dict):
            return {"token": 0, "at": ""}
        raw = source.get("forced_rest")
        if not isinstance(raw, dict):
            raw = source.get("dm_forced_rest")
        if not isinstance(raw, dict):
            return {"token": 0, "at": ""}
        try:
            token = max(0, int(raw.get("token", 0) or 0))
        except (TypeError, ValueError):
            token = 0
        return {"token": token, "at": str(raw.get("at") or "").strip()}

    @staticmethod
    def _normalize_dm_xp_award(source):
        if not isinstance(source, dict):
            return {"token": 0, "amount": 0, "at": ""}
        raw = source.get("dm_xp_award")
        if not isinstance(raw, dict):
            return {"token": 0, "amount": 0, "at": ""}
        try:
            token = max(0, int(raw.get("token", 0) or 0))
            amount = int(raw.get("amount", 0) or 0)
        except (TypeError, ValueError):
            token = 0
            amount = 0
        return {
            "token": token,
            "amount": amount,
            "at": str(raw.get("at") or "").strip(),
        }

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
            "dm_weather": CloudSyncManager._normalize_dm_weather(source),
            "survival_days": CloudSyncManager._normalize_survival_days(source),
            "forced_rest": CloudSyncManager._normalize_forced_rest(source),
            "pending_nonlethal": CloudSyncManager._normalize_dm_pending_nonlethal(source),
            "dm_xp_award": CloudSyncManager._normalize_dm_xp_award(source),
        }

    @classmethod
    def dm_status_signature(cls, data):
        status = cls.normalize_dm_status(data)
        weather = status.get("dm_weather") or {"active": False}
        weather_sig = (
            weather.get("active"),
            weather.get("summary"),
            weather.get("ranged_attack"),
            weather.get("ranged_attack_impossible"),
            weather.get("melee_attack"),
            weather.get("spot"),
            weather.get("search"),
            weather.get("listen"),
        )
        survival = status.get("survival_days") or {}
        survival_sig = tuple(
            (key, int(survival.get(key, 0) or 0))
            for key in SURVIVAL_DAY_KEYS
        )
        forced = status.get("forced_rest") or {}
        forced_sig = (
            int(forced.get("token", 0) or 0),
            str(forced.get("at") or ""),
        )
        award = status.get("dm_xp_award") or {}
        award_sig = (
            int(award.get("token", 0) or 0),
            int(award.get("amount", 0) or 0),
            str(award.get("at") or ""),
        )
        return (
            tuple(sorted(status["afflictions"].items())),
            status["negative_levels"],
            tuple(status["ability_damage"].items()),
            weather_sig,
            survival_sig,
            forced_sig,
            int(status.get("pending_nonlethal", 0) or 0),
            award_sig,
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

    def get_dm_status_poll_interval_sec(self):
        """Poll interval for DM-controlled fields (afflictions, weather, etc.)."""
        raw = (
            self.config.get("poll_interval_sec")
            or self.config.get("dm_status_poll_interval_sec")
            or DEFAULT_DM_STATUS_POLL_INTERVAL_SEC
        )
        base = max(3, int(raw or DEFAULT_DM_STATUS_POLL_INTERVAL_SEC))
        return int(
            apply_focus_multiplier(
                base,
                multiplier=getattr(self, "_focus_interval_multiplier", 1),
                max_sec=FOCUS_SLOW_POLL_MAX_SEC,
            )
        )

    def _dm_status_poll_loop(self):
        interval = self.get_dm_status_poll_interval_sec()
        while not self._dm_status_stop_event.is_set():
            try:
                remote = self.fetch_dm_status()
                if remote and not remote.get("unchanged"):
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