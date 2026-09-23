"""Spotify recording: plays a track in the hidden Spotify player and records its audio.

The task list, pause/cancel and status handling are the same as for the downloads; only the
worker differs. A recording runs in real time, so the manager runs one at a time (a Spotify
account plays one stream) and hands encoding and tagging to a background thread, which lets the
next track start right away.
"""
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .config import AUDIO_FORMATS, T, load_config
from .converter import embed_metadata, fetch_cover, find_ffmpeg
from .downloader import (
    DownloadStatus,
    DownloadTask,
    TaskInterrupted,
    _TaskManager,
    _apply_template,
    _check_stop,
    _finish_interrupted,
    _make_work_dir,
    _publish_result,
    _work_dir,
    remove_partial_files,
)
from .errors import RecordError
from .recorder import ProcessRecorder, RecordingInfo

_TAIL_SECONDS = 0.6         # audio still in the output buffer when Spotify reports the end
_START_TIMEOUT = 20.0       # the track must start playing within this time
_MAX_OVERRUN = 20.0         # the track must end within its length plus this time
_MIN_PLAYED = 0.9           # part of the track that must have played (else it was cut short)
_END_SLACK = 1.5            # a position this close to the track length counts as "at the end"
_STALL_SECONDS = 1.5        # the position must stand still this long at the end of the track
_SILENCE_PEAK = 0.000002    # a recording quieter than this is treated as silence (the player runs at 0.001)
_TARGET_PEAK = 0.84         # loudest sample of the finished file, about -1.5 dBFS
_EDGE_PAD = 1.0             # silence added before the first and after the last sound (room to ring out)
_CREATE_NO_WINDOW = 0x08000000


def _hooks(task: DownloadTask):
    def status(s: DownloadStatus, msg: str = "") -> None:
        task.status = s
        task.error_msg = msg
        if task.on_status:
            task.on_status(task)

    def progress(pct: float) -> None:
        task.progress = pct
        if task.on_progress:
            task.on_progress(task)

    return status, progress


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def _record_track(task: DownloadTask, session: Any, raw_path: Path, progress: Callable[[float], None],
                  recorder_cls: Callable[..., Any]) -> RecordingInfo:
    """Play the track and record it until Spotify reports the end. Stops early on pause/cancel."""
    recorder = recorder_cls(session.browser_pid(), raw_path)
    recorder.start()
    duration_s = max(task.track.duration_ms / 1000, 1.0)
    try:
        session.play(task.track.track_id)
        started = time.monotonic()
        last_position = 0.0
        moved_at = started     # when the position last moved forward
        while True:
            _check_stop(task)
            snap = session.snapshot()
            if snap["error"]:
                raise RecordError(snap["error"])
            now = time.monotonic()
            elapsed = now - started
            length = (snap["duration"] / 1000) or duration_s
            if snap["position"] / 1000 > last_position + 0.05:
                moved_at = now
            last_position = max(last_position, snap["position"] / 1000)
            if snap["ended"]:
                break
            # Spotify does not always report the end (the player can just stop): the position
            # sits at the end of the track without moving.
            if snap["played"] and last_position >= length - _END_SLACK and now - moved_at > _STALL_SECONDS:
                break
            if snap["played"] and last_position >= length + _END_SLACK:
                break   # the position ran past the end without any end signal
            if not snap["played"] and elapsed > _START_TIMEOUT:
                raise RecordError(T("err_rec_timeout"))
            if elapsed > duration_s + _MAX_OVERRUN:
                raise RecordError(T("err_rec_stalled"))
            progress(min(last_position / length, 1.0) * 0.9)
            time.sleep(0.25)
        if last_position < duration_s * _MIN_PLAYED:
            raise RecordError(T("err_rec_incomplete"))
        time.sleep(_TAIL_SECONDS)
    except BaseException:
        recorder.stop()
        session.pause()
        raise
    info = recorder.stop()
    if info.peak < _SILENCE_PEAK:
        raise RecordError(T("err_rec_silent"))
    return info


