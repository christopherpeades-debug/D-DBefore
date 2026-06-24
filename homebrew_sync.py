"""Supabase REST sync for DM campaign homebrew features."""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

from sync_http import supabase_request
from sync_intervals import FOCUS_SLOW_POLL_MAX_SEC, apply_focus_multiplier

HOMEBREW_TABLE = "campaign_homebrew"
DEFAULT_POLL_INTERVAL_SEC = 6


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _new_feature_id():
    return str(uuid.uuid4())


def default_homebrew_state():
    return {
        "features": [],
        "updated_at": _utc_now_iso(),
    }


def normalize_feature(feature):
    base = {
        "id": _new_feature_id(),
        "name": "",
        "description": "",
        "granted_spell": "",
        "uses_per_day": 0,
        "per_day": 0,
        "max_charges": 0,
        "special_feature_key": "",
        "special_feature_id": "",
        "show_charges": False,
        "pushed": False,
    }
    if not isinstance(feature, dict):
        return base
    merged = copy.deepcopy(base)
    feat_id = str(feature.get("id") or "").strip()
    merged["id"] = feat_id or _new_feature_id()
    merged["name"] = str(feature.get("name") or "").strip()
    merged["description"] = str(feature.get("description") or "").strip()
    merged["granted_spell"] = str(feature.get("granted_spell") or "").strip()
    try:
        uses = max(0, int(feature.get("uses_per_day") or feature.get("per_day", 0) or 0))
    except (TypeError, ValueError):
        uses = 0
    merged["uses_per_day"] = uses
    merged["per_day"] = uses
    try:
        merged["max_charges"] = max(0, int(feature.get("max_charges", 0) or 0))
    except (TypeError, ValueError):
        merged["max_charges"] = 0
    merged["special_feature_key"] = str(feature.get("special_feature_key") or "").strip()
    merged["special_feature_id"] = str(feature.get("special_feature_id") or "").strip()
    merged["show_charges"] = bool(feature.get("show_charges")) or merged["max_charges"] > 0
    merged["pushed"] = bool(feature.get("pushed"))
    return merged


def normalize_homebrew_state(data):
    base = default_homebrew_state()
    if not isinstance(data, dict):
        return base
    merged = copy.deepcopy(base)
    features = []
    for raw in data.get("features") or []:
        features.append(normalize_feature(raw))
    merged["features"] = features
    merged["updated_at"] = data.get("updated_at") or _utc_now_iso()
    return merged


def pushed_features(state):
    """Return only features the DM has toggled to share with the campaign."""
    normalized = normalize_homebrew_state(state)
    return [f for f in normalized.get("features") or [] if f.get("pushed")]


def homebrew_state_fingerprint(state):
    normalized = normalize_homebrew_state(state)
    sig = tuple(
        (
            str(f.get("id", "")),
            str(f.get("name", "")),
            str(f.get("description", "")),
            str(f.get("granted_spell", "")),
            int(f.get("uses_per_day", 0) or 0),
            int(f.get("max_charges", 0) or 0),
            str(f.get("special_feature_key", "")),
            str(f.get("special_feature_id", "")),
            bool(f.get("pushed")),
        )
        for f in (normalized.get("features") or [])
    )
    return (str(normalized.get("updated_at") or ""), sig)


