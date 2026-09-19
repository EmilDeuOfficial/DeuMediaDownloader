# pywebview Frontend Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CustomTkinter UI with an HTML/CSS/JS frontend hosted by pywebview, keeping the Python backend and a 1:1 look and feature set.

**Architecture:** `api.py` (exposed to JS) delegates to one `ServiceRuntime` per service (`services.py`); runtimes push events through an `Emitter` (`events.py`) that calls `window.evaluate_js`. The frontend is vanilla ES modules; one generic `ToolView` is driven by three service descriptors and a settings schema.

**Tech Stack:** Python 3.12, pywebview >= 5, yt-dlp, spotipy, pytest; vanilla JS (ES modules), `node:test` (Node 24).

**Spec:** `docs/superpowers/specs/2026-09-19-pywebview-frontend-design.md`

## Global Constraints

- Config file `~/.spotify_downloader/config.json`, its key names and defaults are unchanged (`config.py` `DEFAULT_CONFIG`).
- Window sizes: launcher 720x360 fixed; tool 820x720, minimum 700x600. Geometry saved in Tk-style strings (`WxH+X+Y`) under `sp_win_geo`, `yt_win_geo`, `tt_win_geo`, `launcher_pos` (`+X+Y`).
- Colors and font are copied from `config.COLORS` and `FONT_FAMILY = "Segoe UI"`. Service accents: Spotify `#1DB954` (hover `#17a347`, dim `#145c30`), YouTube `#CC2222` (hover `#AA1111`, dim `#3a0a0a`), TikTok `#EE1D52` (hover `#C71542`).
- Text from the network is inserted with `textContent` only, never `innerHTML`.
- Every Api method returns `{"ok": True, "data": ...}` or `{"ok": False, "error": str}` and never raises.
- The Api object and everything hanging off it must be private (`_name`); pywebview walks public attributes.
- No emojis and no long dashes in code, comments and docs. Icons are inline SVG.
- Target version 1.7.0.

---

### Task 1: Frameless window spike

**Files:**
- Create: `spike/window_spike.py`, `spike/index.html`

**Produces:** A verdict, written as the first lines of `spike/RESULT.md`, on whether a frameless pywebview window supports: drag via `pywebview-drag-region`, edge resize, minimize, maximize/restore, and `resize()` between 720x360 and 820x720.

- [ ] **Step 1:** `pip install "pywebview>=5"`; verify with `python -c "import webview; print(webview.__version__)"`.
- [ ] **Step 2:** Write `spike/index.html` (custom bar with `pywebview-drag-region`, three buttons) and `spike/window_spike.py` (`webview.create_window(..., frameless=True, easy_drag=False, resizable=True, min_size=(700, 600))`, a `js_api` object with `minimize`, `toggle_maximize`, `close`, `set_size(w, h)`).
- [ ] **Step 3:** Run it; check each behavior programmatically (window `width/height/x/y`, `evaluate_js`) and visually where possible. Record result and any workaround in `spike/RESULT.md`.
- [ ] **Step 4:** Commit `spike/` (removed again in Task 8).

### Task 2: Event emitter

**Files:**
- Create: `events.py`, `tests/test_events.py`

**Produces:**
```python
class Emitter:
    def __init__(self, clock: Callable[[], float] = time.monotonic, min_interval: float = 0.1): ...
    def attach(self, evaluate_js: Callable[[str], Any]) -> None
    def detach(self) -> None
    def emit(self, name: str, payload: dict) -> None          # calls evaluate_js('window.__bridge.emit(<name-json>, <payload-json>)')
    def emit_progress(self, service: str, task_id: str, progress: float) -> None  # throttled per task, 1.0 always sent
```

