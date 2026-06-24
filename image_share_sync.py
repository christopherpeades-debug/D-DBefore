"""Supabase REST sync for DM-shared session card images to player character sheets."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from sync_http import supabase_request
from datetime import datetime, timedelta, timezone
from io import BytesIO

IMAGE_SHARE_TABLE = "campaign_shared_images"
DEFAULT_POLL_INTERVAL_SEC = 5
DEFAULT_FETCH_LIMIT = 40
DEFAULT_PLAYER_IMAGE_MAX_AGE_SEC = 300


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_utc_datetime(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _utc_iso_for_query(dt):
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    iso = dt.astimezone(timezone.utc).isoformat()
    if iso.endswith("+00:00"):
        iso = iso[:-6] + "Z"
    return iso


def _row_within_max_age(row, max_age_seconds, now=None):
    if max_age_seconds is None or max_age_seconds <= 0:
        return True
    created = _parse_utc_datetime(row.get("created_at"))
    if created is None:
        return False
    now = now or datetime.now(timezone.utc)
    return created >= now - timedelta(seconds=max_age_seconds)


class ImageShareSyncClient:
    """Post and poll shared image URLs per campaign character."""

    def __init__(self, config_path, on_remote_update=None, on_status=None):
        self.config_path = config_path
        self.on_remote_update = on_remote_update
        self.on_status = on_status
        self.config = {}
        self._stop_event = threading.Event()
        self._thread = None
        self._last_signature = None
        self._notified_image_ids = set()

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
        try:
            return supabase_request(
                base, method, path, self._headers(prefer=prefer), body=body,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and "PGRST205" in detail:
                raise RuntimeError(
                    "The campaign_shared_images table is missing in Supabase.\n\n"
                    "Open Supabase → SQL Editor → New query, paste and run "
                    "supabase_image_share_setup.sql, then retry."
                ) from exc
            raise RuntimeError(f"Image share HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Image share network error: {exc.reason}") from exc

    def get_seen_image_ids(self):
        raw = self.config.get("seen_shared_image_ids") or []
        if not isinstance(raw, list):
            return set()
        return {str(x).strip() for x in raw if str(x).strip()}

    def mark_image_seen(self, image_id):
        if not image_id:
            return
        seen = list(self.get_seen_image_ids())
        image_id = str(image_id).strip()
        if image_id not in seen:
            seen.append(image_id)
        if len(seen) > 200:
            seen = seen[-200:]
        self.config["seen_shared_image_ids"] = seen
        self.save_config(self.config)

    def post_shared_image(self, *, character_id, image_url, title="", card_id="", shared_by="DM"):
        self.load_config()
        if not self.is_configured():
            raise RuntimeError("Cloud sync is not configured.")
        character_id = str(character_id or "").strip()
        image_url = str(image_url or "").strip()
        if not character_id or not image_url:
            raise RuntimeError("Character and image URL are required.")
        payload = {
            "campaign_id": self.config["campaign_id"],
            "character_id": character_id,
            "image_url": image_url,
            "title": str(title or "").strip(),
            "card_id": str(card_id or "").strip(),
            "shared_by": str(shared_by or "DM").strip() or "DM",
            "created_at": _utc_now_iso(),
        }
        path = f"/rest/v1/{IMAGE_SHARE_TABLE}"
        result = self._request("POST", path, body=payload, prefer="return=representation")
        if isinstance(result, list) and result:
            return result[0]
        return result

    def fetch_images_for_character(
        self, character_id=None, limit=DEFAULT_FETCH_LIMIT, created_after=None,
    ):
        if not self.is_player_configured() and not (self.is_configured() and character_id):
            return []
        cid = str(character_id or self.config.get("character_id") or "").strip()
        if not cid:
            return []
        campaign_id = urllib.parse.quote(str(self.config["campaign_id"]), safe="")
        char_q = urllib.parse.quote(cid, safe="")
        lim = max(1, min(int(limit or DEFAULT_FETCH_LIMIT), 100))
        path = (
            f"/rest/v1/{IMAGE_SHARE_TABLE}?campaign_id=eq.{campaign_id}"
            f"&character_id=eq.{char_q}"
            "&select=id,campaign_id,character_id,image_url,title,card_id,shared_by,created_at"
            f"&order=created_at.desc&limit={lim}"
        )
        if created_after is not None:
            if isinstance(created_after, datetime):
                cutoff_dt = created_after
            else:
                cutoff_dt = _parse_utc_datetime(created_after)
            cutoff_iso = _utc_iso_for_query(cutoff_dt)
            if cutoff_iso:
                path += f"&created_at=gte.{urllib.parse.quote(cutoff_iso, safe='')}"
        return list(self._request("GET", path) or [])

    def fetch_unseen_images(self, max_age_seconds=DEFAULT_PLAYER_IMAGE_MAX_AGE_SEC):
        if not self.is_player_configured():
            return []
        seen = self.get_seen_image_ids()
        created_after = None
        if max_age_seconds and max_age_seconds > 0:
            created_after = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        rows = self.fetch_images_for_character(created_after=created_after)
        now = datetime.now(timezone.utc)
        unseen = []
        for row in rows:
            img_id = str(row.get("id") or "").strip()
            if not img_id or img_id in seen:
                continue
            if not _row_within_max_age(row, max_age_seconds, now=now):
                continue
            unseen.append(row)
        unseen.reverse()
        return unseen

    def _signature_for_rows(self, rows):
        return tuple(str(row.get("id") or "") for row in (rows or []))

    def start_polling(self):
        self.stop_polling()
        if not self.is_player_configured():
            return
        self._stop_event.clear()
        self._notified_image_ids = set()
        self._last_signature = None
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop_polling(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _poll_loop(self):
        interval = max(
            3,
            int(
                self.config.get(
                    "dm_status_poll_interval_sec",
                    self.config.get("image_share_poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC),
                )
                or DEFAULT_POLL_INTERVAL_SEC
            ),
        )
        while not self._stop_event.is_set():
            try:
                unseen = self.fetch_unseen_images()
                fresh = []
                for row in unseen:
                    img_id = str(row.get("id") or "").strip()
                    if img_id and img_id not in self._notified_image_ids:
                        fresh.append(row)
                        self._notified_image_ids.add(img_id)
                if fresh:
                    self._last_signature = self._signature_for_rows(unseen)
                    self._invoke_callback(self.on_remote_update, list(fresh))
                elif not unseen:
                    self._last_signature = None
            except Exception as exc:
                self._set_status(str(exc), is_error=True)
            self._stop_event.wait(interval)


def fetch_url_image_pil(image_url, max_size=(640, 480)):
    """Download image URL and return a PIL Image, or None on failure."""
    try:
        from PIL import Image
    except ImportError:
        return None
    url = str(image_url or "").strip()
    if not url:
        return None
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DnD-Image-Share/1.0)"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()
        img = Image.open(BytesIO(data))
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        return img.convert("RGBA") if img.mode not in ("RGB", "RGBA") else img
    except Exception:
        return None