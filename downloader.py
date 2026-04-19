import re
import os
import threading
import queue
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

import yt_dlp

from config import AUDIO_FORMATS, load_config
from converter import embed_metadata, fetch_cover, find_ffmpeg


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class DownloadStatus(Enum):
    QUEUED      = "Queued"
    SEARCHING   = "Searching…"
    DOWNLOADING = "Downloading…"
    CONVERTING  = "Converting…"
    EMBEDDING   = "Embedding…"
    DONE        = "Done"
    ERROR       = "Error"


@dataclass
class TrackInfo:
    track_id:    str
    title:       str
    artist:      str
    album:       str
    cover_url:   Optional[str]
    duration_ms: int
    year:        Optional[str] = None

    def display_name(self) -> str:
        return f"{self.artist} – {self.title}"


@dataclass
class DownloadTask:
    task_id:      str
    track:        TrackInfo
    output_dir:   str
    format_name:  str
    status:       DownloadStatus = DownloadStatus.QUEUED
    progress:     float          = 0.0
    error_msg:    str            = ""
    output_file:  str            = ""

    # Callbacks set by the UI; called from the worker thread via root.after
    on_progress: Optional[Callable] = field(default=None, repr=False)
    on_status:   Optional[Callable] = field(default=None, repr=False)
    on_done:     Optional[Callable] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Spotify client (wraps spotipy)
# ---------------------------------------------------------------------------

class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str):
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        from pathlib import Path

        cache_path = Path.home() / ".spotify_downloader" / ".spotify_token_cache"
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # OAuth grants access to public + private playlists and all catalog endpoints.
        # On first run the browser opens once for the user to authorise the app.
        self._sp = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri="http://127.0.0.1:8888/callback",
                scope="playlist-read-private playlist-read-collaborative",
                cache_path=str(cache_path),
                open_browser=True,
            )
        )

    # ------------------------------------------------------------------
    def parse_url(self, url: str) -> tuple[str, str]:
        """Return (type, id) for a Spotify URL. Raises ValueError on bad input."""
        patterns = [
            (r"/track/([A-Za-z0-9]+)",    "track"),
            (r"/playlist/([A-Za-z0-9]+)", "playlist"),
            (r"/album/([A-Za-z0-9]+)",    "album"),
            (r"spotify:track:([A-Za-z0-9]+)",     "track"),
            (r"spotify:playlist:([A-Za-z0-9]+)",  "playlist"),
            (r"spotify:album:([A-Za-z0-9]+)",     "album"),
        ]
        for pattern, kind in patterns:
            m = re.search(pattern, url)
            if m:
                return kind, m.group(1)
        raise ValueError(f"Could not parse Spotify URL: {url}")

    # ------------------------------------------------------------------
    def get_track_info(self, track_id: str) -> TrackInfo:
        data = self._sp.track(track_id)
        return self._track_from_data(data)

    # ------------------------------------------------------------------
    def get_playlist_tracks(self, playlist_id: str) -> List[TrackInfo]:
        tracks: List[TrackInfo] = []
        # playlist_items supports tracks + episodes; filter to tracks only
        results = self._sp.playlist_items(
            playlist_id,
            additional_types=("track",),
        )
        while results:
            for item in results.get("items", []):
                if not item:
                    continue
                # playlist_items() uses "item" key, playlist_tracks() uses "track"
                t = item.get("item") or item.get("track")
                if not t or not t.get("id") or t.get("type") == "episode":
                    continue
                try:
                    tracks.append(self._track_from_data(t))
                except Exception:
                    pass
            results = self._sp.next(results) if results.get("next") else None
        return tracks

    # ------------------------------------------------------------------
    def get_album_tracks(self, album_id: str) -> List[TrackInfo]:
        album_data = self._sp.album(album_id)
        album_name = album_data["name"]
        cover_url  = album_data["images"][0]["url"] if album_data["images"] else None
        year       = album_data.get("release_date", "")[:4] or None

        tracks: List[TrackInfo] = []
        results = self._sp.album_tracks(album_id)
        while results:
            for t in results["items"]:
                tracks.append(TrackInfo(
                    track_id    = t["id"],
                    title       = t["name"],
                    artist      = ", ".join(a["name"] for a in t["artists"]),
                    album       = album_name,
                    cover_url   = cover_url,
                    duration_ms = t["duration_ms"],
                    year        = year,
                ))
            results = self._sp.next(results) if results.get("next") else None
        return tracks

    # ------------------------------------------------------------------
    @staticmethod
    def _track_from_data(data: dict) -> TrackInfo:
        images     = data["album"]["images"]
        cover_url  = images[0]["url"] if images else None
        year       = data["album"].get("release_date", "")[:4] or None
        return TrackInfo(
            track_id    = data["id"],
            title       = data["name"],
            artist      = ", ".join(a["name"] for a in data["artists"]),
            album       = data["album"]["name"],
            cover_url   = cover_url,
            duration_ms = data["duration_ms"],
            year        = year,
        )


