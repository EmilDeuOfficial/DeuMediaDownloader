import glob
import re
import threading
import queue
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

import requests
import yt_dlp

from config import AUDIO_FORMATS, VIDEO_FORMATS, WIKI_PAGES, load_config, T
from converter import embed_metadata, fetch_cover, find_ffmpeg


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class DownloadStatus(Enum):
    QUEUED      = "Queued"
    SEARCHING   = "Searching…"
    DOWNLOADING = "Downloading…"
    CONVERTING  = "Converting…"
    EMBEDDING   = "Embedding…"
    DONE        = "Done"
    ERROR       = "Error"
    PAUSED      = "Paused"
    CANCELLED   = "Cancelled"


def _sanitize(name: str) -> str:
    name = name.replace('|', '｜').replace(':', '꞉')  # Unicode lookalikes (visually identical, Windows-safe)
    name = re.sub(r'[\\/*?"<>]', '', name)
    name = re.sub(r'\s{2,}', ' ', name)
    return name.strip()


def _apply_template(template: str, artist: str = "", title: str = "",
                    album: str = "", year: str = "") -> str:
    try:
        result = template.format(
            artist=artist or "Unknown Artist",
            title=title  or "Unknown Title",
            album=album  or "",
            year=year    or "",
        )
        result = re.sub(r'\s*\(\s*\)\s*', ' ', result)  # empty () from template
        result = re.sub(r'\s*\[\s*\]\s*', ' ', result)  # empty [] from template
        result = result.strip(" -—_").strip()
    except (KeyError, ValueError):
        result = title or artist or "track"
    return _sanitize(result) or "track"


_RATE_MAP = {"1M": 1_048_576, "5M": 5_242_880, "10M": 10_485_760, "50M": 52_428_800}

# yt-dlp's EmbedThumbnail postprocessor only supports these container/codec
# extensions (its own reported list); WAV (and anything else) raises a hard
# PostProcessingError that aborts the task even though the file already
# downloaded and converted successfully.
_THUMBNAIL_EMBED_EXTS = {"mp3", "mkv", "mka", "ogg", "opus", "flac", "m4a", "mp4", "m4v", "mov"}


def _ffmpeg_opts() -> dict:
    opts: dict = {}
    path = find_ffmpeg()
    if path:
        opts["ffmpeg_location"] = str(Path(path).parent)
    return opts


def _tiktok_cookie_opts(cfg: dict) -> dict:
    """TikTok blocks most cookie-less requests. A manually exported cookie file
    (cfg["tt_cookies_file"]) always works and takes priority since it needs no
    browser-side decryption; otherwise fall back to reading the selected browser's
    cookie jar directly (cfg["tt_cookies_browser"])."""
    cookie_file = cfg.get("tt_cookies_file", "")
    if cookie_file:
        return {"cookiefile": cookie_file}
    browser = cfg.get("tt_cookies_browser", "")
    return {"cookiesfrombrowser": (browser,)} if browser else {}


def _friendly_tiktok_error(msg: str) -> str:
    """Chrome's and Edge's "App-Bound Encryption" (rolled out since mid-2024)
    permanently broke yt-dlp's cookie decryption for those browsers on Windows - see
    https://github.com/yt-dlp/yt-dlp/issues/10927. There is no fix on yt-dlp's or our
    side; Firefox (if installed) or a manually exported cookie file still work."""
    if "Failed to decrypt with DPAPI" in msg:
        return T("tt_err_dpapi").format(WIKI_PAGES["tiktok_cookies"])
    if "could not find" in msg and "cookies database" in msg:
        return T("tt_err_no_browser").format(WIKI_PAGES["tiktok_cookies"])
    return msg


class TaskInterrupted(yt_dlp.utils.DownloadCancelled):
    """Raised inside a running download when the user pauses or cancels the task.

    Deriving from yt-dlp's DownloadCancelled makes yt-dlp abort at once without
    retrying other formats. `reason` is "pause" or "cancel".
    """

    def __init__(self, reason: str):
        super().__init__(f"task {reason}")
        self.reason = reason


def _check_stop(task) -> None:
    if task.stop:
        raise TaskInterrupted(task.stop)


# yt-dlp's unfinished download files plus the thumbnail it writes next to the media file.
_PARTIAL_SUFFIXES = (".part", ".ytdl", ".temp", ".webp", ".jpg", ".jpeg", ".png")