- [ ] **Step 1: Write failing tests**
```python
import json
from events import Emitter

def make():
    calls, now = [], [0.0]
    e = Emitter(clock=lambda: now[0], min_interval=0.1)
    e.attach(calls.append)
    return e, calls, now

def test_emit_builds_bridge_call():
    e, calls, _ = make()
    e.emit("log", {"service": "spotify", "msg": "hi"})
    assert calls == ['window.__bridge.emit("log", {"service": "spotify", "msg": "hi"})']

def test_emit_without_window_is_noop():
    e = Emitter()
    e.emit("log", {})            # must not raise

def test_evaluate_js_failure_is_swallowed():
    e = Emitter()
    def boom(_): raise RuntimeError("window closed")
    e.attach(boom)
    e.emit("log", {})            # must not raise

def test_progress_throttled_per_task():
    e, calls, now = make()
    e.emit_progress("youtube", "t1", 0.10); now[0] = 0.05
    e.emit_progress("youtube", "t1", 0.20)     # dropped
    e.emit_progress("youtube", "t2", 0.20)     # other task, sent
    now[0] = 0.20
    e.emit_progress("youtube", "t1", 0.30)     # interval passed, sent
    assert len(calls) == 3

def test_progress_completion_always_sent():
    e, calls, now = make()
    e.emit_progress("youtube", "t1", 0.10); now[0] = 0.01
    e.emit_progress("youtube", "t1", 1.0)
    assert len(calls) == 2
    payload = json.loads(calls[1].split(", ", 1)[1].rstrip(")"))
    assert payload == {"service": "youtube", "id": "t1", "progress": 1.0}
```
- [ ] **Step 2:** `python -m pytest tests/test_events.py -v` -> FAIL (module missing).
- [ ] **Step 3:** Implement `events.py` with a lock around `evaluate_js`, a dict of last-send times keyed by `(service, task_id)`, and `emit_progress` sending event `task_progress`.
- [ ] **Step 4:** Run tests -> PASS.
- [ ] **Step 5:** `git add events.py tests/test_events.py && git commit -m "feat: add thread-safe event emitter"`

### Task 3: Service runtimes

**Files:**
- Create: `services.py`, `tests/test_services.py`
- Read for porting: `ui.py` `_resolve_and_queue`/`_queue_*` of the three apps, `_status_log_line`, `_yt_status_log_line`, `_tt_status_log_line`

**Consumes:** `Emitter` (Task 2); `downloader.*` managers, tasks and extractors; `config.T`, `load_config`.

**Produces:**
```python
SERVICE_IDS = ("spotify", "youtube", "tiktok")

def serialize_task(service: str, task) -> dict
    # {"id", "service", "name", "status": DownloadStatus.name, "progress": float, "error": str}

class ServiceRuntime:
    def __init__(self, spec: ServiceSpec, emitter: Emitter, ffmpeg_ok: bool,
                 opener: Callable[[str], None] = os.startfile): ...
    def configure(self, config: dict) -> None      # (re)builds manager when concurrency changes; Spotify: (re)builds client, logs init/auth error
    def submit(self, url: str, out_dir: str, fmt: str) -> None   # spawns worker thread; emits log/task_added/resolve_done/resolve_error
    def clear_done(self) -> list[str]              # removes DONE/ERROR tasks, returns their ids
    def tasks(self) -> list[dict]                  # serialized snapshot

def build_runtimes(emitter, ffmpeg_ok) -> dict[str, ServiceRuntime]
```
`ServiceSpec` (dataclass): `id`, `concurrency_key`, `open_folder_key`, `make_manager(n, ffmpeg_ok)`, `resolve(url, ctx) -> list[item]`, `make_task(item, out_dir, fmt) -> task`, `task_name(task) -> str`, `status_line(task) -> str`.

- [ ] **Step 1: Write failing tests** (fake spec with a fake manager that records submitted tasks and lets the test fire `on_status`/`on_progress`/`on_done`):
  - `test_submit_emits_added_then_done`: events are `log`, `task_added` per item, `resolve_done`.
  - `test_resolve_error_emits_resolve_error_and_log`: resolve raises `ValueError("boom")`; expect `resolve_error` with message `boom`, then `resolve_done` is NOT emitted.
  - `test_status_and_progress_forwarded`: firing callbacks emits `task_status` (with error text) and `task_progress`.
  - `test_open_folder_after_all_done`: with `open_folder_key` true, opener called once with `out_dir` only after the last of two tasks reports done; with the key false, never.
  - `test_clear_done_removes_only_finished`.
  - `test_configure_recreates_manager_only_when_concurrency_changes`.
- [ ] **Step 2:** Run -> FAIL.
- [ ] **Step 3:** Implement. Task callbacks are set to closures that call the emitter; `on_done` runs the open-folder check over this runtime's task dict. Copy log strings from the UI (`T("fetching_youtube")`, `T("queued_n_videos")`, `T("queued_n_tracks")`, `T("fetching_spotify")`, `T("log_queued")`, `T("err_resolving")`). Spotify spec: `resolve` handles YouTube URLs pasted into the Spotify field (`is_youtube_url`) exactly as `DeuMediaDownloaderApp._resolve_and_queue` does; raises `ValueError(T("no_credentials"))` if no client.
- [ ] **Step 4:** Run -> PASS.
- [ ] **Step 5:** Commit `feat: add per-service runtimes`.

### Task 4: Api

**Files:**
- Create: `api.py`, `tests/test_api.py`
- Modify: `config.py` (remove `COLORS`/`FONT_FAMILY` only after Task 8; add `strings_for(lang)` and `set_language(lang)` helpers now)

