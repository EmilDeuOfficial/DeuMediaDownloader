import sys
import subprocess
import importlib.util


REQUIRED_PACKAGES = {
    "customtkinter": "customtkinter",
    "spotipy":       "spotipy",
    "yt_dlp":        "yt-dlp",
    "mutagen":       "mutagen",
    "requests":      "requests",
}


def _check_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _check_ffmpeg() -> bool:
    from converter import find_ffmpeg
    return find_ffmpeg() is not None


def main():
    missing = [pkg for mod, pkg in REQUIRED_PACKAGES.items() if not _check_module(mod)]

    if missing:
        install_cmd = f"pip install {' '.join(missing)}"
        print(f"[ERROR] Missing packages: {', '.join(missing)}")
        print(f"        Run:  {install_cmd}")
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Missing Dependencies",
                f"The following packages are required but not installed:\n\n"
                f"{chr(10).join(missing)}\n\n"
                f"Run this command and restart:\n{install_cmd}",
            )
            root.destroy()
        except Exception:
            pass
        sys.exit(1)

    from config import load_language
    load_language()

    ffmpeg_ok = _check_ffmpeg()
    if not ffmpeg_ok:
        print("[WARNING] FFmpeg not found. Audio conversion will be limited.")
        print("          Download FFmpeg from https://ffmpeg.org/download.html")
        print("          and add it to your system PATH.")

    from ui import LauncherApp, DeuDownloaderApp, YouTubeDownloaderApp

    while True:
        choice = LauncherApp().run()
        if not choice:
            break
        if choice == "spotify":
            went_back = DeuDownloaderApp(ffmpeg_available=ffmpeg_ok, show_back=True).run()
        else:
            went_back = YouTubeDownloaderApp(ffmpeg_available=ffmpeg_ok, show_back=True).run()
        if not went_back:
            break


if __name__ == "__main__":
    main()
