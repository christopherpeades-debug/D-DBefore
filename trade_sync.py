"""Supabase REST sync for pending player-to-player and DM item trades."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

TRADE_TABLE = "campaign_pending_trades"
DM_CHARACTER_ID = "__dm__"
DEFAULT_POLL_INTERVAL_SEC = 2
DEFAULT_FETCH_LIMIT = 50

_TRADE_SELECT = (
    "id,campaign_id,from_character_id,from_player_name,from_character_name,"
    "to_character_id,to_player_name,to_character_name,item,quantity,status,"
    "claimed_by_character_id,claimed_at,created_at,updated_at"
)


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def format_trade_timestamp(value):
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


def format_coins_trade_label(coins):
    """Human-readable label for a coin payout dict (PP/GP/EP/SP/CP)."""
    if not isinstance(coins, dict):
        return "Coins"
    parts = []
    for coin in ("PP", "GP", "EP", "SP", "CP"):
        try:
            count = int(coins.get(coin, 0) or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            parts.append(f"{count:,} {coin}")
    return ", ".join(parts) if parts else "Coins"


def format_trade_item_label(item, quantity=1):
    if not item:
        return "Item"
    if isinstance(item, str):
        name = item.strip()
    else:
        if str(item.get("type", "") or "").strip().lower() == "coins":
            return format_coins_trade_label(item.get("coins") or {})
        name = str(item.get("name", "") or "").strip()
    try:
        qty = max(1, int(quantity or 1))
    except (TypeError, ValueError):
        qty = 1
    if not name:
        return "Item"
    if qty > 1:
        return f"{name} (x{qty})"
    return name


def format_trade_log_line(entry):
    """Human-readable one-line summary for a pending trade row."""
    if not entry:
        return ""
    ts = format_trade_timestamp(entry.get("created_at"))
    from_id = str(entry.get("from_character_id") or "").strip()
    from_player = str(entry.get("from_player_name") or "").strip()
    from_char = str(entry.get("from_character_name") or "").strip()
    to_player = str(entry.get("to_player_name") or "").strip()
    to_char = str(entry.get("to_character_name") or "").strip()
    if from_id == DM_CHARACTER_ID:
        sender = "DM (Treasure Horde)"
    elif from_player and from_char:
        sender = f"{from_player} ({from_char})"
    else:
        sender = from_player or from_char or "Someone"
    if to_player and to_char:
        receiver = f"{to_player} ({to_char})"
    else:
        receiver = to_player or to_char or "someone"
    item = entry.get("item") or {}
    label = format_trade_item_label(item, entry.get("quantity", 1))
    prefix = f"[{ts}] " if ts else ""
    return f"{prefix}{sender} offered {label} to {receiver}"


def normalize_trade_row(row):
    if not isinstance(row, dict):
        return {}
    item = row.get("item") or {}
    if isinstance(item, str):
        try:
            item = json.loads(item)
        except (TypeError, ValueError, json.JSONDecodeError):
            item = {"name": item}
    if not isinstance(item, dict):
        item = {}
    try:
        qty = max(1, int(row.get("quantity", 1) or 1))
    except (TypeError, ValueError):
        qty = 1
    return {
        "id": str(row.get("id") or ""),
        "campaign_id": str(row.get("campaign_id") or ""),
        "from_character_id": str(row.get("from_character_id") or ""),
        "from_player_name": str(row.get("from_player_name") or ""),
        "from_character_name": str(row.get("from_character_name") or ""),
        "to_character_id": str(row.get("to_character_id") or ""),
        "to_player_name": str(row.get("to_player_name") or ""),
        "to_character_name": str(row.get("to_character_name") or ""),
        "item": item,
        "quantity": qty,
        "status": str(row.get("status") or "pending"),
        "claimed_by_character_id": str(row.get("claimed_by_character_id") or ""),
        "claimed_at": row.get("claimed_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def trades_signature(entries):
    return tuple(
        (
            str(row.get("id") or ""),
            str(row.get("status") or ""),
            str(row.get("updated_at") or ""),
            str(row.get("claimed_by_character_id") or ""),
        )
        for row in (entries or [])
    )


class TradeSyncClient:
    """Create, list, claim, and cancel pending trades via Supabase REST."""

    def __init__(self, config_path, on_remote_update=None, on_status=None):
        self.config_path = config_path
        self.on_remote_update = on_remote_update
        self.on_status = on_status
        self.config = {}
        self._stop_event = threading.Event()
        self._thread = None
        self._entries = []
        self._entries_signature = None
        self._dm_poll_mode = False

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

    def is_dm_configured(self):
        self.load_config()
        return bool(
            self.config.get("enabled")
            and self.config.get("supabase_url")
            and self.config.get("supabase_anon_key")
            and self.config.get("campaign_id")
        )

    def is_configured(self):
        self.load_config()
        return bool(
            self.is_dm_configured()
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
                    "The campaign_pending_trades table is missing in Supabase.\n\n"
                    "Open Supabase → SQL Editor → New query, paste and run "
                    "supabase_trade_setup.sql, then retry."
                ) from exc
            raise RuntimeError(f"Trade sync HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Trade sync network error: {exc.reason}") from exc

    def _fetch_pending(self, extra_filter="", limit=DEFAULT_FETCH_LIMIT):
        if not self.is_dm_configured():
            return []
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        lim = max(1, min(int(limit or DEFAULT_FETCH_LIMIT), 100))
        path = (
            f"/rest/v1/{TRADE_TABLE}?campaign_id=eq.{campaign_id}"
            "&status=eq.pending"
            f"{extra_filter}"
            f"&select={_TRADE_SELECT}"
            f"&order=created_at.desc&limit={lim}"
        )
        rows = self._request("GET", path) or []
        normalized = [normalize_trade_row(row) for row in rows]
        self._entries = normalized
        self._entries_signature = trades_signature(normalized)
        return list(normalized)

    def fetch_pending_trades(self, character_id=None, limit=DEFAULT_FETCH_LIMIT):
        if not self.is_configured():
            return []
        char_id = urllib.parse.quote(
            str(character_id or self.config.get("character_id") or "").strip(),
            safe="",
        )
        if not char_id:
            return []
        return self._fetch_pending(
            extra_filter=f"&or=(from_character_id.eq.{char_id},to_character_id.eq.{char_id})",
            limit=limit,
        )

    def fetch_dm_pending_trades(self, limit=DEFAULT_FETCH_LIMIT):
        dm_id = urllib.parse.quote(DM_CHARACTER_ID, safe="")
        return self._fetch_pending(
            extra_filter=f"&from_character_id=eq.{dm_id}",
            limit=limit,
        )

    def create_pending_trade(
        self,
        *,
        to_character_id,
        item,
        quantity=1,
        to_player_name="",
        to_character_name="",
        from_character_id=None,
        from_player_name=None,
        from_character_name=None,
    ):
        to_id = str(to_character_id or "").strip()
        if not to_id:
            raise RuntimeError("Trade recipient is required.")
        from_id = str(
            from_character_id or self.config.get("character_id") or "",
        ).strip()
        if not from_id:
            raise RuntimeError("Sender character ID is required.")
        if from_id == to_id:
            raise RuntimeError("You cannot trade with yourself.")
        is_dm = from_id == DM_CHARACTER_ID
        if is_dm:
            if not self.is_dm_configured():
                raise RuntimeError("Trade sync is not configured.")
        elif not self.is_configured():
            raise RuntimeError("Trade sync is not configured.")

        if not isinstance(item, dict):
            item = {"name": str(item or "Item")}
        try:
            qty = max(1, int(quantity or 1))
        except (TypeError, ValueError):
            qty = 1

        payload = {
            "campaign_id": self.config["campaign_id"],
            "from_character_id": from_id,
            "from_player_name": str(
                from_player_name if from_player_name is not None
                else ("" if is_dm else self.config.get("player_name", "") or ""),
            ),
            "from_character_name": str(
                from_character_name or ("Treasure Horde" if is_dm else ""),
            ),
            "to_character_id": to_id,
            "to_player_name": str(to_player_name or ""),
            "to_character_name": str(to_character_name or ""),
            "item": item,
            "quantity": qty,
            "status": "pending",
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
        path = f"/rest/v1/{TRADE_TABLE}"
        result = self._request(
            "POST", path, body=payload, prefer="return=representation",
        )
        if isinstance(result, list) and result:
            return normalize_trade_row(result[0])
        if isinstance(result, dict):
            return normalize_trade_row(result)
        raise RuntimeError("Trade server did not return the new pending trade.")

    def claim_trade(self, trade_id, character_id=None):
        if not self.is_configured():
            raise RuntimeError("Trade sync is not configured.")
        trade_uuid = str(trade_id or "").strip()
        if not trade_uuid:
            raise RuntimeError("Trade ID is required.")
        char_id = str(
            character_id or self.config.get("character_id") or "",
        ).strip()
        if not char_id:
            raise RuntimeError("Your character ID is not configured.")

        trade_id_q = urllib.parse.quote(trade_uuid, safe="")
        path = f"/rest/v1/{TRADE_TABLE}?id=eq.{trade_id_q}&status=eq.pending"
        body = {
            "status": "claimed",
            "claimed_by_character_id": char_id,
            "claimed_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
        result = self._request(
            "PATCH", path, body=body, prefer="return=representation",
        )
        if not result:
            raise RuntimeError(
                "This trade was already claimed or is no longer available.",
            )
        row = normalize_trade_row(result[0] if isinstance(result, list) else result)
        from_id = row.get("from_character_id", "")
        to_id = row.get("to_character_id", "")
        if from_id == DM_CHARACTER_ID:
            if char_id != to_id:
                raise RuntimeError("Only the recipient can claim a DM handout.")
        elif char_id not in (from_id, to_id):
            raise RuntimeError("You are not part of this trade.")
        return row

    def cancel_trade(self, trade_id):
        if not self.is_dm_configured():
            raise RuntimeError("Trade sync is not configured.")
        trade_uuid = str(trade_id or "").strip()
        if not trade_uuid:
            raise RuntimeError("Trade ID is required.")
        trade_id_q = urllib.parse.quote(trade_uuid, safe="")
        path = f"/rest/v1/{TRADE_TABLE}?id=eq.{trade_id_q}&status=eq.pending"
        body = {
            "status": "cancelled",
            "updated_at": _utc_now_iso(),
        }
        result = self._request(
            "PATCH", path, body=body, prefer="return=representation",
        )
        if not result:
            raise RuntimeError(
                "This trade was already resolved or is no longer available.",
            )
        return normalize_trade_row(result[0] if isinstance(result, list) else result)

    def start_polling(self, *, dm_mode=False):
        self.stop_polling()
        self._dm_poll_mode = bool(dm_mode)
        if self._dm_poll_mode:
            if not self.is_dm_configured():
                return
        elif not self.is_configured():
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
            int(
                self.config.get("trade_poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC)
                or DEFAULT_POLL_INTERVAL_SEC
            ),
        )
        while not self._stop_event.is_set():
            try:
                if self._dm_poll_mode:
                    rows = self.fetch_dm_pending_trades()
                else:
                    rows = self.fetch_pending_trades()
                signature = trades_signature(rows)
                if signature != getattr(self, "_last_polled_signature", None):
                    self._last_polled_signature = signature
                    self._invoke_callback(self.on_remote_update, list(rows))
            except Exception as exc:
                self._set_status(str(exc), is_error=True)
            self._stop_event.wait(interval)