**Consumes:** `build_runtimes`, `Emitter`, `config.load_config/save_config`.

**Produces:** class `Api` with `__init__(self, emitter, runtimes, ffmpeg_ok, io=None)`, `attach_window(window)`, and methods `bootstrap()`, `set_language(lang)`, `save_config(partial)`, `submit(service, url, out_dir, fmt)`, `clear_done(service)`, `pick_folder(initial)`, `pick_file(kind)`, `open_folder(path)`, `open_url(url)`, `minimize()`, `toggle_maximize()`, `close()`, `set_view(view)`, `save_geometry(view)`, `clear_data()`, `uninstall_ffmpeg()`, `uninstall_app()`. `bootstrap()["data"]` keys: `version`, `lang`, `strings`, `config`, `ffmpeg_ok`, `options` (`audio_formats`, `video_formats`, `sp_templates`, `yt_templates`, `tt_templates`, `cookie_browsers` as ordered lists of `[value, label_key]` or names).

- [ ] **Step 1: Write failing tests** (temporary config file via monkeypatched `CONFIG_FILE`; fake window recording calls):
  - `test_bootstrap_contains_strings_and_config`
  - `test_save_config_merges_and_persists` (unrelated keys survive; runtimes are re-`configure`d)
  - `test_unknown_service_returns_error_not_exception`
  - `test_submit_rejects_empty_url_and_empty_outdir` (returns `ok False` with the existing `mb_no_url_*`/`mb_no_outdir` strings)
  - `test_set_view_resizes_window` (launcher -> 720x360, tool -> 820x720 or saved geometry)
  - `test_save_geometry_writes_tk_style_string`
  - `test_exception_in_method_is_wrapped` (decorator `_safe`)
- [ ] **Step 2:** Run -> FAIL.
- [ ] **Step 3:** Implement with a `_safe` decorator that wraps returns/exceptions. Maintenance methods are ported from `SettingsDialog._do_clear_data/_do_uninstall_ffmpeg/_do_uninstall_app/_find_uninstaller` (no dialogs; JS confirms first).
- [ ] **Step 4:** Run -> PASS.
- [ ] **Step 5:** Commit `feat: add pywebview Api layer`.

### Task 5: Frontend core and mock bridge

**Files:**
- Create: `frontend/index.html`, `frontend/css/base.css`, `frontend/js/main.js`, `frontend/js/bridge.js`, `frontend/js/store.js`, `frontend/js/i18n.js`, `frontend/js/mock-bridge.js`, `frontend/tests/store.test.mjs`, `frontend/tests/i18n.test.mjs`

**Produces (JS):**
```js
// store.js
export function createStore(initial)              // {get(), set(patch), subscribe(fn) -> unsubscribe}
// i18n.js
export function setStrings(dict); export function T(key, ...args)   // args replace "{}" in order; missing key returns the key
// bridge.js
export const api                                   // Proxy: api.method(...args) -> Promise<data>, throws Error(error) on ok:false
export function on(eventName, handler)             // returns unsubscribe
// window.__bridge.emit(name, payload) is called by Python
```
`mock-bridge.js` implements the same `api`/`on` surface in the browser (fake bootstrap, `submit` emits task events on timers), selected when the URL has `?mock=1` or `window.pywebview` is absent.

- [ ] **Step 1:** Write `store.test.mjs` and `i18n.test.mjs` (`node --test frontend/tests`).
- [ ] **Step 2:** Run -> FAIL.
- [ ] **Step 3:** Implement modules; write `base.css` with the color custom properties and `[data-service]` accent overrides.
- [ ] **Step 4:** `node --test frontend/tests` -> PASS.
- [ ] **Step 5:** Commit `feat: frontend core, store, i18n and mock bridge`.

### Task 6: Components, launcher and ToolView

**Files:**
- Create: `frontend/js/components/{titlebar,dropdown,queue-item,log-panel,modal}.js`, `frontend/js/views/{launcher,tool-view}.js`, `frontend/js/services.js` (three descriptors), `frontend/css/components.css`, `frontend/css/views.css`, `frontend/img/*.svg` (copied from `img/`)
- Modify: `frontend/js/main.js`

**Interfaces:** each component exports `create...(opts) -> HTMLElement` with an `update...` function where state changes; `services.js` exports `SERVICES = {spotify, youtube, tiktok}` with `{id, title, accent, accentHover, accentDim, icon, placeholderKey, urlLabelKey, mediaToggle: bool, cfg: {outDir, format, formatAudio, formatVideo, mediaType, openFolder}}`.