def remove_partial_files(task) -> None:
    """Delete the unfinished download files of `task` (see _PARTIAL_SUFFIXES).

    Finished media files are never touched, only names that start with the task's
    file name and end in one of those suffixes.
    """
    stem = getattr(task, "work_stem", "")
    if not stem:
        return
    for path in Path(task.output_dir).glob(glob.escape(stem) + ".*"):
        name = path.name.lower()
        if name.endswith(_PARTIAL_SUFFIXES) or ".part-frag" in name:
            try:
                path.unlink()
            except OSError:
                pass


def _has_partial_files(task) -> bool:
    stem = getattr(task, "work_stem", "")
    if not stem:
        return False
    return any(p.name.lower().endswith((".part", ".ytdl"))
               for p in Path(task.output_dir).glob(glob.escape(stem) + ".*"))


def _run_ydl(task, ydl_opts: Dict[str, Any], url: str) -> None:
    """Run the yt-dlp download. YouTube sometimes answers HTTP 416 when yt-dlp tries to
    resume a paused download from its .part file; then the download starts over once."""
    for attempt in (1, 2):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return
        except TaskInterrupted:
            raise
        except Exception as exc:
            if attempt == 1 and "416" in str(exc) and _has_partial_files(task):
                remove_partial_files(task)
                continue
            raise


def _finish_interrupted(task, reason: str, status_cb, progress_cb) -> None:
    """Common end of a download that was stopped by the user."""
    if reason == "cancel":
        remove_partial_files(task)
        status_cb(DownloadStatus.CANCELLED)
        progress_cb(0.0)
        if task.on_done:
            task.on_done(task)
    else:
        # Paused: keep the partial file and the progress; resuming re-queues the task
        # and yt-dlp continues from the .part file.
        status_cb(DownloadStatus.PAUSED)


class _TaskManager:
    """Runs queued tasks on a limited number of worker threads.

    A task can be re-submitted (resume). Every submit gets a new run id so an older
    queue entry of the same task is recognised as stale and skipped, as is an entry
    of a task that was paused or cancelled while it waited.
    """

    def __init__(self, max_workers: int = 2, ffmpeg_ok: bool = True):
        self._max_workers = max_workers
        self._ffmpeg_ok   = ffmpeg_ok
        self._active      = 0
        self._lock        = threading.Lock()
        self._pending: queue.Queue = queue.Queue()
        self._dispatcher  = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatcher.start()

    def submit(self, task) -> None:
        with self._lock:
            task.run_id += 1
            token = task.run_id
        self._pending.put((task, token))

    @staticmethod
    def _stale(task, token: int) -> bool:
        return task.run_id != token or bool(task.stop)

    def _dispatch_loop(self) -> None:
        while True:
            task, token = self._pending.get()
            if self._stale(task, token):
                continue
            while True:
                with self._lock:
                    if self._active < self._max_workers:
                        self._active += 1
                        break
                time.sleep(0.2)
            if self._stale(task, token):
                with self._lock:
                    self._active -= 1
                continue
            threading.Thread(target=self._run_task, args=(task,), daemon=True).start()

    def _run_task(self, task) -> None:
        try:
            self._run(task)
        finally:
            with self._lock:
                self._active -= 1

    def _run(self, task) -> None:
        raise NotImplementedError


# ===========================================================================
# SPOTIFY
# ===========================================================================

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
        return f"{self.artist} - {self.title}"


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
    stop:         Optional[str]  = None    # "pause" or "cancel", set by the user
    run_id:       int            = 0       # bumped on every submit (see _TaskManager)
    work_stem:    str            = ""      # file name stem, used to clean up partial files

    on_progress: Optional[Callable] = field(default=None, repr=False)
    on_status:   Optional[Callable] = field(default=None, repr=False)
    on_done:     Optional[Callable] = field(default=None, repr=False)


