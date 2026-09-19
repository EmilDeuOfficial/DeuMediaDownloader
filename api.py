"""The object exposed to JavaScript as window.pywebview.api.

Every public method returns {"ok": True, "data": ...} or {"ok": False, "error": str}
(plus "title" for user-facing validation errors) and never raises. All attributes are
private because pywebview walks the public attributes of the exposed object.
"""
import functools
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import clipboard
import config
from config import (
    APP_NAME,
    APP_VERSION,
    AUDIO_FORMATS,
    DEFAULT_CONFIG,
    SP_FILENAME_TEMPLATES,
    T,
    TT_COOKIE_BROWSERS,
    TT_FILENAME_TEMPLATES,
    VIDEO_FORMATS,
    YT_FILENAME_TEMPLATES,
    active_strings,
    current_language,
)

LAUNCHER_SIZE = (720, 360)
TOOL_DEFAULT_SIZE = (820, 720)
TOOL_MIN_SIZE = (700, 600)
GEOMETRY_KEYS = {
    "spotify": "sp_win_geo",
    "youtube": "yt_win_geo",
    "tiktok": "tt_win_geo",
    "launcher": "launcher_pos",
}
_APP_ID = "{8F3A2B1C-4D5E-6F7A-8B9C-0D1E2F3A4B5C}_is1"


class ApiError(Exception):
    def __init__(self, message: str, title: str = ""):
        super().__init__(message)
        self.title = title


