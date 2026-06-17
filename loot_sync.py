"""Supabase REST sync for DM treasure hoards and player loot claims."""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

LOOT_TABLE = "campaign_loot"
DEFAULT_POLL_INTERVAL_SEC = 2
COIN_TYPES = ("PP", "GP", "EP", "SP", "CP")


def empty_coin_dict():
    return {coin: 0 for coin in COIN_TYPES}


def calculate_coin_share(shared_coins, party_member_count):
    """Each player's take from the shared pool (floor division)."""
    members = max(1, int(party_member_count or 1))
    shared = shared_coins or {}
    return {
        coin: int(shared.get(coin, 0) or 0) // members
        for coin in COIN_TYPES
    }


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def clamp_trade_multiplier(value, default=1.0):
    """Campaign-wide buy/sell price multiplier (0.5 = 50%, 1.0 = 100%, 2.0 = 200%)."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.5, min(2.0, parsed))


def default_loot_state():
    return {
        "ready_to_loot": False,
        "party_member_count": 4,
        "loot_push_id": 0,
        "buy_multiplier": 1.0,
        "sell_multiplier": 1.0,
        "coins_claimed_by": [],
        "shared_coins": empty_coin_dict(),
        "character_coins": {},
        "items": [],
        "updated_at": _utc_now_iso(),
    }


def normalize_loot_state(data):
    base = default_loot_state()
    if not isinstance(data, dict):
        return base
    merged = copy.deepcopy(base)
    merged["ready_to_loot"] = bool(data.get("ready_to_loot", False))
    try:
        merged["party_member_count"] = max(1, int(data.get("party_member_count", 4) or 4))
    except (TypeError, ValueError):
        merged["party_member_count"] = 4
    for coin in COIN_TYPES:
        merged["shared_coins"][coin] = int((data.get("shared_coins") or {}).get(coin, 0) or 0)
    merged["character_coins"] = copy.deepcopy(data.get("character_coins") or {})
    try:
        merged["loot_push_id"] = max(0, int(data.get("loot_push_id", 0) or 0))
    except (TypeError, ValueError):
        merged["loot_push_id"] = 0
    claimed = data.get("coins_claimed_by") or []
    merged["coins_claimed_by"] = [str(char_id) for char_id in claimed if str(char_id).strip()]
    merged["items"] = copy.deepcopy(data.get("items") or [])
    merged["buy_multiplier"] = clamp_trade_multiplier(data.get("buy_multiplier", 1.0))
    merged["sell_multiplier"] = clamp_trade_multiplier(data.get("sell_multiplier", 1.0))
    merged["updated_at"] = data.get("updated_at") or _utc_now_iso()
    return merged


def loot_state_fingerprint(state):
    """Stable signature for detecting remote hoard changes between polls."""
    normalized = normalize_loot_state(state)
    item_sig = tuple(
        (str(item.get("id", "")), str(item.get("claimed_by") or ""))
        for item in (normalized.get("items") or [])
    )
    coin_sig = tuple(
        (coin, int((normalized.get("shared_coins") or {}).get(coin, 0) or 0))
        for coin in COIN_TYPES
    )
    claimed_sig = tuple(sorted(str(c) for c in (normalized.get("coins_claimed_by") or [])))
    return (
        str(normalized.get("updated_at") or ""),
        item_sig,
        coin_sig,
        claimed_sig,
        bool(normalized.get("ready_to_loot")),
        int(normalized.get("loot_push_id", 0) or 0),
        float(normalized.get("buy_multiplier", 1.0) or 1.0),
        float(normalized.get("sell_multiplier", 1.0) or 1.0),
    )


def player_visible_name(item):
    if not item:
        return ""
    if item.get("identified") or not item.get("is_magical"):
        return item.get("name") or item.get("generic_name") or "Item"
    return item.get("generic_name") or item.get("flavor") or "Unidentified item"


class LootSyncClient:
    """Read/write campaign loot state via Supabase REST."""

    def __init__(self, config_path, on_remote_update=None, on_status=None):
        self.config_path = config_path
        self.on_remote_update = on_remote_update
        self.on_status = on_status
        self.config = {}
        self._stop_event = threading.Event()
        self._thread = None
        self._last_seen_at = None
        self._last_seen_fingerprint = None

    def note_remote_state(self, state):
        """Record the latest known cloud state so polling only reacts to real changes."""
        if not state:
            return
        self._last_seen_fingerprint = loot_state_fingerprint(state)
        remote_at = state.get("updated_at")
        if remote_at:
            self._last_seen_at = remote_at

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
        if not base:
            raise RuntimeError("Supabase URL is not configured.")
        url = f"{base}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, headers=self._headers(prefer=prefer), method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
                if not raw.strip():
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and "PGRST205" in detail:
                raise RuntimeError(
                    "The campaign_loot table is missing in Supabase.\n\n"
                    "Open Supabase → SQL Editor → New query, paste and run "
                    "supabase_loot_setup.sql (in your D&D Behind folder), then retry."
                ) from exc
            raise RuntimeError(f"Loot sync HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Loot sync network error: {exc.reason}") from exc

    def test_connection(self):
        if not self.is_configured():
            raise RuntimeError("Loot sync is not fully configured.")
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = f"/rest/v1/{LOOT_TABLE}?campaign_id=eq.{campaign_id}&select=campaign_id&limit=1"
        self._request("GET", path)
        self._set_status("Connected to loot cloud")
        return True

    def fetch_loot_state(self):
        if not self.is_configured():
            return None
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = (
            f"/rest/v1/{LOOT_TABLE}?campaign_id=eq.{campaign_id}"
            "&select=data,updated_at&limit=1"
        )
        rows = self._request("GET", path) or []
        if not rows:
            return normalize_loot_state({})
        row = rows[0]
        state = normalize_loot_state(row.get("data") or {})
        state["updated_at"] = row.get("updated_at") or state.get("updated_at")
        return state

    def upsert_loot_state(self, loot_state):
        if not self.is_configured():
            return False
        state = normalize_loot_state(loot_state)
        state["updated_at"] = _utc_now_iso()
        payload = {
            "campaign_id": self.config["campaign_id"],
            "data": state,
            "updated_at": _utc_now_iso(),
        }
        path = f"/rest/v1/{LOOT_TABLE}?on_conflict=campaign_id"
        result = self._request(
            "POST", path, body=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        if isinstance(result, list) and result:
            remote_at = result[0].get("updated_at")
            if remote_at:
                state["updated_at"] = remote_at
        self.note_remote_state(state)
        self._set_status("Loot pushed to cloud")
        return state

    def list_campaign_characters(self):
        if not self.is_configured():
            return []
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        path = (
            "/rest/v1/campaign_characters"
            f"?campaign_id=eq.{campaign_id}"
            "&select=character_id,player_name,character_name"
            "&order=player_name.asc"
        )
        return self._request("GET", path) or []

    def claim_character_coins(self, character_id):
        state = self.fetch_loot_state()
        if not state:
            raise RuntimeError("No loot state in cloud.")
        char_id = str(character_id or "").strip()
        if not char_id:
            raise RuntimeError("Character ID is not configured.")
        claimed = [str(cid) for cid in (state.get("coins_claimed_by") or [])]
        if char_id in claimed:
            raise RuntimeError(
                "You already took your coin share. Wait for the DM to push a new hoard."
            )
        party_count = max(1, int(state.get("party_member_count", 1) or 1))
        payout = calculate_coin_share(state.get("shared_coins"), party_count)
        if not any(int(payout.get(c, 0) or 0) for c in COIN_TYPES):
            raise RuntimeError("No coins available to loot.")
        shared = state.setdefault("shared_coins", empty_coin_dict())
        for coin in COIN_TYPES:
            shared[coin] = max(0, int(shared.get(coin, 0) or 0) - int(payout.get(coin, 0) or 0))
        claimed.append(char_id)
        state["coins_claimed_by"] = claimed
        self.upsert_loot_state(state)
        return payout

    def claim_item(self, item_id, character_id):
        state = self.fetch_loot_state()
        if not state:
            raise RuntimeError("No loot state in cloud.")
        items = state.get("items") or []
        found = None
        remaining = []
        for item in items:
            if item.get("id") == item_id:
                found = item
            else:
                remaining.append(item)
        if not found:
            raise RuntimeError("Item not found in hoard.")
        if found.get("claimed_by"):
            raise RuntimeError("Item already claimed.")
        found = copy.deepcopy(found)
        found["claimed_by"] = character_id
        state["items"] = remaining
        self.upsert_loot_state(state)
        return found

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
        interval = max(
            2,
            int(self.config.get("loot_poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC) or DEFAULT_POLL_INTERVAL_SEC),
        )
        while not self._stop_event.is_set():
            try:
                remote = self.fetch_loot_state()
                if remote:
                    fingerprint = loot_state_fingerprint(remote)
                    if fingerprint != self._last_seen_fingerprint:
                        self.note_remote_state(remote)
                        self._invoke_callback(self.on_remote_update, remote)
            except Exception as exc:
                self._set_status(str(exc), is_error=True)
            self._stop_event.wait(interval)