class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str):
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        # Cache is keyed by client_id: a token cached under different (e.g. old/rotated)
        # credentials causes Spotify's token endpoint to reject refresh attempts with
        # "invalid_client", since a refresh token is only valid for the client it was issued to.
        cache_path = Path.home() / ".spotify_downloader" / f".spotify_token_cache_{client_id}"
        cache_path.parent.mkdir(parents=True, exist_ok=True)

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

    def parse_url(self, url: str) -> tuple[str, str]:
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

    def get_track_info(self, track_id: str) -> TrackInfo:
        return self._track_from_data(self._sp.track(track_id))

    def get_playlist_tracks(self, playlist_id: str) -> List[TrackInfo]:
        import spotipy
        try:
            return self._get_playlist_tracks_via_api(playlist_id)
        except spotipy.exceptions.SpotifyException as exc:
            if exc.http_status != 403:
                raise
            # Spotify's Web API rejects "get playlist items" with 403 for playlists the
            # authenticated user doesn't own, unless the app has been granted Extended
            # Quota Mode (Spotify no longer approves this for hobby apps). The public
            # embed page exposes the same track listing with no such restriction, so we
            # fall back to that for other people's playlists.
            return self._get_playlist_tracks_via_embed(playlist_id)

    def _get_playlist_tracks_via_api(self, playlist_id: str) -> List[TrackInfo]:
        tracks: List[TrackInfo] = []
        results = self._sp.playlist_items(playlist_id, additional_types=("track",))
        while results:
            for item in results.get("items", []):
                if not item:
                    continue
                t = item.get("item") or item.get("track")
                if not t or not t.get("id") or t.get("type") == "episode":
                    continue
                try:
                    tracks.append(self._track_from_data(t))
                except Exception:
                    pass
            results = self._sp.next(results) if results.get("next") else None
        return tracks

    def _get_playlist_tracks_via_embed(self, playlist_id: str) -> List[TrackInfo]:
        resp = requests.get(
            f"https://open.spotify.com/embed/playlist/{playlist_id}", timeout=15
        )
        resp.raise_for_status()
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, re.S
        )
        if not m:
            raise ValueError("Could not read playlist from Spotify's public page.")

        import json
        entity = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
        track_ids = [
            item["uri"].rsplit(":", 1)[-1]
            for item in entity.get("trackList") or []
            if (item.get("uri") or "").startswith("spotify:track:")
        ]

        # The embed page only exposes a preview window of the playlist (currently
        # ~100 tracks); this is a known limit of this fallback, not a bug.
        #
        # Spotify's batch "Get Several Tracks" endpoint (/v1/tracks?ids=...) is
        # blocked by the same Extended Quota restriction as playlist items, even
        # though the single-track endpoint isn't - so these have to be fetched
        # one at a time.
        tracks: List[TrackInfo] = []
        for track_id in track_ids:
            try:
                tracks.append(self.get_track_info(track_id))
            except Exception:
                pass
        return tracks

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

    @staticmethod
    def _track_from_data(data: dict) -> TrackInfo:
        images    = data["album"]["images"]
        cover_url = images[0]["url"] if images else None
        year      = data["album"].get("release_date", "")[:4] or None
        return TrackInfo(
            track_id    = data["id"],
            title       = data["name"],
            artist      = ", ".join(a["name"] for a in data["artists"]),
            album       = data["album"]["name"],
            cover_url   = cover_url,
            duration_ms = data["duration_ms"],
            year        = year,
        )


