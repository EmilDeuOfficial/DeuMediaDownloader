# pywebview Frontend Rewrite - Design

Date: 2026-09-19
Branch: `gui`
Target version: 1.7.0

## Goal

Replace the CustomTkinter UI (`ui.py`, `assets.py`) with a frontend written in HTML,
CSS and JavaScript, hosted in a native window via pywebview. The Python backend stays.
The first release is a 1:1 port: same look, same flow, same features, same config file.

## Non-goals

- No redesign, no new features (a redesign can follow once the port is stable).
- No changes to download logic in `downloader.py` and `converter.py` beyond wiring.
- No JS framework and no frontend build step.

## Decision: host technology

pywebview (Python in-process, WebView2 on Windows).

- One process, one EXE. The PyInstaller and Inno Setup pipeline stays.
- JS calls Python directly (`window.pywebview.api.*`); Python pushes events with
  `window.evaluate_js`.
- Rejected: Electron with a Python sidecar (about 150 MB Chromium, two processes,
  IPC protocol, new build pipeline) and Tauri with a sidecar (needs a Rust toolchain,
  same sidecar cost, small gain for a 1:1 port). A local Flask/FastAPI server was
  rejected as well (port handling, more code, no benefit).

## Current state (findings)

- `ui.py` is 3166 lines (58% of the code base): three near-identical apps
  (Spotify, YouTube, TikTok), three settings dialogs, a launcher and a custom dropdown.
- Business logic lives in the UI: URL resolving (`_resolve_and_queue`), queue building,
  config persistence, "open folder when all tasks finished", uninstall actions.
- `downloader.py` is cleanly separable. Tasks and managers run in threads and report
  through the callbacks `on_progress`, `on_status`, `on_done`, which map directly to events.
- `config.py` mixes constants, UI colors (`COLORS`, `FONT_FAMILY`), about 320 lines of
  EN/DE strings and config IO.
- Tk-only workarounds disappear: `overrideredirect` title bar, Win11 rounding, taskbar
  button fix, scroll ghosting fix, `assets.py` (SVG to PIL via aggdraw).
- `DeuMediaDownloader.spec` is not tracked in git although `build.py` requires it.

## Architecture

Python owns config, URL resolving, tasks, queues and downloads. JS owns rendering and
input only.

```
main.py              create window, hand Api to it
api.py               thin class exposed to JS (window.pywebview.api)
events.py            emit(name, payload) -> evaluate_js, thread-safe
downloader.py        unchanged logic; callbacks wired to events by api.py
converter.py         unchanged
config.py            constants, strings, load/save; COLORS and FONT_FAMILY removed
frontend/
  index.html
  css/               base.css, components.css, views.css
  js/                main.js, bridge.js, store.js, i18n.js, settings-schema.js,
                     components/, views/
  img/               service SVGs (inlined by JS)
```

Removed: `ui.py`, `assets.py`, dependencies `customtkinter` and `aggdraw`.
Added: dependency `pywebview`.

### Api (JS to Python)

All methods return `{ok: true, data}` or `{ok: false, error}` and never raise across
the bridge.

- `bootstrap()` returns version, language, active string table, config, ffmpeg status and
  the static option lists (formats, filename templates, cookie browsers).
- `set_language(lang)` returns the new string table.
- `save_config(partial)` merges into the stored config and returns it.
- `submit(service, url, opts)` returns immediately; resolving and queuing run in a
  worker thread and report through events.
- `clear_done(service)`.
- `pick_folder(initial)` and `pick_file(kind)` use native pywebview dialogs.
- `open_folder(path)` and `open_url(url)`.
- Window: `minimize()`, `toggle_maximize()`, `close()`, `set_view(view)` (resizes the
  window between launcher and tool sizes), `save_geometry(view)`.
- Maintenance: `clear_data()`, `uninstall_ffmpeg()`, `uninstall_app()`
  (moved from the three settings dialogs; the confirm dialog is rendered by JS).

