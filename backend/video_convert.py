"""Converts a downloaded video into MOV or AVI with live progress.

yt-dlp's own converter runs ffmpeg with its default settings: a 4K source is re-encoded with
libx264 "medium" on the CPU, which takes far longer than the video itself and reports no
progress. This module runs ffmpeg itself instead:

- streams the target container can hold are copied, not re-encoded (seconds instead of minutes)
- a video that has to be re-encoded uses the graphics card (NVIDIA, Intel or AMD) when there is
  one, otherwise libx264 with a fast preset
- ffmpeg runs at "below normal" priority, so the PC stays usable
- the progress comes from ffmpeg's -progress output and can be cancelled at any time
"""
import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

log = logging.getLogger(__name__)

_CREATE_NO_WINDOW = 0x08000000
_BELOW_NORMAL_PRIORITY = 0x00004000

# Codecs each container takes as they are (a copy keeps the quality and costs no time).
_COPY_VIDEO = {
    "mov": {"h264", "hevc", "mpeg4", "prores", "mjpeg"},
    "avi": {"mpeg4", "msmpeg4v3", "mjpeg"},
}
_COPY_AUDIO = {
    "mov": {"aac", "mp3", "alac", "pcm_s16le", "pcm_s24le"},
    "avi": {"mp3", "ac3", "pcm_s16le"},
}

# Hardware H.264 encoders, fastest first; each is tried once with a tiny test clip.
_HW_ENCODERS = [
    ("h264_nvenc", ["-preset", "p3", "-rc", "vbr", "-cq", "21", "-b:v", "0"]),
    ("h264_qsv", ["-preset", "veryfast", "-global_quality", "22"]),
    ("h264_amf", ["-quality", "speed", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"]),
]
_SOFTWARE_H264 = ("libx264", ["-preset", "veryfast", "-crf", "20"])

_hw_lock = threading.Lock()
_hw_cache: dict = {}


class ConvertCancelled(Exception):
    """The task was paused or cancelled while ffmpeg was running."""


@dataclass
class MediaInfo:
    duration: float          # seconds, 0 when unknown
    video_codec: str
    audio_codec: str


def _run_quiet(cmd: List[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=_CREATE_NO_WINDOW)


def probe(ffmpeg: str, path: Path) -> MediaInfo:
    """Duration and codecs of `path` (ffmpeg prints them when called without an output)."""
    out = _run_quiet([ffmpeg, "-hide_banner", "-i", str(path)], timeout=60).stderr
    duration = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    video = re.search(r"Stream #\S+.*?: Video: (\w+)", out)
    audio = re.search(r"Stream #\S+.*?: Audio: (\w+)", out)
    return MediaInfo(duration, video.group(1) if video else "", audio.group(1) if audio else "")


def _encoder_works(ffmpeg: str, name: str, args: List[str]) -> bool:
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
           "-i", "color=c=black:s=1280x720:r=30:d=0.2", "-frames:v", "5",
           "-pix_fmt", "yuv420p", "-c:v", name, *args, "-f", "null", "-"]
    try:
        return _run_quiet(cmd, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def h264_encoder(ffmpeg: str) -> tuple:
    """(name, args) of the fastest H.264 encoder this PC has; checked once per ffmpeg."""
    with _hw_lock:
        if ffmpeg not in _hw_cache:
            found = next(((n, a) for n, a in _HW_ENCODERS if _encoder_works(ffmpeg, n, a)), None)
            _hw_cache[ffmpeg] = found or _SOFTWARE_H264
            log.info("H.264 encoder for conversions: %s", _hw_cache[ffmpeg][0])
        return _hw_cache[ffmpeg]


def _video_args(ffmpeg: str, target: str, info: MediaInfo, encoder: Optional[tuple]) -> List[str]:
    if info.video_codec in _COPY_VIDEO[target]:
        return ["-c:v", "copy"]
    if target == "avi":
        # AVI stays Xvid-compatible (MPEG-4 Part 2), which is fast to encode on the CPU.
        return ["-c:v", "mpeg4", "-vtag", "xvid", "-q:v", "3", "-pix_fmt", "yuv420p", "-threads", "0"]
    name, args = encoder or h264_encoder(ffmpeg)
    return ["-c:v", name, *args, "-pix_fmt", "yuv420p"]


def _audio_args(target: str, info: MediaInfo) -> List[str]:
    if not info.audio_codec:
        return []
    if info.audio_codec in _COPY_AUDIO[target]:
        return ["-c:a", "copy"]
    if target == "avi":
        return ["-c:a", "libmp3lame", "-b:a", "320k"]
    return ["-c:a", "aac", "-b:a", "256k"]


def build_command(ffmpeg: str, src: Path, dst: Path, info: MediaInfo,
                  hwaccel: bool = True, encoder: Optional[tuple] = None) -> List[str]:
    target = dst.suffix.lstrip(".").lower()
    video = _video_args(ffmpeg, target, info, encoder)
    decode = ["-hwaccel", "auto"] if hwaccel and video[1] != "copy" else []
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostats", "-y",
            *decode, "-i", str(src), "-map", "0:v:0?", "-map", "0:a:0?",
            *video, *_audio_args(target, info),
            "-progress", "pipe:1", str(dst)]


def _run(cmd: List[str], duration: float, on_progress: Callable[[float], None],
         should_stop: Callable[[], bool]) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace",
                            creationflags=_CREATE_NO_WINDOW | _BELOW_NORMAL_PRIORITY)
    errors: List[str] = []
    reader = threading.Thread(target=lambda: errors.extend(proc.stderr), daemon=True)
    reader.start()

    stopped = threading.Event()

    def watch() -> None:
        while proc.poll() is None:
            if should_stop():
                stopped.set()
                proc.kill()
                return
            time.sleep(0.2)

    threading.Thread(target=watch, daemon=True).start()
    for line in proc.stdout:
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and duration > 0 and value.isdigit():
            on_progress(min(int(value) / 1_000_000 / duration, 1.0))
    proc.wait()
    reader.join(timeout=2)
    if stopped.is_set():
        raise ConvertCancelled()
    if proc.returncode != 0:
        message = "".join(errors).strip().splitlines()
        raise RuntimeError(message[-1] if message else f"ffmpeg exited with code {proc.returncode}")


def convert(ffmpeg: str, src: Path, dst: Path, on_progress: Callable[[float], None],
            should_stop: Callable[[], bool], duration: float = 0.0) -> None:
    """Convert `src` into the container of `dst` (.mov or .avi), reporting 0.0 to 1.0."""
    info = probe(ffmpeg, src)
    total = info.duration or duration
    attempts = [build_command(ffmpeg, src, dst, info)]
    if "-hwaccel" in attempts[0]:
        # A hardware encoder or decoder can still fail on an unusual source: fall back to the CPU.
        attempts.append(build_command(ffmpeg, src, dst, info, hwaccel=False, encoder=_SOFTWARE_H264))
    for i, cmd in enumerate(attempts):
        try:
            _run(cmd, total, on_progress, should_stop)
            return
        except RuntimeError as exc:
            dst.unlink(missing_ok=True)
            if i == len(attempts) - 1:
                raise
            log.warning("Conversion with %s failed (%s), retrying on the CPU", cmd[cmd.index("-c:v") + 1], exc)
