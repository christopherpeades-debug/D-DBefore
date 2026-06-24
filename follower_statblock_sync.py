"""Supabase REST sync for DM-shared NPC statblocks to player character sheets."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FOLLOWER_TABLE = "campaign_shared_followers"
DEFAULT_POLL_INTERVAL_SEC = 20
DEFAULT_FETCH_LIMIT = 40
SUMMARY_SELECT = "id,created_at,follower_name,shared_by,source_id"
FULL_SELECT = (
    "id,campaign_id,character_id,follower_name,monster_json,"
    "view_data_json,shared_by,source_id,created_at"
)


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class FollowerStatblockSyncClient:
    """Post and poll shared follower statblocks per campaign character."""

    def __init__(self, config_path, on_remote_update=None, on_status=None):
        self.config_path = config_path
        self.on_remote_update = on_remote_update
        self.on_status = on_status
        self.config = {}
        self._stop_event = threading.Event()
        self._thread = None
        self._notified_ids = set()
        self._last_signature = None

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

    def is_player_configured(self):
        return self.is_configured() and bool(str(self.config.get("character_id") or "").strip())

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
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                if not raw.strip():
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and "PGRST205" in detail:
                raise RuntimeError(
                    "The campaign_shared_followers table is missing in Supabase.\n\n"
                    "Open Supabase → SQL Editor → New query, paste and run "
                    "supabase_follower_statblock_setup.sql, then retry."
                ) from exc
            raise RuntimeError(f"Follower statblock HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Follower statblock network error: {exc.reason}") from exc

    def get_seen_follower_ids(self):
        raw = self.config.get("seen_shared_follower_ids") or []
        if not isinstance(raw, list):
            return set()
        return {str(x).strip() for x in raw if str(x).strip()}

    def mark_followers_seen(self, follower_ids):
        ids = [str(x).strip() for x in (follower_ids or []) if str(x).strip()]
        if not ids:
            return
        seen = list(self.get_seen_follower_ids())
        seen_set = set(seen)
        changed = False
        for follower_id in ids:
            if follower_id not in seen_set:
                seen.append(follower_id)
                seen_set.add(follower_id)
                changed = True
        if not changed:
            return
        if len(seen) > 200:
            seen = seen[-200:]
        self.config["seen_shared_follower_ids"] = seen
        self.save_config(self.config)

    def mark_follower_seen(self, follower_id):
        if not follower_id:
            return
        self.mark_followers_seen([follower_id])

    def _character_list_path(self, *, select, character_id=None, limit=None, extra=""):
        if not self.is_player_configured() and not (self.is_configured() and character_id):
            return None
        cid = str(character_id or self.config.get("character_id") or "").strip()
        if not cid:
            return None
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        char_q = urllib.parse.quote(cid, safe="")
        path = (
            f"/rest/v1/{FOLLOWER_TABLE}?campaign_id=eq.{campaign_id}"
            f"&character_id=eq.{char_q}"
            f"&select={select}"
            f"{extra}"
        )
        if limit is not None:
            lim = max(1, min(int(limit or DEFAULT_FETCH_LIMIT), 100))
            path += f"&order=created_at.desc&limit={lim}"
        return path

    def fetch_follower_summaries_for_character(self, character_id=None, limit=DEFAULT_FETCH_LIMIT):
        path = self._character_list_path(
            select=SUMMARY_SELECT,
            character_id=character_id,
            limit=limit,
        )
        if not path:
            return []
        return list(self._request("GET", path) or [])

    def fetch_followers_by_ids(self, follower_ids, character_id=None):
        ids = [str(x).strip() for x in (follower_ids or []) if str(x).strip()]
        if not ids:
            return []
        cid = str(character_id or self.config.get("character_id") or "").strip()
        if not cid or not self.is_configured():
            return []
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        char_q = urllib.parse.quote(cid, safe="")
        id_filter = ",".join(ids)
        path = (
            f"/rest/v1/{FOLLOWER_TABLE}?campaign_id=eq.{campaign_id}"
            f"&character_id=eq.{char_q}"
            f"&id=in.({id_filter})"
            f"&select={FULL_SELECT}"
        )
        return list(self._request("GET", path) or [])

    def fetch_followers_for_character(self, character_id=None, limit=DEFAULT_FETCH_LIMIT):
        path = self._character_list_path(
            select=FULL_SELECT,
            character_id=character_id,
            limit=limit,
        )
        if not path:
            return []
        return list(self._request("GET", path) or [])

    def _signature_for_summaries(self, rows):
        return tuple(
            (str(row.get("id") or ""), str(row.get("created_at") or ""))
            for row in (rows or [])
        )

    def fetch_unseen_followers(self):
        if not self.is_player_configured():
            return []
        seen = self.get_seen_follower_ids()
        summaries = self.fetch_follower_summaries_for_character()
        unseen_ids = []
        for row in summaries:
            fid = str(row.get("id") or "").strip()
            if fid and fid not in seen:
                unseen_ids.append(fid)
        if not unseen_ids:
            return []
        full_rows = self.fetch_followers_by_ids(unseen_ids)
        full_by_id = {str(r.get("id") or "").strip(): r for r in full_rows}
        unseen = []
        for fid in reversed(unseen_ids):
            row = full_by_id.get(fid)
            if row:
                unseen.append(row)
        return unseen

    def delete_shared_follower(self, follower_id, character_id=None):
        follower_id = str(follower_id or "").strip()
        cid = str(character_id or self.config.get("character_id") or "").strip()
        if not follower_id or not cid or not self.is_configured():
            return 0
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        char_q = urllib.parse.quote(cid, safe="")
        fid_q = urllib.parse.quote(follower_id, safe="")
        path = (
            f"/rest/v1/{FOLLOWER_TABLE}?campaign_id=eq.{campaign_id}"
            f"&character_id=eq.{char_q}&id=eq.{fid_q}"
        )
        self._request("DELETE", path)
        return 1

    def delete_shared_followers(self, follower_ids, character_id=None):
        ids = [str(x).strip() for x in (follower_ids or []) if str(x).strip()]
        if not ids or not self.is_configured():
            return 0
        cid = str(character_id or self.config.get("character_id") or "").strip()
        if not cid:
            return 0
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        char_q = urllib.parse.quote(cid, safe="")
        id_filter = ",".join(ids)
        path = (
            f"/rest/v1/{FOLLOWER_TABLE}?campaign_id=eq.{campaign_id}"
            f"&character_id=eq.{char_q}&id=in.({id_filter})"
        )
        self._request("DELETE", path)
        return len(ids)

    def delete_shared_followers_by_source_id(self, character_id, source_id):
        source_id = str(source_id or "").strip()
        cid = str(character_id or self.config.get("character_id") or "").strip()
        if not source_id or not cid or not self.is_configured():
            return 0
        rows = self.fetch_follower_summaries_for_character(character_id=cid, limit=100)
        ids = [
            str(row.get("id") or "").strip()
            for row in rows
            if str(row.get("source_id") or "").strip() == source_id
        ]
        if not ids:
            return 0
        return self.delete_shared_followers(ids, character_id=cid)

    def post_shared_follower(
        self,
        *,
        character_id,
        follower_name,
        monster_json,
        view_data_json=None,
        shared_by="DM",
        source_id="",
    ):
        self.load_config()
        if not self.is_configured():
            raise RuntimeError("Cloud sync is not configured.")
        character_id = str(character_id or "").strip()
        follower_name = str(follower_name or "Follower").strip() or "Follower"
        if not character_id:
            raise RuntimeError("Character is required.")
        if not monster_json:
            raise RuntimeError("Statblock data is required.")
        payload = {
            "campaign_id": self.config["campaign_id"],
            "character_id": character_id,
            "follower_name": follower_name,
            "monster_json": monster_json,
            "view_data_json": view_data_json or {},
            "shared_by": str(shared_by or "DM").strip() or "DM",
            "source_id": str(source_id or "").strip(),
            "created_at": _utc_now_iso(),
        }
        path = f"/rest/v1/{FOLLOWER_TABLE}"
        result = self._request("POST", path, body=payload, prefer="return=representation")
        if isinstance(result, list) and result:
            return result[0]
        return result

    def start_polling(self):
        self.stop_polling()
        if not self.is_player_configured():
            return
        self._stop_event.clear()
        self._notified_ids = set()
        self._last_signature = None
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop_polling(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _get_poll_interval_sec(self):
        return max(
            10,
            int(
                self.config.get(
                    "follower_statblock_poll_interval_sec",
                    self.config.get("image_share_poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC),
                )
                or DEFAULT_POLL_INTERVAL_SEC
            ),
        )

    def _poll_loop(self):
        interval = self._get_poll_interval_sec()
        while not self._stop_event.is_set():
            try:
                summaries = self.fetch_follower_summaries_for_character()
                signature = self._signature_for_summaries(summaries)
                if signature == self._last_signature:
                    self._stop_event.wait(interval)
                    continue

                seen = self.get_seen_follower_ids()
                unseen_ids = []
                for row in summaries:
                    fid = str(row.get("id") or "").strip()
                    if fid and fid not in seen:
                        unseen_ids.append(fid)

                if not unseen_ids:
                    self._last_signature = signature
                    self._stop_event.wait(interval)
                    continue

                full_rows = self.fetch_followers_by_ids(unseen_ids)
                full_by_id = {str(r.get("id") or "").strip(): r for r in full_rows}
                unseen = []
                for fid in reversed(unseen_ids):
                    row = full_by_id.get(fid)
                    if row:
                        unseen.append(row)

                fresh = []
                for row in unseen:
                    fid = str(row.get("id") or "").strip()
                    if fid and fid not in self._notified_ids:
                        fresh.append(row)
                        self._notified_ids.add(fid)
                if fresh:
                    self._last_signature = signature
                    self._invoke_callback(self.on_remote_update, list(fresh))
                else:
                    self._last_signature = signature
            except Exception as exc:
                self._set_status(str(exc), is_error=True)
            self._stop_event.wait(interval)