def _safe(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return {"ok": True, "data": fn(self, *args, **kwargs)}
        except ApiError as exc:
            res = {"ok": False, "error": str(exc)}
            if exc.title:
                res["title"] = exc.title
            return res
        except Exception as exc:
            return {"ok": False, "error": str(exc) or exc.__class__.__name__}
    return wrapper


def format_geometry(w: int, h: int, x: int, y: int) -> str:
    return f"{int(w)}x{int(h)}+{int(x)}+{int(y)}"


_GEO_RE = re.compile(r"^\s*(?:(\d+)x(\d+))?(?:([+-])(-?\d+)([+-])(-?\d+))?\s*$")


def parse_geometry(text: str) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """Parse a Tk-style geometry string ("WxH+X+Y", "+X+Y", "WxH"). Unknown parts are None."""
    m = _GEO_RE.match(text or "")
    if not m:
        return None, None, None, None

    def signed(sign: Optional[str], num: Optional[str]) -> Optional[int]:
        if num is None:
            return None
        value = int(num)
        return -value if sign == "-" and value > 0 else value

    w = int(m.group(1)) if m.group(1) else None
    h = int(m.group(2)) if m.group(2) else None
    return w, h, signed(m.group(3), m.group(4)), signed(m.group(5), m.group(6))


def _default_spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class Api:
    def __init__(self, emitter: Any, runtimes: Dict[str, Any], ffmpeg_ok: bool,
                 spawn: Optional[Callable[[Callable[[], None]], None]] = None):
        self._em = emitter
        self._rt = runtimes
        self._ffmpeg_ok = ffmpeg_ok
        self._spawn = spawn or _default_spawn
        self._window: Any = None
        self._view: Optional[str] = None
        self._maximized = False
        self._normal_geo = ""
        self._started = False
        self._data_cleared = False

    # ------------------------------------------------------------- plumbing
    def attach_window(self, window: Any) -> None:
        self._window = window
        events = getattr(window, "events", None)
        if events is not None:
            events.closing += self._on_closing

    def _on_closing(self) -> None:
        self._save_geometry(self._view)

    def _load(self) -> dict:
        if self._data_cleared:
            return dict(DEFAULT_CONFIG)
        return config.load_config()

    def _store(self, cfg: dict) -> None:
        if not self._data_cleared:
            config.save_config(cfg)

    def _runtime(self, service: str) -> Any:
        rt = self._rt.get(service)
        if rt is None:
            raise ApiError(f"Unknown service: {service}")
        return rt

    def _screen_size(self) -> Tuple[int, int]:
        try:
            import webview
            s = webview.screens[0]
            return int(s.width), int(s.height)
        except Exception:
            return 1920, 1080

    # ------------------------------------------------------------ bootstrap
    @_safe
    def bootstrap(self) -> dict:
        cfg = self._load()
        if not self._started:
            self._started = True
            for rt in self._rt.values():
                self._spawn(lambda rt=rt: rt.configure(cfg))
        return {
            "app_name": APP_NAME,
            "version": APP_VERSION,
            "lang": current_language(),
            "strings": active_strings(),
            "config": cfg,
            "ffmpeg_ok": self._ffmpeg_ok,
            "options": {
                "audio_formats": list(AUDIO_FORMATS),
                "video_formats": list(VIDEO_FORMATS),
                "sp_templates": [[k, v] for k, v in SP_FILENAME_TEMPLATES.items()],
                "yt_templates": [[k, v] for k, v in YT_FILENAME_TEMPLATES.items()],
                "tt_templates": [[k, v] for k, v in TT_FILENAME_TEMPLATES.items()],
                "cookie_browsers": [[k, v] for k, v in TT_COOKIE_BROWSERS.items()],
            },
            "tasks": {sid: rt.tasks() for sid, rt in self._rt.items()},
        }

    # --------------------------------------------------------------- config
    @_safe
    def save_config(self, partial: dict) -> dict:
        cfg = self._load()
        cfg.update(partial)
        self._store(cfg)
        return cfg

    @_safe
    def save_settings(self, service: str, partial: dict) -> dict:
        rt = self._runtime(service)
        cfg = self._load()
        cfg.update(partial)
        self._store(cfg)
        self._spawn(lambda: rt.configure(cfg))
        return cfg

    # ------------------------------------------------------------ downloads
    @_safe
    def submit(self, service: str, url: str, out_dir: str, fmt: str) -> None:
        rt = self._runtime(service)
        url = (url or "").strip()
        out_dir = (out_dir or "").strip()
        if not url:
            raise ApiError(T(f"mb_no_url_{service}"), T("mb_no_url_title"))
        if not out_dir:
            raise ApiError(T("mb_no_outdir"), T("mb_no_outdir_title"))
        rt.submit(url, out_dir, fmt)

    @_safe
    def clear_done(self, service: str) -> list:
        return self._runtime(service).clear_done()

    # -------------------------------------------------------------- dialogs
    def _dialog(self, kind: str, directory: str = "", file_types: tuple = ()) -> Optional[str]:
        import webview
        kinds = webview.FileDialog
        dialog = kinds.FOLDER if kind == "folder" else kinds.OPEN
        result = self._window.create_file_dialog(
            dialog, directory=directory or "", allow_multiple=False, file_types=file_types)
        return str(result[0]) if result else None

    @_safe
    def pick_folder(self, initial: str = "") -> Optional[str]:
        return self._dialog("folder", initial)

    @_safe
    def pick_file(self, kind: str = "cookies") -> Optional[str]:
        if kind == "cookies":
            return self._dialog("file", file_types=("Cookies (*.txt)", "All files (*.*)"))
        raise ApiError(f"Unknown file kind: {kind}")

    @_safe
    def paste(self) -> str:
        return clipboard.read_text().strip()

    @_safe
    def open_folder(self, path: str) -> None:
        os.startfile(path)  # type: ignore[attr-defined]  # Windows only

    @_safe
    def open_url(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            raise ApiError("Only http(s) URLs can be opened.")
        webbrowser.open(url)

    # --------------------------------------------------------------- window
    @_safe
    def minimize(self) -> None:
        self._window.minimize()

    @_safe
    def toggle_maximize(self) -> None:
        if self._maximized:
            self._window.restore()
            self._maximized = False
        else:
            self._normal_geo = self._current_geometry()
            self._window.maximize()
            self._maximized = True

    @_safe
    def get_rect(self) -> dict:
        win = self._window
        return {"x": win.x, "y": win.y, "w": win.width, "h": win.height}

    @_safe
    def resize_to(self, w: int, h: int, fix: str = "") -> None:
        """Resize from a JS edge handle. `fix` holds the edges that must stay in place
        ("E" when dragging the west edge, "S" when dragging the north edge)."""
        if self._view in (None, "launcher") or self._maximized:
            return
        from webview.window import FixPoint

        flags = FixPoint.NORTH | FixPoint.WEST
        if "E" in fix:
            flags = (flags & ~FixPoint.WEST) | FixPoint.EAST
        if "S" in fix:
            flags = (flags & ~FixPoint.NORTH) | FixPoint.SOUTH
        self._window.resize(
            max(int(w), TOOL_MIN_SIZE[0]), max(int(h), TOOL_MIN_SIZE[1]), flags)

    @_safe
    def close(self) -> None:
        self._save_geometry(self._view)
        self._window.destroy()

    @_safe
    def set_view(self, view: str) -> None:
        if view not in GEOMETRY_KEYS:
            raise ApiError(f"Unknown view: {view}")
        if self._maximized:
            self._window.restore()
            self._maximized = False
        self._save_geometry(self._view)
        cfg = self._load()
        w, h, x, y = parse_geometry(cfg.get(GEOMETRY_KEYS[view], ""))
        if view == "launcher":
            w, h = LAUNCHER_SIZE
        else:
            w, h = (w or TOOL_DEFAULT_SIZE[0], h or TOOL_DEFAULT_SIZE[1])
            w, h = max(w, TOOL_MIN_SIZE[0]), max(h, TOOL_MIN_SIZE[1])
        if x is None or y is None:
            sw, sh = self._screen_size()
            x, y = (sw - w) // 2, (sh - h) // 2
        self._window.resize(w, h)
        self._window.move(x, y)
        self._view = view

    @_safe
    def save_geometry(self, view: str) -> None:
        self._save_geometry(view)

    def _current_geometry(self) -> str:
        win = self._window
        return format_geometry(win.width, win.height, win.x, win.y)

    def _save_geometry(self, view: Optional[str]) -> None:
        if view is None or self._data_cleared or self._window is None:
            return
        cfg = self._load()
        if view == "launcher":
            value = f"+{self._window.x}+{self._window.y}"
        elif self._maximized:
            value = self._normal_geo
        else:
            value = self._current_geometry()
        if not value:
            return
        cfg[GEOMETRY_KEYS[view]] = value
        self._store(cfg)

    # ---------------------------------------------------------- maintenance
    @_safe
    def clear_data(self) -> None:
        self._data_cleared = True
        shutil.rmtree(config.CONFIG_FILE.parent, ignore_errors=True)

    @_safe
    def uninstall_ffmpeg(self) -> None:
        subprocess.Popen(
            ["winget", "uninstall", "yt-dlp.FFmpeg", "--accept-source-agreements"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    @_safe
    def uninstall_app(self) -> None:
        uninstaller = self._find_uninstaller()
        if not uninstaller:
            raise ApiError(T("no_uninstaller"))
        import ctypes
        # ShellExecuteW with "runas" makes Windows show the UAC prompt for the uninstaller.
        ctypes.windll.shell32.ShellExecuteW(None, "runas", uninstaller, None, None, 1)
        self._window.destroy()

    @staticmethod
    def _find_uninstaller() -> Optional[str]:
        import winreg

        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (
                rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{_APP_ID}",
                rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{_APP_ID}",
            ):
                try:
                    with winreg.OpenKey(hive, sub) as key:
                        raw, _ = winreg.QueryValueEx(key, "UninstallString")
                        path = raw.strip().strip('"')
                        if Path(path).exists():
                            return path
                except Exception:
                    continue

        exe_dir = Path(sys.executable).parent
        for name in ("unins000.exe", "uninstall.exe"):
            candidate = exe_dir / name
            if candidate.exists():
                return str(candidate)

        for base in (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ):
            candidate = base / "DeuMediaDownloader" / "unins000.exe"
            if candidate.exists():
                return str(candidate)
        return None
