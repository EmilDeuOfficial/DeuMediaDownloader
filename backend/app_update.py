"""Updates of the app itself: finds a newer GitHub release, downloads its setup and starts it.

The release page of EmilDeuOfficial/DeuMediaDownloader is the only source. A new version is
announced by a tag "v<version>" that is higher than APP_VERSION and carries the asset
DeuMediaDownloader_Setup.exe. The setup runs silently (Inno Setup /SILENT), replaces the
installed files and starts the app again (see installer.iss, /RESTARTAPP).

This is separate from updater.py, which only keeps yt-dlp current inside the .exe.
"""
import hashlib
import logging
import re
import shutil
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from .config import APP_VERSION
from .updater import UPDATE_DIR, parse_version

log = logging.getLogger(__name__)

REPO = "EmilDeuOfficial/DeuMediaDownloader"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
SETUP_NAME = "DeuMediaDownloader_Setup.exe"
# Only files from this repository's releases are ever downloaded and started.
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
APP_UPDATE_DIR = UPDATE_DIR / "app"
SETUP_ARGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RESTARTAPP=1"]


class UpdateError(Exception):
    """`key` names a message in config.STRINGS; api.py shows the translated text."""

    def __init__(self, key: str, detail: str = ""):
        super().__init__(key)
        self.key = key
        self.detail = detail


class Cancelled(Exception):
    pass


def _session(session=None):
    if session is not None:
        return session
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": f"DeuMediaDownloader/{APP_VERSION}",
                      "Accept": "application/vnd.github+json"})
    return s


def _tag_version(tag: str) -> str:
    """'v7.3' -> '7.3'. Anything that does not look like a version number gives ''."""
    match = re.fullmatch(r"[vV]?(\d+(?:\.\d+)*)", (tag or "").strip())
    return match.group(1) if match else ""


def _setup_asset(release: dict) -> Optional[dict]:
    for asset in release.get("assets", []):
        url = asset.get("browser_download_url", "")
        if asset.get("name") == SETUP_NAME and url.startswith(DOWNLOAD_PREFIX):
            digest = str(asset.get("digest") or "")
            return {
                "url": url,
                "size": int(asset.get("size") or 0),
                "sha256": digest[7:].lower() if digest.lower().startswith("sha256:") else "",
            }
    return None


def parse_release(release: dict, current: str = APP_VERSION) -> dict:
    """Turn the GitHub API answer into what the UI needs.

    {"available": bool, "current": str, "version": str, "notes": str, "page": str,
     "name": str, "size": int}. `available` is only True when the release is newer and has
    a usable setup file; the download details stay on the Python side (see check()).
    """
    version = _tag_version(release.get("tag_name", ""))
    info = {"available": False, "current": current, "version": current, "notes": "",
            "page": release.get("html_url") or RELEASES_URL, "name": release.get("name") or "", "size": 0}
    if not version or release.get("draft") or release.get("prerelease"):
        return info
    if parse_version(version) <= parse_version(current):
        return info
    asset = _setup_asset(release)
    if asset is None:
        raise UpdateError("upd_err_no_setup")
    info.update(available=True, version=version, notes=(release.get("body") or "").strip(),
                size=asset["size"])
    return info


