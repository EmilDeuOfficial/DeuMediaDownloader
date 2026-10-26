"""Keeps yt-dlp (and its YouTube JavaScript solver) current inside the frozen .exe.

Sites change their pages every few weeks and yt-dlp follows with a new release; the copy
bundled into the .exe never changes. So the app downloads newer pure-Python wheels from
PyPI into the data folder, and on the next start puts them in front of the bundled copy on
sys.path. A wheel is a zip archive, and Python imports packages straight from a zip.

activate() must run before anything imports yt_dlp. check_for_updates() runs in the
background and only downloads; the new version is used after a restart.
"""
import hashlib
import importlib.metadata
import importlib.util
import json
import logging
import re
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from .config import CONFIG_FILE

log = logging.getLogger(__name__)

UPDATE_DIR = CONFIG_FILE.parent / "updates"
STAMP_FILE = UPDATE_DIR / "last_check.json"
CHECK_INTERVAL = 12 * 60 * 60  # seconds between two PyPI checks
PYPI_URL = "https://pypi.org/pypi/{}/json"

# PyPI project name -> wheel file prefix (and import name)
PACKAGES = {
    "yt-dlp":     "yt_dlp",
    "yt-dlp-ejs": "yt_dlp_ejs",
}

_active: Dict[str, str] = {}


def parse_version(text: str) -> Tuple[int, ...]:
    """'2026.10.21' -> (2026, 10, 21); unknown parts count as 0."""
    return tuple(int(p) for p in re.findall(r"\d+", text or "")) or (0,)


def bundled_version(project: str) -> str:
    try:
        return importlib.metadata.version(project)
    except importlib.metadata.PackageNotFoundError:
        return "0"


def _wheels(prefix: str, folder: Path):
    """Downloaded wheels of one package, newest first: [(version, path), ...]."""
    found = []
    for path in folder.glob(f"{prefix}-*.whl"):
        version = path.name[len(prefix) + 1:].split("-", 1)[0]
        found.append((version, path))
    found.sort(key=lambda item: parse_version(item[0]), reverse=True)
    return found


def activate(folder: Path = UPDATE_DIR, frozen: Optional[bool] = None) -> Dict[str, str]:
    """Put downloaded wheels that are newer than the bundled packages on sys.path.

    Only for the .exe: in a source checkout pip is the update path. Returns
    {project: version} of the versions that will be imported.
    """
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    for project, prefix in PACKAGES.items():
        bundled = bundled_version(project)
        _active[project] = bundled
        if not frozen or not folder.is_dir():
            continue
        if prefix in sys.modules:
            log.warning("%s was imported before the update check, keeping %s", prefix, bundled)
            continue
        for version, path in _wheels(prefix, folder):
            if parse_version(version) <= parse_version(bundled):
                break
            sys.path.insert(0, str(path))
            try:
                origin = importlib.util.find_spec(prefix).origin or ""
            except Exception as exc:  # zipimport raises its own error types
                origin = f"error: {exc}"
            if not origin.startswith(str(path)):
                # Damaged download: drop it and keep looking (in the end the bundled copy).
                sys.path.remove(str(path))
                log.warning("Ignoring %s, it does not import (%s)", path.name, origin or "not found")
                continue
            _active[project] = version
            log.info("Using downloaded %s %s from %s (bundled: %s)", project, version, origin, bundled)
            break
    return dict(_active)


def active_versions() -> Dict[str, str]:
    return dict(_active) or {p: bundled_version(p) for p in PACKAGES}


def _due(now: float) -> bool:
    try:
        last = json.loads(STAMP_FILE.read_text(encoding="utf-8")).get("checked", 0)
    except FileNotFoundError:
        return True
    except (OSError, ValueError) as exc:
        log.warning("Update stamp unreadable, checking again: %s", exc)
        return True
    return now - float(last) >= CHECK_INTERVAL