def _search_entries(query: str) -> List[Dict[str, Any]]:
    """Top 5 YouTube results (flat metadata) for `query`. A failed search counts as no result."""
    opts = {
        "quiet":         True,
        "no_warnings":   True,
        "extract_flat":  True,
        "skip_download": True,
        **_ffmpeg_opts(),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
        return [e for e in ((info or {}).get("entries") or []) if e]
    except Exception:
        return []


def _search_queries(artist: str, title: str) -> List[str]:
    """Queries in the order they are tried.

    Spotify joins several artists with ", " and YouTube often finds nothing for the
    combined string (for example "HARDX, NX!ZE - ELECTROSOULS"), so each artist alone
    is tried afterwards.
    """
    queries = [f"{artist} - {title}"]
    for name in artist.split(", "):
        name = name.strip()
        query = f"{name} - {title}"
        if name and query not in queries:
            queries.append(query)
    return queries


def _pick_by_duration(entries: List[Dict[str, Any]], target_s: float) -> Optional[Dict[str, Any]]:
    """Result whose duration is closest to the Spotify track (first result if unknown)."""
    valid = [e for e in entries if e.get("id")]
    if not valid:
        return None
    if target_s <= 0:
        return valid[0]
    timed = [e for e in valid if (e.get("duration") or 0) > 0]
    if not timed:
        return valid[0]
    return min(timed, key=lambda e: abs(e["duration"] - target_s))


def _find_best_youtube_match(artist: str, title: str, duration_ms: int) -> str:
    """URL of the YouTube video that best matches the Spotify track.

    Raises LookupError when none of the search queries finds anything, instead of
    handing yt-dlp an empty search (it would finish without error and without a file).
    """
    target_s = duration_ms / 1000 if duration_ms > 0 else 0
    queries = _search_queries(artist, title)
    for query in queries:
        best = _pick_by_duration(_search_entries(query), target_s)
        if best:
            return f"https://www.youtube.com/watch?v={best['id']}"
    raise LookupError(T("err_no_match").format(queries[0]))


def download_spotify_track(task: DownloadTask, ffmpeg_ok: bool) -> None:
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
        _check_stop(task)
        cfg      = load_config()
        fmt_info = AUDIO_FORMATS[task.format_name]
        ext      = fmt_info["ext"]
        quality  = fmt_info["ydl_quality"]
        track    = task.track
        out_dir  = Path(task.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        tmpl          = cfg.get("sp_filename_template", "{artist} - {title}")
        safe_filename = _apply_template(tmpl, artist=track.artist, title=track.title,
                                        album=track.album, year=track.year or "")
        final_path    = out_dir / f"{safe_filename}.{ext}"
        task.work_stem = safe_filename

        if final_path.exists() and cfg.get("sp_skip_existing", True):
            task.output_file = str(final_path)
            _status(DownloadStatus.DONE)
            _progress(1.0)
            if task.on_done:
                task.on_done(task)
            return

        def ydl_hook(d: dict):
            if d["status"] == "downloading":
                _check_stop(task)
                total      = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    _progress(min(downloaded / total * 0.8, 0.8))
            elif d["status"] == "finished":
                _status(DownloadStatus.CONVERTING)
                _progress(0.85)

        _status(DownloadStatus.SEARCHING)
        _progress(0.0)

        search_url = _find_best_youtube_match(
            track.artist, track.title, track.duration_ms
        )
        _check_stop(task)

        ydl_opts: Dict[str, Any] = {
            "format":         "bestaudio/best",
            "outtmpl":        str(out_dir / f"{safe_filename}.%(ext)s"),
            "quiet":          True,
            "no_warnings":    True,
            "progress_hooks": [ydl_hook],
            "noplaylist":     True,
            **_ffmpeg_opts(),
        }

        if ext != "opus" and find_ffmpeg():
            pp: Dict[str, Any] = {"key": "FFmpegExtractAudio", "preferredcodec": ext}
            if quality and quality != "0":
                pp["preferredquality"] = quality
            ydl_opts["postprocessors"] = [pp]
            if cfg.get("sp_normalize", False):
                ydl_opts.setdefault("postprocessor_args", {})
                ydl_opts["postprocessor_args"]["FFmpegExtractAudio"] = ["-af", "loudnorm"]

        _status(DownloadStatus.DOWNLOADING)

        _check_stop(task)
        _run_ydl(task, ydl_opts, search_url)

        if not final_path.exists():
            candidates = list(out_dir.glob(f"{safe_filename}.*"))
            if candidates:
                final_path = candidates[0]
            else:
                raise FileNotFoundError("Downloaded file not found in output directory.")

        task.output_file = str(final_path)

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

    except TaskInterrupted as stop:
        _finish_interrupted(task, stop.reason, _status, _progress)

    except Exception as exc:
        _status(DownloadStatus.ERROR, str(exc))
        _progress(0.0)
        if task.on_done:
            task.on_done(task)


class SpotifyDownloadManager(_TaskManager):
    def _run(self, task) -> None:
        download_spotify_track(task, self._ffmpeg_ok)


# ===========================================================================
# YOUTUBE
# ===========================================================================

def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


class YouTubeClient:
    """Used by the Spotify downloader to resolve YouTube URLs pasted into its URL field."""
    @staticmethod
    def _ydl_opts() -> dict:
        return {"quiet": True, "no_warnings": True, **_ffmpeg_opts()}

    def get_track_info(self, url: str) -> TrackInfo:
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
    stop:        Optional[str]  = None
    run_id:      int            = 0
    work_stem:   str            = ""

    on_progress: Optional[Callable] = field(default=None, repr=False)
    on_status:   Optional[Callable] = field(default=None, repr=False)
    on_done:     Optional[Callable] = field(default=None, repr=False)

    def display_name(self) -> str:
        return self.title or self.url


def extract_youtube_entries(url: str) -> List[Dict[str, Any]]:
    is_playlist = "playlist?list=" in url or ("/playlist" in url and "watch?v=" not in url)

    if not is_playlist:
        url = re.sub(r"[&?]list=[^&]+", "", url)
        url = re.sub(r"[&?]index=[^&]+", "", url)

    ydl_opts = {
        "quiet":         True,
        "no_warnings":   True,
        "extract_flat":  "in_playlist" if is_playlist else False,
        "noplaylist":    not is_playlist,
        "skip_download": True,
        **_ffmpeg_opts(),
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


def download_youtube_task(task: YouTubeTask, ffmpeg_ok: bool) -> None:
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
        _check_stop(task)
        cfg      = load_config()
        is_video = task.format_name in VIDEO_FORMATS
        fmt_info = VIDEO_FORMATS[task.format_name] if is_video else AUDIO_FORMATS[task.format_name]
        ext      = fmt_info["ext"]
        out_dir  = Path(task.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        raw_title = task.title or "track"
        if " - " in raw_title:
            _yt_artist, _yt_title = raw_title.split(" - ", 1)
        else:
            _yt_artist, _yt_title = "", raw_title
        tmpl       = cfg.get("yt_filename_template", "{title}")
        safe_title = _apply_template(tmpl, artist=_yt_artist.strip(),
                                     title=_yt_title.strip())
        final_path = out_dir / f"{safe_title}.{ext}"
        task.work_stem = safe_title

        if final_path.exists():
            task.output_file = str(final_path)
            _status(DownloadStatus.DONE)
            _progress(1.0)
            if task.on_done:
                task.on_done(task)
            return

        def ydl_hook(d: dict):
            if d["status"] == "downloading":
                _check_stop(task)
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
            **_ffmpeg_opts(),
        }

        if not is_video and ffmpeg_ok:
            quality = fmt_info.get("ydl_quality", "0")
            pp: Dict[str, Any] = {"key": "FFmpegExtractAudio", "preferredcodec": ext}
            if quality and quality != "0":
                pp["preferredquality"] = quality
            postprocessors.append(pp)

        if cfg.get("yt_embed_thumbnail", True) and not is_video and ffmpeg_ok and ext in _THUMBNAIL_EMBED_EXTS:
            ydl_opts["writethumbnail"] = True
            postprocessors.append({"key": "EmbedThumbnail"})

        if cfg.get("yt_write_subtitles", False) and ffmpeg_ok:
            langs = [l.strip() for l in cfg.get("yt_subtitle_langs", "en").split(",") if l.strip()]
            ydl_opts["writesubtitles"] = True
            ydl_opts["subtitleslangs"] = langs
            postprocessors.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})

        if cfg.get("yt_sponsorblock", False):
            cats = ["sponsor", "selfpromo", "interaction", "intro", "outro"]
            postprocessors.append({"key": "SponsorBlock", "categories": cats})
            postprocessors.append({"key": "ModifyChapters", "remove_sponsor_segments": cats})

        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors

        rate = cfg.get("yt_rate_limit", "")
        if rate and rate in _RATE_MAP:
            ydl_opts["ratelimit"] = _RATE_MAP[rate]

        _check_stop(task)
        _run_ydl(task, ydl_opts, task.url)

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

    except TaskInterrupted as stop:
        _finish_interrupted(task, stop.reason, _status, _progress)

    except Exception as exc:
        _status(DownloadStatus.ERROR, str(exc))
        _progress(0.0)
        if task.on_done:
            task.on_done(task)


class YouTubeDownloadManager(_TaskManager):
    def _run(self, task) -> None:
        download_youtube_task(task, self._ffmpeg_ok)


# ===========================================================================
# TIKTOK
# ===========================================================================

def is_tiktok_url(url: str) -> bool:
    return "tiktok.com" in url


def _tiktok_title(info: dict) -> str:
    uploader = (info.get("uploader") or info.get("creator") or "").strip()
    desc     = (info.get("description") or "").strip()
    title    = (info.get("title") or "").strip()
    vid_id   = info.get("id", "video")

    def _generic(s: str) -> bool:
        return s.startswith("TikTok video #") or s == vid_id

    if desc and not _generic(desc):
        text = desc[:80].strip()
    elif title and not _generic(title):
        text = title[:80].strip()
    else:
        raw  = info.get("upload_date") or ""
        text = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}" if len(raw) == 8 else vid_id[:20]

    return f"{uploader} - {text}" if uploader else text