class AppUpdater:
    """Holds the result of the last check so the download uses exactly what the user saw."""

    def __init__(self, session=None, folder: Path = APP_UPDATE_DIR, current: str = APP_VERSION):
        self._session = session
        self._folder = folder
        self._current = current
        self._asset: Optional[dict] = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._busy = False

    # --------------------------------------------------------------- check
    def check(self) -> dict:
        session = _session(self._session)
        try:
            resp = session.get(LATEST_URL, timeout=15)
        except Exception as exc:
            log.warning("Update check failed: %s", exc)
            raise UpdateError("upd_err_network", str(exc))
        if resp.status_code in (403, 429):
            log.warning("Update check refused by GitHub: HTTP %s", resp.status_code)
            raise UpdateError("upd_err_rate_limit")
        if resp.status_code == 404:
            # No release has been published yet: nothing to update to.
            return parse_release({}, self._current)
        if resp.status_code != 200:
            log.warning("Update check failed: HTTP %s", resp.status_code)
            raise UpdateError("upd_err_server", str(resp.status_code))
        try:
            release = resp.json()
        except ValueError as exc:
            log.warning("Update check: unreadable answer: %s", exc)
            raise UpdateError("upd_err_server", "json")
        info = parse_release(release, self._current)
        self._asset = _setup_asset(release) if info["available"] else None
        if not info["available"]:
            self._remove_downloads()
        return info

    # ------------------------------------------------------------ download
    def cancel(self) -> None:
        self._cancel.set()

    def download(self, progress: Optional[Callable[[float], None]] = None) -> Path:
        """Download the setup found by the last check(); returns the verified file."""
        if self._asset is None:
            raise UpdateError("upd_err_nothing")
        with self._lock:
            if self._busy:
                raise UpdateError("upd_err_busy")
            self._busy = True
        self._cancel.clear()
        try:
            return self._download(self._asset, progress or (lambda _p: None))
        finally:
            self._busy = False

    def _download(self, asset: dict, progress: Callable[[float], None]) -> Path:
        target = self._folder / SETUP_NAME
        if self._is_complete(target, asset):
            # Retry after a declined Windows prompt: the file is already here and verified.
            progress(1.0)
            return target
        session = _session(self._session)
        try:
            self._remove_downloads()
            self._folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("Update folder not writable: %s", exc)
            raise UpdateError("upd_err_disk", str(exc))
        tmp = target.with_suffix(".part")
        digest = hashlib.sha256()
        done = 0
        try:
            with session.get(asset["url"], timeout=30, stream=True) as resp:
                if resp.status_code != 200:
                    raise UpdateError("upd_err_server", str(resp.status_code))
                total = int(resp.headers.get("Content-Length") or asset["size"] or 0)
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(1 << 16):
                        if self._cancel.is_set():
                            raise Cancelled()
                        f.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        if total:
                            progress(min(done / total, 1.0))
            self._verify(tmp, done, digest.hexdigest(), asset)
            tmp.replace(target)
        except UpdateError:
            tmp.unlink(missing_ok=True)
            raise
        except Cancelled:
            tmp.unlink(missing_ok=True)
            raise UpdateError("upd_err_cancelled")
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            log.warning("Update download failed (disk): %s", exc)
            raise UpdateError("upd_err_disk", str(exc))
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            log.warning("Update download failed: %s", exc)
            raise UpdateError("upd_err_download", str(exc))
        progress(1.0)
        return target

    @classmethod
    def _is_complete(cls, path: Path, asset: dict) -> bool:
        if not path.is_file():
            return False
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    digest.update(chunk)
            cls._verify(path, path.stat().st_size, digest.hexdigest(), asset)
        except (OSError, UpdateError):
            return False
        return True

    @staticmethod
    def _verify(path: Path, size: int, sha256: str, asset: dict) -> None:
        if asset["size"] and size != asset["size"]:
            raise UpdateError("upd_err_checksum", f"size {size} != {asset['size']}")
        if asset["sha256"] and sha256 != asset["sha256"]:
            raise UpdateError("upd_err_checksum", "sha256")
        with open(path, "rb") as f:
            if f.read(2) != b"MZ":
                raise UpdateError("upd_err_checksum", "not an executable")

    def _remove_downloads(self) -> None:
        if self._folder.is_dir():
            shutil.rmtree(self._folder, ignore_errors=True)


def setup_command(setup: Path) -> Dict[str, str]:
    """ShellExecute parameters for the silent update (admin rights are needed, see installer.iss)."""
    return {"file": str(setup), "params": " ".join(SETUP_ARGS)}