- [ ] **Step 1:** Build components and the launcher; match `ui.py` layout (46 px header, 16 px side padding, 10 px card radius, colors from Global Constraints).
- [ ] **Step 2:** Build `ToolView`: URL row with Paste/Clear, options panel (Spotify: format + save-to + Download; YouTube/TikTok: Audio/Video toggle, format, save-to + Download), queue panel with "clear finished" and item count, log panel with clear. Persist format/media type/out dir through `api.save_config` on change.
- [ ] **Step 3:** Serve `frontend/` (`python -m http.server` on a free port), open `?mock=1` in the built-in browser, drive it (launcher -> each tool -> submit -> progress -> done), check console for errors, compare against the Tk layout.
- [ ] **Step 4:** Commit `feat: launcher, tool view and components`.

### Task 7: Settings

**Files:**
- Create: `frontend/js/settings-schema.js`, `frontend/js/components/settings-modal.js`, `frontend/css/settings.css`
- Modify: `frontend/js/views/tool-view.js` (gear button opens the modal)

**Produces:** `SETTINGS_SCHEMA = {spotify: [...sections], youtube: [...], tiktok: [...]}`; section `{titleKey, fields: [{type: "toggle"|"slider"|"select"|"secret"|"text"|"file"|"readonly-copy"|"link", key, labelKey, descKey?, min?, max?, options?}]}`; plus shared `UNINSTALL_ROWS` (clear data, uninstall FFmpeg, uninstall app) with confirm modals. Sections and keys are ported from `SettingsDialog`, `YouTubeSettingsDialog`, `TikTokSettingsDialog` (`ui.py:306-680, 1341-1640, 2206-2545`).

- [ ] **Step 1:** Write the schema for all three services from the Tk dialogs (every key from `DEFAULT_CONFIG` that a dialog edits).
- [ ] **Step 2:** Renderer builds tabs ("Settings", "Uninstall"), cards, switches, slider, selects, secret input; Save calls `api.save_config` with only changed keys; Cancel discards.
- [ ] **Step 3:** Verify in `?mock=1` for all three services; confirm dialogs appear for the uninstall actions.
- [ ] **Step 4:** Commit `feat: schema-driven settings modal`.

### Task 8: Integrate, remove Tk, package

**Files:**
- Modify: `main.py`, `config.py`, `requirements.txt`, `build.py` (if needed), `installer.iss`, `README.md`, `.gitignore` (if needed)
- Create: `DeuMediaDownloader.spec`
- Delete: `ui.py`, `assets.py`, `spike/`

- [ ] **Step 1:** Rewrite `main.py`: dependency check without tkinter, `load_language()`, ffmpeg check, `Emitter`, `build_runtimes`, `Api`, `webview.create_window("DeuMediaDownloader", "frontend/index.html", js_api=api, frameless=True, easy_drag=False, resizable=True, min_size=(700, 600))`, `webview.start()`. Resolve `frontend/` through `sys._MEIPASS` when frozen.
- [ ] **Step 2:** Run the real app (`python main.py`), exercise launcher, settings save, a real short YouTube download if network allows.
- [ ] **Step 3:** Delete `ui.py`, `assets.py`, `spike/`; remove `COLORS`/`FONT_FAMILY` from `config.py`; `requirements.txt`: drop `customtkinter`, `aggdraw`, add `pywebview>=5`.
- [ ] **Step 4:** Write `DeuMediaDownloader.spec` (datas: `frontend`, `img`); add WebView2 registry check and silent install to `installer.iss`; bump `APP_VERSION` and `MyAppVersion` to 1.7.0; update README.
- [ ] **Step 5:** `python -m pytest -q` and `node --test frontend/tests` -> all pass; try `python build.py` up to the EXE step.
- [ ] **Step 6:** Commit `feat: v1.7.0 - HTML/CSS/JS frontend on pywebview`.

## Self-Review

- Spec coverage: architecture (Tasks 2-4), frontend components/descriptors/schema (5-7), config compatibility (constraints, Task 4), error handling (`_safe`, Task 3 errors), threading/throttling (Task 2), tests (2-5), build and installer (8), spike (1). All spec sections have a task.
- Names are consistent across tasks: `Emitter.emit/emit_progress`, `ServiceRuntime.submit/clear_done/configure/tasks`, `build_runtimes`, `Api` method names, `SERVICES`, `SETTINGS_SCHEMA`.
- Known simplification: full implementation code is not pasted for every task; tasks 2-4 include the tests that pin behavior and exact interfaces, frontend tasks are verified visually against the mock bridge.