@dataclass
class TikTokTask:
    task_id:     str
    url:         str
    title:       str
    output_dir:  str
    format_name: str
    status:      DownloadStatus = DownloadStatus.QUEUED
    progress:    float          = 0.0
    error_msg:   str            = ""
    output_file: str            = ""
    stop:        Optional[str]  = None
    run_id:      int            = 0
    work_stem:   str            = ""

    on_progress: Optional[Callable] = field(default=None, repr=False)
    on_status:   Optional[Callable] = field(default=None, repr=False)
    on_done:     Optional[Callable] = field(default=None, repr=False)

    def display_name(self) -> str:
        return self.title or self.url


def extract_tiktok_entries(url: str) -> List[Dict[str, Any]]:
    is_playlist = ("/tag/" in url or "/music/" in url or
                   ("/@" in url and "/video/" not in url))

    ydl_opts = {
        "quiet":         True,
        "no_warnings":   True,
        "extract_flat":  is_playlist,
        "skip_download": True,
        **_ffmpeg_opts(),
        **_tiktok_cookie_opts(load_config()),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise type(exc)(_friendly_tiktok_error(str(exc))) from exc

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
                or f"https://www.tiktok.com/video/{entry.get('id', '')}"
            )
            entries.append({"url": vid_url, "title": _tiktok_title(entry)})
    else:
        entries.append({
            "url":   info.get("webpage_url") or url,
            "title": _tiktok_title(info),
        })
    return entries


