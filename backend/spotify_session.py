"""The hidden Spotify player used for recording.

A hidden pywebview window loads frontend/recorder.html, which runs Spotify's Web Playback
SDK. The SDK registers a player ("DeuMediaDownloader") on the user's Premium account; this
class logs the user in (OAuth in the default browser), starts a track on that player and
reports its state. The audio itself is captured by recorder.py.
"""
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from . import config
from .config import T, TOKEN_DIR
from .errors import RecordError
from .login_page import render_login_page
from .recorder import find_browser_pid, pid_alive

REDIRECT_URI = "http://127.0.0.1:8888/callback"
REC_SCOPES = ("streaming user-read-email user-read-private "
              "user-read-playback-state user-modify-playback-state")
_LOGIN_TIMEOUT = 300.0
_END_TOLERANCE_MS = 400
# The player is recorded almost silent: Chromium works in float, so a very low volume loses
# nothing and record.py amplifies the capture again. Spotify's loudness normalisation boosts quiet
# tracks and a limiter clips them at full volume (measured: 12% waveform error), while the
# capture stays exactly linear up to a volume of 0.3.
RECORD_VOLUME = 0.001


def _make_auth(client_id: str, client_secret: str) -> Any:
    from spotipy.oauth2 import SpotifyOAuth
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=REC_SCOPES,
        cache_path=str(TOKEN_DIR / f".spotify_record_token_{client_id}"),
        open_browser=False,
    )


def _make_api(token: str) -> Any:
    import spotipy
    return spotipy.Spotify(auth=token)


def _make_window(title: str, url: str, **kwargs) -> Any:
    import webview
    return webview.create_window(title, url, **kwargs)


_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020    # clicks go through the window
_WS_EX_TOOLWINDOW = 0x00000080     # no taskbar button, not in Alt+Tab
_WS_EX_APPWINDOW = 0x00040000      # forces a taskbar button, even together with TOOLWINDOW
_WS_EX_LAYERED = 0x00080000
_WS_EX_NOACTIVATE = 0x08000000     # never takes the focus
_LWA_ALPHA = 0x2
_SW_SHOWNOACTIVATE = 4


def _make_invisible(window: Any, wait: float = 5.0) -> None:
    """Show `window` in a way the user does not notice.

    Spotify's player only starts playing when its page is visible: in a hidden window the SDK
    stays in "loading" forever and no sound is produced. So the window is really shown, but fully
    transparent, click-through and without a taskbar button.
    """
    import ctypes
    deadline = time.monotonic() + wait
    native = getattr(window, "native", None)
    while native is None and time.monotonic() < deadline:
        time.sleep(0.05)
        native = getattr(window, "native", None)
    if native is None:
        window.show()
        return
    hwnd = native.Handle.ToInt32()
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
    style |= _WS_EX_LAYERED | _WS_EX_TRANSPARENT | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE
    style &= ~_WS_EX_APPWINDOW   # WinForms sets it for every top-level form: taskbar button
    user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)
    user32.SetLayeredWindowAttributes(hwnd, 0, 0, _LWA_ALPHA)   # alpha 0 = invisible
    # Not window.show(): that activates the window and takes the focus from the user's app.
    user32.ShowWindow(hwnd, _SW_SHOWNOACTIVATE)


