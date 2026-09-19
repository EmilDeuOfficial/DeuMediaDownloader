"""Per-service runtimes: resolve a URL, queue tasks, forward task updates as events.

This is the logic that used to live inside the three Tk apps in ui.py. A
ServiceRuntime knows nothing about the window; it only talks to an Emitter.
"""
import os
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from config import T
from downloader import (
    DownloadStatus,
    DownloadTask,
    SpotifyClient,
    SpotifyDownloadManager,
    TikTokDownloadManager,
    TikTokTask,
    YouTubeClient,
    YouTubeDownloadManager,
    YouTubeTask,
    _apply_template,
    extract_tiktok_entries,
    extract_youtube_entries,
    is_youtube_url,
)

SERVICE_IDS = ("spotify", "youtube", "tiktok")
_NAME_MAX = 60
_FINISHED = (DownloadStatus.DONE, DownloadStatus.ERROR)


def _short(text: str, limit: int) -> str:
    return text[:limit] + "…" if len(text) > limit else text


def _default_open(path: str) -> None:
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # Windows only
    except Exception:
        pass


def _default_spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


@dataclass
class ResolveContext:
    log: Callable[[str], None]
    client: Any
    config: dict


@dataclass
class ServiceSpec:
    id: str
    concurrency_key: str
    open_folder_key: str
    make_manager: Callable[[int, bool], Any]
    resolve: Callable[[str, ResolveContext], list]
    make_task: Callable[[Any, str, str], Any]
    task_name: Callable[[Any, dict], str]
    log_name: Callable[[Any], str]
    queued_key: str
    init_client: Optional[Callable[[dict, Callable[[str], None]], Any]] = None
    needs_client: bool = False


def serialize_task(spec: ServiceSpec, task: Any, config: dict) -> dict:
    status: DownloadStatus = task.status
    label = status.value
    if status == DownloadStatus.ERROR and task.error_msg:
        label = f"Error: {_short(task.error_msg, _NAME_MAX)}"
    return {
        "id": task.task_id,
        "service": spec.id,
        "name": spec.task_name(task, config),
        "status": status.name,
        "label": label,
        "progress": task.progress,
        "error": task.error_msg,
    }


def _status_log_line(name: str, task: Any) -> str:
    if task.status == DownloadStatus.DONE:
        return T("log_done").format(name)
    if task.status == DownloadStatus.ERROR:
        return T("log_error").format(name, task.error_msg)
    return f"{task.status.value}: {name}"


class ServiceRuntime:
    def __init__(self, spec: ServiceSpec, emitter: Any, ffmpeg_ok: bool,
                 opener: Optional[Callable[[str], None]] = None,
                 spawn: Optional[Callable[[Callable[[], None]], None]] = None):
        self._spec = spec
        self._em = emitter
        self._ffmpeg_ok = ffmpeg_ok
        self._opener = opener or _default_open
        self._spawn = spawn or _default_spawn
        self._config: dict = {}
        self._client: Any = None
        self._manager: Any = None
        self._workers: Optional[int] = None
        self._tasks: Dict[str, Any] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ setup
    def configure(self, config: dict) -> None:
        self._config = dict(config)
        if self._spec.init_client:
            self._client = self._spec.init_client(self._config, self._log)
        workers = int(self._config.get(self._spec.concurrency_key, 2))
        if self._manager is None or workers != self._workers:
            self._manager = self._spec.make_manager(workers, self._ffmpeg_ok)
            self._workers = workers

    # ---------------------------------------------------------------- queries
    def tasks(self) -> List[dict]:
        with self._lock:
            return [serialize_task(self._spec, t, self._config) for t in self._tasks.values()]

    def clear_done(self) -> List[str]:
        with self._lock:
            done = [tid for tid, t in self._tasks.items() if t.status in _FINISHED]
            for tid in done:
                del self._tasks[tid]
        return done

    # ----------------------------------------------------------------- submit
    def submit(self, url: str, out_dir: str, fmt: str) -> None:
        if self._spec.needs_client and self._client is None:
            self._em.emit("resolve_error", {
                "service": self._spec.id, "message": T("mb_api_msg"), "kind": "api",
            })
            return
        self._spawn(lambda: self._resolve_and_queue(url, out_dir, fmt))

    def _resolve_and_queue(self, url: str, out_dir: str, fmt: str) -> None:
        try:
            ctx = ResolveContext(log=self._log, client=self._client, config=self._config)
            items = self._spec.resolve(url, ctx)
            self._log(T(self._spec.queued_key).format(len(items), fmt))
            for item in items:
                self._queue(item, out_dir, fmt)
            self._em.emit("resolve_done", {"service": self._spec.id})
        except Exception as exc:
            msg = str(exc)
            self._log(T("err_resolving").format(msg))
            self._em.emit("resolve_error", {
                "service": self._spec.id, "message": msg, "kind": "error",
            })

    def _queue(self, item: Any, out_dir: str, fmt: str) -> None:
        spec = self._spec
        task = spec.make_task(item, out_dir, fmt)
        task.on_progress = self._on_progress
        task.on_status = self._on_status
        task.on_done = self._on_done
        with self._lock:
            self._tasks[task.task_id] = task
        self._em.emit("task_added", serialize_task(spec, task, self._config))
        self._log(T("log_queued").format(spec.log_name(task)))
        self._manager.submit(task)

    # -------------------------------------------------------------- callbacks
    def _on_progress(self, task: Any) -> None:
        self._em.emit_progress(self._spec.id, task.task_id, task.progress)

    def _on_status(self, task: Any) -> None:
        self._em.emit("task_status", serialize_task(self._spec, task, self._config))
        self._log(_status_log_line(self._spec.log_name(task), task))

    def _on_done(self, task: Any) -> None:
        self._em.emit("task_status", serialize_task(self._spec, task, self._config))
        if not self._config.get(self._spec.open_folder_key, False):
            return
        with self._lock:
            all_done = all(t.status in _FINISHED for t in self._tasks.values())
        if all_done:
            self._opener(task.output_dir)

    def _log(self, msg: str) -> None:
        self._em.emit("log", {"service": self._spec.id, "msg": msg})