# ---------------------------------------------------------------------------
# YouTube client
# ---------------------------------------------------------------------------

YT_PATTERNS = [
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
    r"youtube\.com/(?:playlist|watch)\?.*list=([A-Za-z0-9_-]+)",
]

def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


class YouTubeClient:
    @staticmethod
    def _ydl_opts() -> dict:
        opts = {
            "quiet":       True,
            "no_warnings": True,
            "extract_flat": False,
        }
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
        return opts

    def get_track_info(self, url: str) -> TrackInfo:
        # Strip playlist parameters so yt-dlp only fetches the single video
        url = re.sub(r"[&?]list=[^&]+", "", url)
        url = re.sub(r"[&?]index=[^&]+", "", url)
        with yt_dlp.YoutubeDL({**self._ydl_opts(), "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        return self._info_to_track(info)

    def get_playlist_tracks(self, url: str) -> List[TrackInfo]:
        with yt_dlp.YoutubeDL({**self._ydl_opts(), "extract_flat": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = info.get("entries", [info])
        tracks = []
        for e in entries:
            if not e:
                continue
            try:
                tracks.append(self._info_to_track(e))
            except Exception:
                pass
        return tracks

    @staticmethod
    def _info_to_track(info: dict) -> TrackInfo:
        title     = info.get("title", "Unknown")
        uploader  = info.get("uploader") or info.get("channel") or "YouTube"
        thumbnail = info.get("thumbnail")
        duration  = info.get("duration") or 0
        raw_id    = info.get("id", "")
        video_id  = f"https://www.youtube.com/watch?v={raw_id}" if raw_id else title[:16]
        year      = str(info["upload_date"][:4]) if info.get("upload_date") else None

        # Try to split "Artist - Title" from video title
        artist, clean_title = uploader, title
        if " - " in title:
            parts = title.split(" - ", 1)
            artist, clean_title = parts[0].strip(), parts[1].strip()

        return TrackInfo(
            track_id    = video_id,
            title       = clean_title,
            artist      = artist,
            album       = "YouTube",
            cover_url   = thumbnail,
            duration_ms = int(duration * 1000),
            year        = year,
        )


# ---------------------------------------------------------------------------
# Single-track download worker
# ---------------------------------------------------------------------------

def _sanitize(name: str) -> str:
    """Remove characters that are illegal in filenames."""
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def download_track(task: DownloadTask, ffmpeg_ok: bool) -> None:
    """
    Download a single track.  Called in a background thread.
    Updates task.status / task.progress and fires callbacks.
    """
    def _status(s: DownloadStatus, msg: str = ""):
        task.status = s
        task.error_msg = msg
        if task.on_status:
            task.on_status(task)

    def _progress(pct: float):
        task.progress = pct
        if task.on_progress:
            task.on_progress(task)

    try:
        cfg       = load_config()
        fmt_info  = AUDIO_FORMATS[task.format_name]
        ext       = fmt_info["ext"]
        quality   = fmt_info["ydl_quality"]
        track     = task.track
        out_dir   = Path(task.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_filename = _sanitize(f"{track.artist} - {track.title}")
        final_path    = out_dir / f"{safe_filename}.{ext}"

        # Skip if already downloaded (configurable)
        if final_path.exists() and cfg.get("sp_skip_existing", True):
            task.output_file = str(final_path)
            _status(DownloadStatus.DONE)
            _progress(1.0)
            if task.on_done:
                task.on_done(task)
            return

        # yt-dlp progress hook
        def ydl_progress_hook(d: dict):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    # downloading phase = 0–80%
                    _progress(min(downloaded / total * 0.8, 0.8))
            elif d["status"] == "finished":
                _status(DownloadStatus.CONVERTING)
                _progress(0.85)

        _status(DownloadStatus.SEARCHING)
        _progress(0.0)

        # YouTube tracks carry the direct URL in track_id; Spotify tracks get searched
        if track.album == "YouTube" and track.track_id.startswith("http"):
            search_query = track.track_id
        else:
            search_query = f"ytsearch1:{track.artist} {track.title} audio"

        ydl_opts: Dict[str, Any] = {
            "format":          "bestaudio/best",
            "outtmpl":         str(out_dir / f"{safe_filename}.%(ext)s"),
            "quiet":           True,
            "no_warnings":     True,
            "progress_hooks":  [ydl_progress_hook],
            "noplaylist":      True,
        }

        ffmpeg_path = find_ffmpeg()
        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = str(Path(ffmpeg_path).parent)

        # "Original" mode: skip conversion, keep whatever YouTube provides (best quality, no re-encoding)
        if ext != "opus" and ffmpeg_ok:
            pp: Dict[str, Any] = {"key": "FFmpegExtractAudio", "preferredcodec": ext}
            if quality and quality != "0":
                pp["preferredquality"] = quality
            ydl_opts["postprocessors"] = [pp]
            # Loudnorm normalisation
            if cfg.get("sp_normalize", False):
                ydl_opts.setdefault("postprocessor_args", {})
                ydl_opts["postprocessor_args"]["FFmpegExtractAudio"] = ["-af", "loudnorm"]

        _status(DownloadStatus.DOWNLOADING)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([search_query])

        # Find the output file (yt-dlp may rename it)
        if not final_path.exists():
            # Fallback: find any file that starts with safe_filename
            candidates = list(out_dir.glob(f"{safe_filename}.*"))
            if candidates:
                final_path = candidates[0]
            else:
                raise FileNotFoundError("Downloaded file not found in output directory.")

        task.output_file = str(final_path)

        # Embed metadata
        _status(DownloadStatus.EMBEDDING)
        _progress(0.90)

        cover_data = fetch_cover(track.cover_url) if cfg.get("sp_embed_cover", True) else None
        try:
            embed_metadata(
                filepath   = str(final_path),
                ext        = ext,
                title      = track.title,
                artist     = track.artist,
                album      = track.album,
                year       = track.year,
                cover_data = cover_data,
            )
        except Exception:
            pass

        _status(DownloadStatus.DONE)
        _progress(1.0)
        if task.on_done:
            task.on_done(task)

    except Exception as exc:
        _status(DownloadStatus.ERROR, str(exc))
        _progress(0.0)
        if task.on_done:
            task.on_done(task)


# ---------------------------------------------------------------------------
# Download manager (thread pool)
# ---------------------------------------------------------------------------

class DownloadManager:
    def __init__(self, max_workers: int = 2, ffmpeg_ok: bool = True):
        self._max_workers = max_workers
        self._ffmpeg_ok   = ffmpeg_ok
        self._active      = 0
        self._lock        = threading.Lock()
        self._pending: queue.Queue[DownloadTask] = queue.Queue()
        self._dispatcher  = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher.start()

    # ------------------------------------------------------------------
    def submit(self, task: DownloadTask) -> None:
        self._pending.put(task)

    # ------------------------------------------------------------------
    def _dispatch_loop(self) -> None:
        while True:
            task = self._pending.get()
            # Wait until a worker slot is free
            while True:
                with self._lock:
                    if self._active < self._max_workers:
                        self._active += 1
                        break
                time.sleep(0.2)

            t = threading.Thread(
                target=self._run_task,
                args=(task,),
                daemon=True,
            )
            t.start()

    # ------------------------------------------------------------------
    def _run_task(self, task: DownloadTask) -> None:
        try:
            download_track(task, self._ffmpeg_ok)
        finally:
            with self._lock:
                self._active -= 1


# ---------------------------------------------------------------------------
# YouTube direct download
# ---------------------------------------------------------------------------

@dataclass
class YouTubeTask:
    task_id:     str
    url:         str
    title:       str
    output_dir:  str
    format_name: str
    status:      DownloadStatus = DownloadStatus.QUEUED
    progress:    float          = 0.0
    error_msg:   str            = ""
    output_file: str            = ""

    on_progress: Optional[Callable] = field(default=None, repr=False)
    on_status:   Optional[Callable] = field(default=None, repr=False)
    on_done:     Optional[Callable] = field(default=None, repr=False)

    def display_name(self) -> str:
        return self.title or self.url


def extract_youtube_entries(url: str) -> List[Dict[str, Any]]:
    """Return [{url, title}] for a YouTube video or playlist URL."""
    # Only treat as playlist if the URL explicitly points to a playlist page
    is_playlist = "playlist?list=" in url or ("/playlist" in url and "watch?v=" not in url)

    if not is_playlist:
        # Strip list= and index= so yt-dlp never touches the playlist
        url = re.sub(r"[&?]list=[^&]+", "", url)
        url = re.sub(r"[&?]index=[^&]+", "", url)

    ydl_opts = {
        "quiet":         True,
        "no_warnings":   True,
        "extract_flat":  "in_playlist" if is_playlist else False,
        "noplaylist":    not is_playlist,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise ValueError("Could not extract info from URL.")

    entries: List[Dict[str, Any]] = []
    if info.get("_type") == "playlist":
        for entry in info.get("entries") or []:
            if not entry:
                continue
            vid_url = (
                entry.get("url")
                or entry.get("webpage_url")
                or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
            )
            entries.append({"url": vid_url, "title": entry.get("title") or "Unknown"})
    else:
        entries.append({
            "url":   info.get("webpage_url") or url,
            "title": info.get("title") or "Unknown",
        })
    return entries


_RATE_MAP = {"1M": 1_048_576, "5M": 5_242_880, "10M": 10_485_760, "50M": 52_428_800}


def download_youtube_task(task: "YouTubeTask", ffmpeg_ok: bool) -> None:
    def _status(s: DownloadStatus, msg: str = ""):
        task.status    = s
        task.error_msg = msg
        if task.on_status:
            task.on_status(task)

    def _progress(pct: float):
        task.progress = pct
        if task.on_progress:
            task.on_progress(task)

    try:
        from config import VIDEO_FORMATS
        cfg        = load_config()
        is_video   = task.format_name in VIDEO_FORMATS
        fmt_info   = VIDEO_FORMATS[task.format_name] if is_video else AUDIO_FORMATS[task.format_name]
        ext        = fmt_info["ext"]
        out_dir    = Path(task.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_title = _sanitize(task.title or "track")
        final_path = out_dir / f"{safe_title}.{ext}"

        if final_path.exists():
            task.output_file = str(final_path)
            _status(DownloadStatus.DONE)
            _progress(1.0)
            if task.on_done:
                task.on_done(task)
            return

        def ydl_hook(d: dict):
            if d["status"] == "downloading":
                total      = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    _progress(min(downloaded / total * 0.8, 0.8))
            elif d["status"] == "finished":
                _status(DownloadStatus.CONVERTING)
                _progress(0.85)

        _status(DownloadStatus.DOWNLOADING)
        _progress(0.0)

        postprocessors: List[Dict[str, Any]] = []

        ydl_opts: Dict[str, Any] = {
            "format":         fmt_info["ydl_format"] if is_video else "bestaudio/best",
            "outtmpl":        str(out_dir / f"{safe_title}.%(ext)s"),
            "quiet":          True,
            "no_warnings":    True,
            "progress_hooks": [ydl_hook],
            "noplaylist":     True,
        }

        ffmpeg_path = find_ffmpeg()
        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = str(Path(ffmpeg_path).parent)

        # Audio extraction
        if not is_video and ffmpeg_ok:
            quality = fmt_info.get("ydl_quality", "0")
            pp: Dict[str, Any] = {"key": "FFmpegExtractAudio", "preferredcodec": ext}
            if quality and quality != "0":
                pp["preferredquality"] = quality
            postprocessors.append(pp)

        # Embed thumbnail (audio files)
        if cfg.get("yt_embed_thumbnail", True) and not is_video and ffmpeg_ok:
            ydl_opts["writethumbnail"] = True
            postprocessors.append({"key": "EmbedThumbnail"})

        # Subtitles
        if cfg.get("yt_write_subtitles", False) and ffmpeg_ok:
            langs = [l.strip() for l in cfg.get("yt_subtitle_langs", "en").split(",") if l.strip()]
            ydl_opts["writesubtitles"]  = True
            ydl_opts["subtitleslangs"]  = langs
            postprocessors.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})

        # SponsorBlock
        if cfg.get("yt_sponsorblock", False):
            cats = ["sponsor", "selfpromo", "interaction", "intro", "outro"]
            postprocessors.append({"key": "SponsorBlock", "categories": cats})
            postprocessors.append({"key": "ModifyChapters", "remove_sponsor_segments": cats})

        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors

        # Speed limit
        rate = cfg.get("yt_rate_limit", "")
        if rate and rate in _RATE_MAP:
            ydl_opts["ratelimit"] = _RATE_MAP[rate]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([task.url])

        if not final_path.exists():
            candidates = list(out_dir.glob(f"{safe_title}.*"))
            if candidates:
                final_path = candidates[0]
            else:
                raise FileNotFoundError("Downloaded file not found.")

        task.output_file = str(final_path)
        _status(DownloadStatus.DONE)
        _progress(1.0)
        if task.on_done:
            task.on_done(task)

    except Exception as exc:
        _status(DownloadStatus.ERROR, str(exc))
        _progress(0.0)
        if task.on_done:
            task.on_done(task)


class YouTubeDownloadManager:
    def __init__(self, max_workers: int = 2, ffmpeg_ok: bool = True):
        self._max_workers = max_workers
        self._ffmpeg_ok   = ffmpeg_ok
        self._active      = 0
        self._lock        = threading.Lock()
        self._pending: queue.Queue["YouTubeTask"] = queue.Queue()
        self._dispatcher  = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher.start()

    def submit(self, task: "YouTubeTask") -> None:
        self._pending.put(task)

    def _dispatch_loop(self) -> None:
        while True:
            task = self._pending.get()
            while True:
                with self._lock:
                    if self._active < self._max_workers:
                        self._active += 1
                        break
                time.sleep(0.2)
            threading.Thread(target=self._run_task, args=(task,), daemon=True).start()

    def _run_task(self, task: "YouTubeTask") -> None:
        try:
            download_youtube_task(task, self._ffmpeg_ok)
        finally:
            with self._lock:
                self._active -= 1
