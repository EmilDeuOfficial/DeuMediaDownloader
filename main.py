import ctypes
import importlib.util
import sys
from pathlib import Path


REQUIRED_PACKAGES = {
    "webview": "pywebview",
    "spotipy": "spotipy",
    "yt_dlp":  "yt-dlp",
    "mutagen": "mutagen",
    "requests": "requests",
}


def _check_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _check_ffmpeg() -> bool:
    from converter import find_ffmpeg
    return find_ffmpeg() is not None


def _resource_dir() -> Path:
    """Folder that contains frontend/ and img/ (PyInstaller unpacks them to _MEIPASS)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent


def _message_box(title: str, text: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)  # MB_ICONERROR
    except Exception:
        pass


def _round_corners(window) -> None:
    """Ask Windows 11 for rounded corners on the frameless window (no-op elsewhere)."""
    try:
        hwnd = window.native.Handle.ToInt32()
        preference = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(preference), 4)
    except Exception:
        pass


def main():
    if not getattr(sys, "frozen", False):
        missing = [pkg for mod, pkg in REQUIRED_PACKAGES.items() if not _check_module(mod)]
        if missing:
            install_cmd = f"pip install {' '.join(missing)}"
            print(f"[ERROR] Missing packages: {', '.join(missing)}")
            print(f"        Run:  {install_cmd}")
            _message_box(
                "Missing Dependencies",
                "The following packages are required but not installed:\n\n"
                + "\n".join(missing)
                + f"\n\nRun this command and restart:\n{install_cmd}",
            )
            sys.exit(1)

    from config import load_language
    load_language()

    ffmpeg_ok = _check_ffmpeg()
    if not ffmpeg_ok:
        print("[WARNING] FFmpeg not found. Audio conversion will be limited.")
        print("          Download FFmpeg from https://ffmpeg.org/download.html")
        print("          and add it to your system PATH.")

    import webview
    window = create_app(ffmpeg_ok)
    base = _resource_dir()
    icon = base / "img" / "app.ico"
    webview.start(http_server=True, icon=str(icon) if icon.exists() else None)


def create_app(ffmpeg_ok: bool):
    """Wire backend and window together. Returns the (not yet started) pywebview window."""
    import webview
    from api import Api, LAUNCHER_SIZE
    from config import APP_NAME
    from events import Emitter
    from services import build_runtimes

    emitter = Emitter()
    api = Api(emitter, build_runtimes(emitter, ffmpeg_ok), ffmpeg_ok)

    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    window = webview.create_window(
        APP_NAME,
        str(_resource_dir() / "frontend" / "index.html"),
        js_api=api,
        width=LAUNCHER_SIZE[0],
        height=LAUNCHER_SIZE[1],
        min_size=(320, 240),  # per-view minimums are enforced by Api.set_view/resize_to
        frameless=True,
        easy_drag=False,
        resizable=True,
        background_color="#0d1117",
        shadow=True,
    )
    api.attach_window(window)
    emitter.attach(window.evaluate_js)
    window.events.shown += lambda: _round_corners(window)
    return window


if __name__ == "__main__":
    main()