def _encode(ffmpeg: str, info: RecordingInfo, out: Path, fmt_info: Dict[str, Any],
            duration_ms: int, normalize: bool) -> None:
    """Raw capture -> chosen format.

    The capture is very quiet (the player ran at a tiny volume), so it is amplified first, in
    float, until its loudest sample is _TARGET_PEAK; then the silence before the first sound and
    after the track is cut, and exactly _EDGE_PAD seconds of silence are put back at both ends
    (room for the track to fade/ring out instead of a hard cut).
    """
    codec = fmt_info["codec"]
    delay_ms = int(_EDGE_PAD * 1000)
    filters = [f"volume={_TARGET_PEAK / info.peak:.6f}",
               "silenceremove=start_periods=1:start_threshold=-70dB:start_silence=0.05"]
    if duration_ms > 0:
        filters.append(f"atrim=duration={duration_ms / 1000 + 0.15:.3f}")
    filters += [f"adelay={'|'.join([str(delay_ms)] * info.channels)}", f"apad=pad_dur={_EDGE_PAD}"]
    if normalize:
        filters += ["loudnorm", f"aresample={info.sample_rate}"]   # loudnorm resamples to 192 kHz
    integer = codec == "flac" or codec.startswith("pcm_")
    if integer:
        filters.append("aresample=osf=s16:dither_method=triangular")
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "f32le", "-ar", str(info.sample_rate), "-ac", str(info.channels), "-i", str(info.path),
           "-af", ",".join(filters), "-c:a", codec]
    if fmt_info.get("bitrate"):
        cmd += ["-b:a", fmt_info["bitrate"]]
    if codec == "flac":
        cmd += ["-sample_fmt", "s16"]
    cmd.append(str(out))
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip().splitlines()[-1] if result.stderr else "FFmpeg failed")


def _finalize(task: DownloadTask, info: RecordingInfo, cfg: dict, ffmpeg: str, stem: str,
              fmt_info: Dict[str, Any]) -> None:
    """Encode, publish and tag the recording (runs in the background)."""
    status, progress = _hooks(task)
    ext = fmt_info["ext"]
    track = task.track
    try:
        status(DownloadStatus.CONVERTING)
        progress(0.92)
        _encode(ffmpeg, info, _work_dir(task) / f"{stem}.{ext}", fmt_info,
                track.duration_ms, bool(cfg.get("sp_normalize", False)))
        task.output_file = str(_publish_result(task, stem, ext))

        status(DownloadStatus.EMBEDDING)
        progress(0.97)
        cover = fetch_cover(track.cover_url) if cfg.get("sp_embed_cover", True) else None
        try:
            embed_metadata(filepath=task.output_file, ext=ext, title=track.title, artist=track.artist,
                           album=track.album, year=track.year, cover_data=cover)
        except Exception:
            pass

        status(DownloadStatus.DONE)
        progress(1.0)
    except Exception as exc:
        remove_partial_files(task)
        status(DownloadStatus.ERROR, str(exc))
        progress(0.0)
    if task.on_done:
        task.on_done(task)


def record_spotify_track(task: DownloadTask, session: Any,
                         spawn: Callable[[Callable[[], None]], None] = _spawn,
                         recorder_cls: Callable[..., Any] = ProcessRecorder,
                         ffmpeg_finder: Callable[[], Optional[str]] = find_ffmpeg) -> None:
    status, progress = _hooks(task)
    try:
        _check_stop(task)
        cfg = load_config()
        fmt_info = AUDIO_FORMATS[task.format_name]
        ext = fmt_info["ext"]
        track = task.track
        out_dir = Path(task.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        stem = _apply_template(cfg.get("sp_filename_template", "{artist} - {title}"),
                               artist=track.artist, title=track.title,
                               album=track.album, year=track.year or "")
        final_path = out_dir / f"{stem}.{ext}"
        if final_path.exists() and cfg.get("sp_skip_existing", True):
            task.output_file = str(final_path)
            status(DownloadStatus.DONE)
            progress(1.0)
            if task.on_done:
                task.on_done(task)
            return

        ffmpeg = ffmpeg_finder()
        if not ffmpeg:
            raise RecordError(T("err_rec_ffmpeg"))

        status(DownloadStatus.RECORDING)
        progress(0.0)
        session.ensure_ready()
        _check_stop(task)
        work = _make_work_dir(task)
        info = _record_track(task, session, work / "capture.f32", progress, recorder_cls)
    except TaskInterrupted as stop:
        _finish_interrupted(task, stop.reason, status, progress)
    except Exception as exc:
        remove_partial_files(task)
        status(DownloadStatus.ERROR, str(exc))
        progress(0.0)
        if task.on_done:
            task.on_done(task)
    else:
        spawn(lambda: _finalize(task, info, cfg, ffmpeg, stem, fmt_info))


class SpotifyRecordManager(_TaskManager):
    """One recording at a time (a Spotify account plays one stream at a time)."""

    def __init__(self, ffmpeg_ok: bool, session: Any):
        super().__init__(1, ffmpeg_ok)
        self._session = session

    def _run(self, task) -> None:
        record_spotify_track(task, self._session)