class _CallbackServer:
    """Catches the redirect of Spotify's login page (http://127.0.0.1:8888/callback?code=...)."""

    def __init__(self) -> None:
        self.code: Optional[str] = None      # None after the redirect = Spotify did not grant access
        self.done = threading.Event()        # set by the redirect to /callback
        outer = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 5   # an idle speculative connection of the browser must not block the server

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path != "/callback":
                    self.send_error(404)   # favicon and the like
                    return
                outer.code = (parse_qs(parsed.query).get("code") or [None])[0]
                body = render_login_page(ok=bool(outer.code)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                outer.done.set()

            def log_message(self, *args):
                pass

        try:
            self._server = HTTPServer(("127.0.0.1", 8888), Handler)
        except OSError as exc:
            raise RecordError(T("err_rec_port")) from exc
        self._server.timeout = 0.5
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set() and not self.done.is_set():
            self._server.handle_request()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._server.server_close()


class _PageApi:
    """Exposed to recorder.html as window.pywebview.api (the page calls back into Python)."""

    def __init__(self, on_event: Callable[[str, dict], None], get_token: Callable[[], str]):
        self._on_event = on_event
        self._get_token = get_token

    def event(self, name: str, data: Optional[dict] = None) -> None:
        self._on_event(name, data or {})

    def token(self) -> str:
        return self._get_token()


class SpotifySession:
    def __init__(self, page_path: Path,
                 config_loader: Callable[[], dict] = config.load_config,
                 auth_factory: Callable[[str, str], Any] = _make_auth,
                 api_factory: Callable[[str], Any] = _make_api,
                 window_factory: Callable[..., Any] = _make_window,
                 pid_finder: Callable[[], Optional[int]] = find_browser_pid,
                 open_browser: Callable[[str], Any] = webbrowser.open):
        self._page = page_path
        self._config = config_loader
        self._auth_factory = auth_factory
        self._api_factory = api_factory
        self._window_factory = window_factory
        self._pid_finder = pid_finder
        self._open_browser = open_browser
        self._login_cancel = threading.Event()
        self._lock = threading.RLock()
        self._cond = threading.Condition()
        self._window: Any = None
        self._device_id: Optional[str] = None
        self._error: Optional[dict] = None
        self._state: dict = {}
        self._uri = ""
        self._played = False
        self._ended = False
        self._identity: Optional[dict] = None
        self._pid: Optional[int] = None
        self.diagnostics: deque = deque(maxlen=50)   # what the player page reported (troubleshooting)

    # ------------------------------------------------------------------ login
    def _auth(self) -> Any:
        cfg = self._config()
        client_id, client_secret = cfg.get("spotify_client_id", ""), cfg.get("spotify_client_secret", "")
        if not (client_id and client_secret):
            raise RecordError(T("no_credentials"))
        return self._auth_factory(client_id, client_secret)

    @staticmethod
    def _cached_token(auth: Any) -> Optional[dict]:
        try:
            return auth.validate_token(auth.cache_handler.get_cached_token())
        except Exception:
            return None

    def _access_token(self) -> str:
        token = self._cached_token(self._auth())
        if not token:
            raise RecordError(T("err_rec_login"))
        return token["access_token"]

    def status(self) -> dict:
        """{"logged_in": bool, "name": str, "premium": bool}; never raises."""
        empty = {"logged_in": False, "name": "", "premium": False}
        try:
            token = self._cached_token(self._auth())
        except RecordError:
            return empty
        if not token:
            return empty
        if self._identity is None:
            try:
                me = self._api_factory(token["access_token"]).me()
                self._identity = {"name": me.get("display_name") or me.get("id", ""),
                                  "premium": me.get("product") == "premium"}
            except Exception:
                return {"logged_in": True, "name": "", "premium": True}
        return {"logged_in": True, **self._identity}

    def login(self) -> dict:
        """Open Spotify's login page in the default browser; returns the status once it is done.

        The browser is redirected to http://127.0.0.1:8888/callback, which the callback server
        answers. Ends with an error after a timeout or when cancel_login() is called.
        """
        auth = self._auth()
        server = _CallbackServer()
        server.start()
        self._login_cancel.clear()
        try:
            self._open_browser(auth.get_authorize_url())
            deadline = time.monotonic() + _LOGIN_TIMEOUT
            while not server.done.is_set() and not self._login_cancel.is_set() and time.monotonic() < deadline:
                time.sleep(0.25)
            code = server.code
        finally:
            server.close()
        if not code:
            raise RecordError(T("err_rec_login_cancelled"))
        auth.get_access_token(code=code, as_dict=False, check_cache=False)
        self._identity = None
        return self.status()

    def cancel_login(self) -> None:
        self._login_cancel.set()

    def logout(self) -> dict:
        try:
            auth = self._auth()
            Path(auth.cache_handler.cache_path).unlink(missing_ok=True)
        except (RecordError, OSError, AttributeError):
            pass
        self._identity = None
        self.close()
        return self.status()

    # ----------------------------------------------------------------- player
    def _on_event(self, name: str, data: dict) -> None:
        with self._cond:
            if name == "ready":
                self._device_id = data.get("device_id")
            elif name == "not_ready":
                self._device_id = None
            elif name == "error":
                self._error = data
            elif name == "diag":
                self.diagnostics.append(f"{data.get('what')}: {data.get('detail')}")
            elif name == "state":
                self._apply_state(data)
            self._cond.notify_all()

    def _matches(self, state: dict) -> bool:
        """The state belongs to the requested track (Spotify may play a relinked version of it)."""
        return self._uri in (state.get("uri"), state.get("linked_uri"))

    def _apply_state(self, state: dict) -> None:
        if state.get("inactive"):
            # The player deactivated: this is how the end of the last track of its queue shows.
            if self._played:
                self._ended = True
            return
        self._state = state
        if not self._uri:
            return
        position = state.get("position", 0)
        duration = state.get("duration", 0)
        if self._matches(state):
            if not state.get("paused") and position > 0:
                self._played = True
            elif (self._played and state.get("paused")
                  and (position <= 0 or position >= duration - _END_TOLERANCE_MS)):
                self._ended = True
        elif self._played:
            self._ended = True

    def ensure_ready(self, timeout: float = 45.0) -> None:
        """Log-in check plus start of the hidden player; returns when the SDK device exists."""
        with self._lock:
            status = self.status()
            if not status["logged_in"]:
                raise RecordError(T("err_rec_login"))
            if not status["premium"]:
                raise RecordError(T("err_rec_premium"))
            if self._window is not None and self._device_id:
                return
            self.close()
            self._error = None
            api = _PageApi(self._on_event, self._access_token)
            self._window = self._window_factory("Recorder", str(self._page), js_api=api,
                                                hidden=True, width=400, height=300)
            _make_invisible(self._window)
            deadline = time.monotonic() + timeout
            with self._cond:
                while not self._device_id and not self._error and time.monotonic() < deadline:
                    self._cond.wait(0.5)
                error, device = self._error, self._device_id
            if not device:
                self.close()
                raise RecordError(self._describe(error) if error else T("err_rec_timeout"))

    def close(self) -> None:
        window, self._window = self._window, None
        self._device_id = None
        self._pid = None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass

    def browser_pid(self) -> int:
        """PID of the WebView2 browser process that plays the audio."""
        if self._pid is None or not pid_alive(self._pid):
            self._pid = self._pid_finder()
        if self._pid is None:
            raise RecordError(T("err_rec_no_capture"))
        return self._pid

    @staticmethod
    def _describe(error: dict) -> str:
        kind = error.get("kind", "")
        if kind == "account":
            return T("err_rec_premium")
        if kind == "initialization":
            return T("err_rec_drm")
        if kind == "authentication":
            return T("err_rec_login")
        return f"{T('err_rec_playback')} {error.get('message', '')}".strip()

    def play(self, track_id: str) -> None:
        import spotipy
        uri = f"spotify:track:{track_id}"
        with self._cond:
            self._uri, self._played, self._ended, self._state, self._error = uri, False, False, {}, None
        self._set_volume(RECORD_VOLUME)   # before the track starts, so nothing is heard
        api = self._api_factory(self._access_token())
        for attempt in range(5):
            try:
                api.start_playback(device_id=self._device_id, uris=[uri])
                return
            except spotipy.SpotifyException as exc:
                if exc.http_status == 404 and attempt < 4:
                    time.sleep(1.0)   # the Web API does not know the new device yet
                    continue
                if exc.http_status == 403:
                    raise RecordError(T("err_rec_premium")) from exc
                raise RecordError(f"{T('err_rec_playback')} {exc.msg}") from exc

    def _set_volume(self, value: float) -> None:
        window = self._window
        if window is not None:
            try:
                window.evaluate_js(f"window.recorder && window.recorder.setVolume({value})")
            except Exception:
                pass

    def pause(self) -> None:
        window = self._window
        if window is not None:
            try:
                window.evaluate_js("window.recorder && window.recorder.pause()")
            except Exception:
                pass

    def snapshot(self) -> Dict[str, Any]:
        """Playback progress of the current track: position and duration in ms, played, ended."""
        with self._cond:
            same = self._matches(self._state)
            return {
                "position": self._state.get("position", 0) if same else 0,
                "duration": self._state.get("duration", 0) if same else 0,
                "played": self._played,
                "ended": self._ended,
                "error": self._describe(self._error) if self._error else "",
            }
