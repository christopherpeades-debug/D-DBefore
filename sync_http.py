"""Shared HTTP helpers for Supabase REST sync clients."""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request


def decode_response_body(response):
    raw = response.read()
    if response.headers.get("Content-Encoding", "").lower() == "gzip":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")


def supabase_request(base_url, method, path, headers, *, body=None, timeout=20):
    """Issue a Supabase REST request with gzip support."""
    base = str(base_url or "").rstrip("/")
    if not base:
        raise RuntimeError("Supabase URL is not configured.")
    url = f"{base}{path}"
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
    req_headers = dict(headers or {})
    req_headers.setdefault("Accept-Encoding", "gzip")
    request = urllib.request.Request(
        url,
        data=payload,
        headers=req_headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = decode_response_body(response)
        if not text.strip():
            return None
        return json.loads(text)