def _write_stamp(now: float) -> None:
    tmp = STAMP_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"checked": now}), encoding="utf-8")
    tmp.replace(STAMP_FILE)


def _release(session, project: str, version: str = "") -> dict:
    url = PYPI_URL.format(f"{project}/{version}" if version else project)
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _wheel_of(data: dict) -> Optional[dict]:
    """{'version', 'url', 'sha256', 'filename'} of the universal wheel of a PyPI release."""
    for item in data.get("urls", []):
        name = item.get("filename", "")
        if item.get("packagetype") == "bdist_wheel" and name.endswith("-py3-none-any.whl"):
            return {"version": data["info"]["version"], "url": item["url"],
                    "sha256": item["digests"]["sha256"], "filename": name}
    return None


def ejs_pin(requires_dist) -> Optional[str]:
    """yt-dlp only accepts the exact yt-dlp-ejs version it was released with."""
    for req in requires_dist or []:
        match = re.match(r"yt-dlp-ejs\s*==\s*([\w.]+)", req)
        if match:
            return match.group(1)
    return None


def _download(session, wheel: dict, folder: Path) -> Path:
    target = folder / wheel["filename"]
    tmp = target.with_suffix(".part")
    digest = hashlib.sha256()
    with session.get(wheel["url"], timeout=60, stream=True) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(1 << 16):
                digest.update(chunk)
                f.write(chunk)
    if digest.hexdigest() != wheel["sha256"]:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"checksum mismatch for {wheel['filename']}")
    tmp.replace(target)
    return target


def _prune(prefix: str, folder: Path, keep: Path) -> None:
    """Delete older downloaded wheels; the one in use stays until the next start."""
    for version, path in _wheels(prefix, folder):
        if path == keep or str(path) in sys.path:
            continue
        try:
            path.unlink()
        except OSError as exc:
            log.warning("Could not delete old update %s: %s", path.name, exc)


def _fetch(session, wheel: dict, prefix: str, folder: Path, project: str) -> bool:
    """Download one wheel unless it is not newer than what is bundled or downloaded."""
    current = max([active_versions().get(project, "0")] + [v for v, _ in _wheels(prefix, folder)],
                  key=parse_version)
    if parse_version(wheel["version"]) <= parse_version(current):
        return False
    path = _download(session, wheel, folder)
    _prune(prefix, folder, keep=path)
    log.info("Downloaded %s %s, active after restart", project, wheel["version"])
    return True


def check_for_updates(force: bool = False, session=None, folder: Path = UPDATE_DIR,
                      now: Optional[float] = None) -> Dict[str, str]:
    """Download newer wheels from PyPI. Returns {project: version} of new downloads."""
    now = time.time() if now is None else now
    folder.mkdir(parents=True, exist_ok=True)
    if not force and folder == UPDATE_DIR and not _due(now):
        return {}
    if session is None:
        import requests
        session = requests.Session()
    downloaded = {}
    try:
        release = _release(session, "yt-dlp")
        wheel = _wheel_of(release)
        if wheel and _fetch(session, wheel, "yt_dlp", folder, "yt-dlp"):
            downloaded["yt-dlp"] = wheel["version"]
        # The solver must match the yt-dlp release that will be active.
        pin = ejs_pin(release["info"].get("requires_dist"))
        if wheel and pin:
            ejs = _wheel_of(_release(session, "yt-dlp-ejs", pin))
            if ejs and _fetch(session, ejs, "yt_dlp_ejs", folder, "yt-dlp-ejs"):
                downloaded["yt-dlp-ejs"] = ejs["version"]
    except Exception as exc:
        log.warning("Update check failed: %s", exc)
    if folder == UPDATE_DIR:
        try:
            _write_stamp(now)
        except OSError as exc:
            log.warning("Could not write update stamp: %s", exc)
    return downloaded


def check_in_background() -> None:
    if not getattr(sys, "frozen", False):
        return
    threading.Thread(target=check_for_updates, name="ytdlp-update", daemon=True).start()
