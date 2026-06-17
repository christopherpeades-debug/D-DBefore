"""Check GitHub Releases and download/install newer app versions."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

VERSION_FILENAME = "version.json"
USER_AGENT = "DnD-Before-Updater"


def _parse_version_tuple(value):
    text = re.sub(r"^v", "", str(value or "").strip(), flags=re.I)
    parts = re.findall(r"\d+", text)
    return tuple(int(p) for p in parts) if parts else (0,)


def version_is_newer(candidate, current):
    return _parse_version_tuple(candidate) > _parse_version_tuple(current)


def _read_json_file(path):
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


class AppUpdateManager:
    """Fetch latest GitHub release and install the Windows setup executable."""

    def __init__(self, bundle_dir, app_dir):
        self.bundle_dir = bundle_dir
        self.app_dir = app_dir
        self.config = self._load_version_config()

    def _version_file_candidates(self):
        dirs = []
        for path in (self.bundle_dir, self.app_dir):
            if path and path not in dirs:
                dirs.append(path)
        return [os.path.join(path, VERSION_FILENAME) for path in dirs]

    def _load_version_config(self):
        merged = {
            "version": "0.0.0",
            "app_name": "D&D Before",
            "github_owner": "",
            "github_repo": "",
            "installer_asset_keyword": "Setup",
            "check_on_startup": False,
        }
        for path in self._version_file_candidates():
            merged.update(_read_json_file(path))
        return merged

    def get_current_version(self):
        return str(self.config.get("version") or "0.0.0").strip()

    def get_app_name(self):
        return str(self.config.get("app_name") or "D&D Before").strip()

    def is_configured(self):
        owner = str(self.config.get("github_owner") or "").strip()
        repo = str(self.config.get("github_repo") or "").strip()
        if not owner or not repo:
            return False
        if owner.upper() == "YOUR_GITHUB_USERNAME":
            return False
        return True

    def should_check_on_startup(self):
        return bool(self.config.get("check_on_startup", False))

    def _github_request(self, url):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404:
                raise RuntimeError("No GitHub releases found yet for this repository.") from exc
            raise RuntimeError(f"GitHub update check failed (HTTP {exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach GitHub: {exc.reason}") from exc

    def _pick_installer_asset(self, assets):
        keyword = str(self.config.get("installer_asset_keyword") or "Setup").lower()
        exe_assets = [
            asset for asset in (assets or [])
            if str(asset.get("name") or "").lower().endswith(".exe")
        ]
        if not exe_assets:
            return None
        for asset in exe_assets:
            name = str(asset.get("name") or "").lower()
            if keyword in name:
                return asset
        return exe_assets[0]

    def check_for_update(self):
        if not self.is_configured():
            raise RuntimeError(
                "Update source is not configured. Edit version.json with your GitHub owner and repo, "
                "then publish a GitHub Release with the installer .exe attached."
            )
        owner = urllib.parse.quote(str(self.config["github_owner"]).strip(), safe="")
        repo = urllib.parse.quote(str(self.config["github_repo"]).strip(), safe="")
        payload = self._github_request(f"https://api.github.com/repos/{owner}/{repo}/releases/latest")
        tag_name = str(payload.get("tag_name") or "").strip()
        if not tag_name:
            raise RuntimeError("Latest GitHub release did not include a version tag.")
        latest_version = re.sub(r"^v", "", tag_name, flags=re.I)
        current_version = self.get_current_version()
        asset = self._pick_installer_asset(payload.get("assets"))
        return {
            "current_version": current_version,
            "latest_version": latest_version,
            "update_available": version_is_newer(latest_version, current_version),
            "release_name": str(payload.get("name") or tag_name).strip(),
            "release_notes": str(payload.get("body") or "").strip(),
            "html_url": str(payload.get("html_url") or "").strip(),
            "asset_name": str(asset.get("name") or "").strip() if asset else "",
            "asset_url": str(asset.get("browser_download_url") or "").strip() if asset else "",
            "asset_size": int(asset.get("size") or 0) if asset else 0,
        }

    def download_installer(self, asset_url, asset_name=None, progress_callback: Optional[Callable[[float], None]] = None):
        if not asset_url:
            raise RuntimeError("No installer download URL was provided.")
        updates_dir = os.path.join(self.app_dir, "updates")
        os.makedirs(updates_dir, exist_ok=True)
        safe_name = re.sub(r'[<>:"/\\|?*]+', "_", str(asset_name or "DnD_Before_Setup.exe"))
        dest_path = os.path.join(updates_dir, safe_name)

        request = urllib.request.Request(asset_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                total = int(response.headers.get("Content-Length") or 0)
                read = 0
                chunk_size = 1024 * 256
                with open(dest_path, "wb") as handle:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        handle.write(chunk)
                        read += len(chunk)
                        if progress_callback and total > 0:
                            progress_callback(min(1.0, read / total))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Installer download failed (HTTP {exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Installer download failed: {exc.reason}") from exc

        if progress_callback:
            progress_callback(1.0)
        return dest_path

    def launch_installer(self, installer_path):
        if not installer_path or not os.path.isfile(installer_path):
            raise RuntimeError("Installer file was not found.")
        args = [installer_path, "/CLOSEAPPLICATIONS"]
        if sys.platform == "win32":
            subprocess.Popen(args, close_fds=True)
            return True
        os.startfile(installer_path)  # type: ignore[attr-defined]
        return True

    def open_release_page(self, url):
        if not url:
            return
        if sys.platform == "win32":
            os.startfile(url)  # type: ignore[attr-defined]
            return
        import webbrowser
        webbrowser.open(url)