def download_tiktok_task(task: TikTokTask, ffmpeg_ok: bool) -> None:
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
        _check_stop(task)
        cfg      = load_config()
        is_video = task.format_name in VIDEO_FORMATS
        fmt_info = VIDEO_FORMATS[task.format_name] if is_video else AUDIO_FORMATS[task.format_name]
        ext      = fmt_info["ext"]
        out_dir  = Path(task.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        raw_title = task.title or "video"
        if " - " in raw_title:
            _tt_artist, _tt_title = raw_title.split(" - ", 1)
        else:
            _tt_artist, _tt_title = "", raw_title
        tmpl       = cfg.get("tt_filename_template", "{title}")
        safe_title = _apply_template(tmpl, artist=_tt_artist.strip(),
                                     title=_tt_title.strip())
        final_path = out_dir / f"{safe_title}.{ext}"
        task.work_stem = safe_title

        if final_path.exists():
            task.output_file = str(final_path)
            _status(DownloadStatus.DONE)
            _progress(1.0)
            if task.on_done:
                task.on_done(task)
            return

        def ydl_hook(d: dict):
            if d["status"] == "downloading":
                _check_stop(task)
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
            **_ffmpeg_opts(),
            **_tiktok_cookie_opts(cfg),
        }

        if not is_video and ffmpeg_ok:
            quality = fmt_info.get("ydl_quality", "0")
            pp: Dict[str, Any] = {"key": "FFmpegExtractAudio", "preferredcodec": ext}
            if quality and quality != "0":
                pp["preferredquality"] = quality
            postprocessors.append(pp)

        if cfg.get("tt_embed_thumbnail", True) and not is_video and ffmpeg_ok and ext in _THUMBNAIL_EMBED_EXTS:
            ydl_opts["writethumbnail"] = True
            postprocessors.append({"key": "EmbedThumbnail"})

        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors

        rate = cfg.get("tt_rate_limit", "")
        if rate and rate in _RATE_MAP:
            ydl_opts["ratelimit"] = _RATE_MAP[rate]

        _check_stop(task)
        _run_ydl(task, ydl_opts, task.url)

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

    except TaskInterrupted as stop:
        _finish_interrupted(task, stop.reason, _status, _progress)

    except Exception as exc:
        _status(DownloadStatus.ERROR, _friendly_tiktok_error(str(exc)))
        _progress(0.0)
        if task.on_done:
            task.on_done(task)


class TikTokDownloadManager(_TaskManager):
    def _run(self, task) -> None:
        download_tiktok_task(task, self._ffmpeg_ok)
