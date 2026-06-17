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

ROLL_LOG_TABLE = "campaign_dice_rolls"
DEFAULT_POLL_INTERVAL_SEC = 2
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


def format_roll_log_line(entry):
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
    detail = f"{label}: {formula}" if formula else label
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
                    "The campaign_dice_rolls table is missing in Supabase.\n\n"
                    "Open Supabase → SQL Editor → New query, paste and run "
                    "supabase_roll_log_setup.sql (in your D&D Behind folder), then retry."
                ) from exc
            raise RuntimeError(f"Roll log HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Roll log network error: {exc.reason}") from exc

    def _signature_for_entries(self, entries):
        return tuple(
            (
                str(row.get("id") or ""),
                str(row.get("created_at") or ""),
                str(row.get("roll_result") or ""),
            )
            for row in (entries or [])
        )

    def fetch_roll_log(self, limit=DEFAULT_FETCH_LIMIT):
        if not self.is_configured():
            return []
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        lim = max(1, min(int(limit or DEFAULT_FETCH_LIMIT), 200))
        path = (
            f"/rest/v1/{ROLL_LOG_TABLE}?campaign_id=eq.{campaign_id}"
            "&select=id,campaign_id,character_id,player_name,character_name,"
            "roll_label,roll_formula,roll_result,roll_detail,created_at"
            f"&order=created_at.desc&limit={lim}"
        )
        rows = self._request("GET", path) or []
        self._entries = list(rows)
        self._entries_signature = self._signature_for_entries(rows)
        return list(rows)

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
            return result[0]
        return result

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
            int(self.config.get("roll_log_poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC) or DEFAULT_POLL_INTERVAL_SEC),
        )
        while not self._stop_event.is_set():
            try:
                rows = self.fetch_roll_log()
                signature = self._signature_for_entries(rows)
                if signature != getattr(self, "_last_polled_signature", None):
                    self._last_polled_signature = signature
                    self._invoke_callback(self.on_remote_update, list(rows))
            except Exception as exc:
                self._set_status(str(exc), is_error=True)
            self._stop_event.wait(interval)