# ---------------------------------------------------------------------------
# Real service definitions
# ---------------------------------------------------------------------------

def _spotify_init_client(config: dict, log: Callable[[str], None]) -> Any:
    cid = config.get("spotify_client_id", "")
    csec = config.get("spotify_client_secret", "")
    if not (cid and csec):
        log(T("no_credentials"))
        return None
    try:
        client = SpotifyClient(cid, csec)
        log(T("spotify_init"))
        return client
    except Exception as exc:
        log(T("spotify_auth_err").format(exc))
        return None


def _is_youtube_playlist(url: str) -> bool:
    return "playlist?list=" in url or ("/playlist" in url and "watch?v=" not in url)


def _spotify_resolve(url: str, ctx: ResolveContext) -> list:
    if is_youtube_url(url):
        ctx.log(T("fetching_youtube"))
        yt = YouTubeClient()
        if _is_youtube_playlist(url):
            return yt.get_playlist_tracks(url)
        return [yt.get_track_info(url)]

    if ctx.client is None:
        raise ValueError(T("no_credentials"))
    kind, sp_id = ctx.client.parse_url(url)
    ctx.log(T("fetching_spotify").format(kind))
    if kind == "track":
        return [ctx.client.get_track_info(sp_id)]
    if kind == "playlist":
        return ctx.client.get_playlist_tracks(sp_id)
    if kind == "album":
        return ctx.client.get_album_tracks(sp_id)
    raise ValueError(f"Unknown type: {kind}")


def _spotify_task_name(task: DownloadTask, cfg: dict) -> str:
    tmpl = cfg.get("sp_filename_template", "{artist} - {title}")
    t = task.track
    name = _apply_template(tmpl, artist=t.artist, title=t.title,
                           album=t.album or "", year=t.year or "")
    return _short(name, _NAME_MAX - 3)


def _flat_task_name(template_key: str) -> Callable[[Any, dict], str]:
    def name_of(task: Any, cfg: dict) -> str:
        tmpl = cfg.get(template_key, "{title}")
        raw = task.display_name()
        parts = raw.split(" - ", 1) if " - " in raw else ["", raw]
        name = _apply_template(tmpl, artist=parts[0].strip(), title=parts[1].strip())
        return _short(name, _NAME_MAX - 3)
    return name_of


def _youtube_resolve(url: str, ctx: ResolveContext) -> list:
    ctx.log(T("fetching_youtube"))
    return extract_youtube_entries(url)


def _tiktok_resolve(url: str, ctx: ResolveContext) -> list:
    ctx.log(T("fetching_tiktok"))
    return extract_tiktok_entries(url)


def _spotify_spec() -> ServiceSpec:
    return ServiceSpec(
        id="spotify",
        concurrency_key="concurrent_downloads",
        open_folder_key="sp_open_folder",
        make_manager=SpotifyDownloadManager,
        resolve=_spotify_resolve,
        make_task=lambda track, out_dir, fmt: DownloadTask(
            task_id=str(uuid.uuid4()), track=track, output_dir=out_dir, format_name=fmt),
        task_name=_spotify_task_name,
        log_name=lambda task: task.track.display_name(),
        queued_key="queued_n_tracks",
        init_client=_spotify_init_client,
        needs_client=True,
    )


def _youtube_spec() -> ServiceSpec:
    return ServiceSpec(
        id="youtube",
        concurrency_key="yt_concurrent",
        open_folder_key="yt_open_folder",
        make_manager=YouTubeDownloadManager,
        resolve=_youtube_resolve,
        make_task=lambda entry, out_dir, fmt: YouTubeTask(
            task_id=str(uuid.uuid4()), url=entry["url"], title=entry["title"],
            output_dir=out_dir, format_name=fmt),
        task_name=_flat_task_name("yt_filename_template"),
        log_name=lambda task: task.display_name(),
        queued_key="queued_n_videos",
    )


def _tiktok_spec() -> ServiceSpec:
    return ServiceSpec(
        id="tiktok",
        concurrency_key="tt_concurrent",
        open_folder_key="tt_open_folder",
        make_manager=TikTokDownloadManager,
        resolve=_tiktok_resolve,
        make_task=lambda entry, out_dir, fmt: TikTokTask(
            task_id=str(uuid.uuid4()), url=entry["url"], title=entry["title"],
            output_dir=out_dir, format_name=fmt),
        task_name=_flat_task_name("tt_filename_template"),
        log_name=lambda task: task.display_name(),
        queued_key="queued_n_videos",
    )


def build_runtimes(emitter: Any, ffmpeg_ok: bool) -> Dict[str, ServiceRuntime]:
    specs = (_spotify_spec(), _youtube_spec(), _tiktok_spec())
    return {s.id: ServiceRuntime(s, emitter, ffmpeg_ok) for s in specs}