class HomebrewSyncClient:
    """Read/write campaign homebrew state via Supabase REST."""

    def __init__(self, config_path, on_remote_update=None, on_status=None):
        self.config_path = config_path
        self.on_remote_update = on_remote_update
        self.on_status = on_status
        self.config = {}
        self._stop_event = threading.Event()
        self._thread = None
        self._last_seen_fingerprint = None
        self._last_seen_updated_at = None
        self._focus_interval_multiplier = 1

    def note_remote_state(self, state):
        if not state:
            return
        self._last_seen_fingerprint = homebrew_state_fingerprint(state)
        remote_at = state.get("updated_at")
        if remote_at:
            self._last_seen_updated_at = remote_at

    def set_focus_multiplier(self, multiplier):
        try:
            self._focus_interval_multiplier = max(1, min(8, int(multiplier or 1)))
        except (TypeError, ValueError):
            self._focus_interval_multiplier = 1

    def _get_poll_interval_sec(self):
        try:
            base = int(
                self.config.get("homebrew_poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC)
                or DEFAULT_POLL_INTERVAL_SEC
            )
        except (TypeError, ValueError):
            base = DEFAULT_POLL_INTERVAL_SEC
        return apply_focus_multiplier(
            max(2, base),
            multiplier=self._focus_interval_multiplier,
            max_sec=FOCUS_SLOW_POLL_MAX_SEC,
        )

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
                    "The campaign_homebrew table is missing in Supabase.\n\n"
                    "Open Supabase → SQL Editor → New query, paste and run "
                    "supabase_homebrew_setup.sql, then retry."
                ) from exc
            raise RuntimeError(f"Homebrew sync HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Homebrew sync network error: {exc.reason}") from exc

    def fetch_homebrew_revision(self):
        if not self.is_configured():
            return None
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = (
            f"/rest/v1/{HOMEBREW_TABLE}?campaign_id=eq.{campaign_id}"
            "&select=updated_at&limit=1"
        )
        rows = self._request("GET", path) or []
        if not rows:
            return None
        return rows[0].get("updated_at")

    def poll_homebrew_updates(self):
        revision = self.fetch_homebrew_revision()
        if revision and self._last_seen_updated_at and revision == self._last_seen_updated_at:
            return None
        remote = self.fetch_homebrew_state()
        if not remote:
            return None
        fingerprint = homebrew_state_fingerprint(remote)
        if fingerprint == self._last_seen_fingerprint:
            self._last_seen_updated_at = remote.get("updated_at") or self._last_seen_updated_at
            return None
        return remote

    def test_connection(self):
        if not self.is_configured():
            raise RuntimeError("Homebrew sync is not fully configured.")
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = f"/rest/v1/{HOMEBREW_TABLE}?campaign_id=eq.{campaign_id}&select=campaign_id&limit=1"
        self._request("GET", path)
        self._set_status("Connected to homebrew cloud")
        return True

    def fetch_homebrew_state(self):
        if not self.is_configured():
            return None
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = (
            f"/rest/v1/{HOMEBREW_TABLE}?campaign_id=eq.{campaign_id}"
            "&select=data,updated_at&limit=1"
        )
        rows = self._request("GET", path) or []
        if not rows:
            return normalize_homebrew_state({})
        row = rows[0]
        state = normalize_homebrew_state(row.get("data") or {})
        state["updated_at"] = row.get("updated_at") or state.get("updated_at")
        return state

    def upsert_homebrew_state(self, homebrew_state):
        if not self.is_configured():
            return False
        state = normalize_homebrew_state(homebrew_state)
        state["updated_at"] = _utc_now_iso()
        payload = {
            "campaign_id": self.config["campaign_id"],
            "data": state,
            "updated_at": _utc_now_iso(),
        }
        path = f"/rest/v1/{HOMEBREW_TABLE}?on_conflict=campaign_id"
        result = self._request(
            "POST", path, body=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        if isinstance(result, list) and result:
            remote_at = result[0].get("updated_at")
            if remote_at:
                state["updated_at"] = remote_at
        self.note_remote_state(state)
        self._set_status("Homebrew pushed to cloud")
        return state

    def start_polling(self, interval_sec=None):
        self.stop_polling()
        if not self.is_configured():
            return
        self._poll_interval = max(2, int(interval_sec or DEFAULT_POLL_INTERVAL_SEC))
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
                remote = self.poll_homebrew_updates()
                if remote:
                    self.note_remote_state(remote)
                    self._invoke_callback(self.on_remote_update, remote)
            except Exception:
                pass
            interval = self._get_poll_interval_sec()
            if getattr(self, "_poll_interval", None):
                try:
                    interval = max(interval, int(self._poll_interval))
                except (TypeError, ValueError):
                    pass
            self._stop_event.wait(interval)