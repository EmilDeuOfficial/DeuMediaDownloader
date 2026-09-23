"""Records the audio of the hidden Spotify window into a raw float32 file.

Windows 10 (2004 and newer) can capture the audio of one process tree only (WASAPI
process loopback, wrapped by the proc-tap package), so nothing else the PC plays ends up in
the recording and the volume slider does not change it.

WebView2 does not start its processes as children of the app, so the app's own PID is no use;
the browser process is found by the user data folder it was started with.
"""
import subprocess
import threading
import time
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Union

from .errors import RecordError

_CREATE_NO_WINDOW = 0x08000000
_LIST_PROCESSES = (
    "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
    "Get-CimInstance Win32_Process -Filter \"Name='msedgewebview2.exe'\" | "
    "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"
)


def _pywebview_cache_dir() -> Optional[str]:
    """The user data folder pywebview created its WebView2 windows with.

    pywebview sets this itself (a private module global, set once for the app's main window and
    reused for every window after) when running in private mode with no fixed storage path,
    which is what main.py uses; there is no public API for it. Reading it here means the app does
    not have to pin its own path (that would force WebView2 to keep a persistent, ever-growing
    HTTP cache across runs, which also holds stale copies of the app's own frontend files).
    """
    try:
        from webview.platforms import winforms
        return winforms.cache_dir
    except Exception:
        return None


def find_browser_pid(data_dir: Union[Path, str, None] = None) -> Optional[int]:
    """PID of the WebView2 browser process whose user data folder is `data_dir`

    (pywebview's own folder by default; see _pywebview_cache_dir)."""
    needle = str(data_dir or _pywebview_cache_dir() or "").lower()
    if not needle:
        return None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _LIST_PROCESSES],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        pid, _, cmdline = line.partition("\t")
        lowered = cmdline.lower()
        if pid.strip().isdigit() and needle in lowered and "--type=" not in lowered:
            return int(pid)
    return None


def pid_alive(pid: int) -> bool:
    """True while process `pid` is running. (os.kill must not be used: on Windows it terminates.)"""
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel32.CloseHandle(handle)


@dataclass
class RecordingInfo:
    path: Path
    sample_rate: int
    channels: int
    bytes_written: int
    peak: float   # loudest sample, 0.0 to 1.0

    @property
    def seconds(self) -> float:
        frame = self.channels * 4
        return self.bytes_written / (frame * self.sample_rate) if frame and self.sample_rate else 0.0


def _native_capture(pid: int) -> Any:
    try:
        from proctap._native import ProcessLoopback
    except ImportError as exc:
        raise RecordError("Audio capture is not available (install proc-tap).") from exc
    try:
        return ProcessLoopback(pid)
    except RuntimeError as exc:
        raise RecordError(f"Audio capture failed: {exc}") from exc


def _peak(chunk: bytes) -> float:
    samples = array("f")
    samples.frombytes(chunk[: len(chunk) // 4 * 4])
    if not samples:
        return 0.0
    return max(max(samples), -min(samples))


class ProcessRecorder:
    """Writes the captured audio (48 kHz, 2 channels, float32, native WASAPI format) to `path`."""

    def __init__(self, pid: int, path: Path,
                 capture_factory: Optional[Callable[[int], Any]] = None):
        self._pid = pid
        self._path = path
        self._factory = capture_factory or _native_capture
        self._cap: Any = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._peak = 0.0
        self._bytes = 0
        self._format = {"sample_rate": 48000, "channels": 2, "bits_per_sample": 32}

    def start(self) -> None:
        self._cap = self._factory(self._pid)
        self._format = dict(self._cap.get_format())
        if self._format.get("bits_per_sample") != 32:
            raise RecordError(f"Unexpected capture format: {self._format}")
        file = open(self._path, "wb")
        try:
            self._cap.start()
        except Exception as exc:
            file.close()
            raise RecordError(f"Audio capture failed: {exc}") from exc
        self._thread = threading.Thread(target=self._pump, args=(file,), daemon=True)
        self._thread.start()

    def _pump(self, file) -> None:
        try:
            while not self._stop.is_set():
                data = self._cap.read()
                if not data:
                    time.sleep(0.01)
                    continue
                file.write(data)
                level = _peak(data)
                with self._lock:
                    self._bytes += len(data)
                    self._peak = max(self._peak, level)
        finally:
            file.close()

    @property
    def peak(self) -> float:
        with self._lock:
            return self._peak

    def stop(self) -> RecordingInfo:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        try:
            self._cap.stop()
        except Exception:
            pass
        with self._lock:
            return RecordingInfo(
                path=self._path,
                sample_rate=int(self._format.get("sample_rate", 48000)),
                channels=int(self._format.get("channels", 2)),
                bytes_written=self._bytes,
                peak=self._peak,
            )