The Api owns one download manager per service and recreates it when the concurrency
setting changes, as `_init_client` does today. It also tracks tasks per service so
"open folder after all tasks finished" (`sp_open_folder`, `yt_open_folder`,
`tt_open_folder`) moves out of the UI.

### Events (Python to JS)

`log`, `task_added`, `task_status`, `task_progress`, `resolve_done`, `resolve_error`.
A task is serialized as `{id, service, name, status, progress, error}` where `status` is
the `DownloadStatus` name. Progress events are throttled per task (about 10 Hz, always
send 100%).

### Strings

One source of truth in Python. `bootstrap()` sends the active language dictionary and JS
uses `T(key)`. Backend messages that are shown to users (for example TikTok error
mapping) keep using `T()` on the Python side.

## Frontend

- One generic `ToolView` replaces the three copied apps. Each service is a descriptor:
  accent color, icon, URL placeholder, format lists, media-type toggle (YouTube and
  TikTok have Audio/Video, Spotify is audio only) and the config keys it reads.
- `settings-schema.js` describes sections and fields per service (toggle, slider 1 to 5,
  dropdown, secret input, file picker). One renderer builds all settings dialogs,
  including the shared "Uninstall" tab.
- Components: title bar (drag region, back, icon, gear, minimize, maximize, close),
  custom dropdown, queue item (name, status color, progress bar), log panel (colored
  lines, clear), modal and confirm dialog (replace `messagebox`).
- Look: values from `COLORS` become CSS custom properties, font Segoe UI, accent per
  service via `data-service`. Window sizes stay: launcher 720x360 fixed, tool 820x720
  with minimum 700x600. Geometry is stored per tool in the existing config keys
  (`sp_win_geo`, `tt_win_geo`, `launcher_pos`, ...), written in the same Tk-style string
  format so existing configs keep working.
- Vanilla ES modules. `bridge.js` waits for `pywebviewready` and dispatches events.
  `store.js` is a minimal observable. Text coming from the network (titles, artists) is
  only ever inserted with `textContent`. A CSP meta tag blocks external scripts.

## Config compatibility

Config location (`~/.spotify_downloader/config.json`), key names and defaults are
unchanged. `save_config` merges partial updates. No migration needed.

## Error handling

- Resolve errors: modal plus log line, same as today.
- Download errors: task status `ERROR` with message.
- Any exception inside an Api method is caught and returned as `{ok: false, error}`.
- `emit()` is a no-op once the window is closed.

## Testing

- Backend: pytest for the Api layer with fake managers (event order, `save_config`
  merge, string table, open-folder-when-done logic).
- Frontend: `node:test` for pure modules (`store`, `i18n`, formatters).
- Views: a `?mock=1` mode loads a simulated bridge so the UI can be checked in a browser
  and compared with screenshots of the current Tk app, without Python.
- Real downloads (network dependent) are verified manually.

## Build and release

- `requirements.txt`: remove `customtkinter`, `aggdraw`; add `pywebview`.
- Add a tracked `DeuMediaDownloader.spec` that bundles `frontend/` and `img/`.
- `installer.iss`: check for the WebView2 runtime via registry and install it silently
  if missing, following the existing FFmpeg step.
- `main.py`: drop the tkinter error dialog; report missing packages on the console.
- Bump `APP_VERSION` and `installer.iss` to 1.7.0, update the README.

## Rollout order

1. Spike: frameless window with drag, resize, minimize, maximize and size change between
   launcher and tool view. This decides whether the custom title bar is viable.
2. `api.py` and `events.py` with tests; move logic out of the UI.
3. Frontend shell, launcher and `ToolView` against the mock bridge.
4. Settings (schema and renderer).
5. Connect the real backend; delete `ui.py` and `assets.py`.
6. Build, spec file, installer, README, version bump.

## Risks

- Resize behavior of frameless pywebview windows (covered by step 1; fallback is a
  native resize border via the OS window style).
- WebView2 missing on Windows 10 (installer step).
- Many `evaluate_js` calls from worker threads (covered by throttling and a lock).
