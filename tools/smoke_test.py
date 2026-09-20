"""Start the real app (real pywebview window, real Api) against a throw-away config
folder, drive it through JS and print what happened. Nothing is downloaded.

Run from the project root:  python tools/smoke_test.py
"""
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="deumedia-smoke-"))
config.CONFIG_FILE = _tmp / "config.json"
config.LANGUAGE_FILE = _tmp / "language"

import main  # noqa: E402
import webview  # noqa: E402

report = {}


def js(window, code, default=None):
    try:
        return window.evaluate_js(code)
    except Exception as exc:
        report.setdefault("js_errors", []).append(f"{code[:60]}: {exc!r}")
        return default


def wait_for(window, code, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if js(window, code):
            return True
        time.sleep(0.25)
    return False


def probe(window):
    try:
        report["loaded"] = wait_for(window, "document.querySelectorAll('.view').length === 4")
        if not report["loaded"]:
            report["body"] = js(window, "document.body.innerText")
            return
        time.sleep(0.8)
        report["launcher_size"] = [window.width, window.height]
        report["launcher_visible"] = js(window, "!document.querySelector('.launcher-view').hidden")

        js(window, "[...document.querySelectorAll('.lc-open')].find(b => b.textContent.includes('YouTube')).click()")
        time.sleep(1.0)
        report["tool_size"] = [window.width, window.height]
        report["tool_visible"] = js(window, "!document.querySelector('.tool-view[data-service=\"youtube\"]').hidden")
        report["config_geo_saved"] = config.CONFIG_FILE.exists()

        # empty URL must produce the validation modal
        js(window, "document.querySelector('.tool-view[data-service=\"youtube\"] .download').click()")
        time.sleep(0.6)
        report["validation_modal"] = js(window, "document.querySelector('.modal-overlay .modal-body')?.textContent")
        js(window, "document.querySelector('.modal-overlay .btn')?.click()")

        # settings open + close
        js(window, "document.querySelector('.tool-view[data-service=\"youtube\"] .tb-btn[data-action=\"settings\"]').click()")
        time.sleep(0.4)
        report["settings_open"] = js(window, "!!document.querySelector('.settings-modal')")
        js(window, "document.querySelector('.settings-modal .sm-head .tb-btn').click()")

        # resize through the DOM handle (drives api.resize_to)
        before = [window.width, window.height]
        js(window, """
          (async () => {
            const el = document.querySelector('.rz.se');
            const r = el.getBoundingClientRect();
            const sx = screenX + r.left + 2, sy = screenY + r.top + 2;
            const o = (x, y) => ({bubbles: true, pointerId: 1, screenX: x, screenY: y});
            el.dispatchEvent(new PointerEvent('pointerdown', o(sx, sy)));
            await new Promise(r => setTimeout(r, 300));
            el.dispatchEvent(new PointerEvent('pointermove', o(sx + 40, sy + 30)));
            await new Promise(r => setTimeout(r, 400));
            el.dispatchEvent(new PointerEvent('pointerup', o(sx + 40, sy + 30)));
          })()
        """)
        time.sleep(1.5)
        report["resize"] = {"before": before, "after": [window.width, window.height]}

        # back to the launcher
        js(window, "document.querySelector('.tool-view[data-service=\"youtube\"] .tb-btn[data-action=\"back\"]').click()")
        time.sleep(1.0)
        report["back_size"] = [window.width, window.height]
        report["saved_keys"] = sorted(k for k in json.loads(config.CONFIG_FILE.read_text(encoding="utf-8")) if k.endswith("_geo") or k == "launcher_pos")
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        print(json.dumps(report, indent=2))
        if "--keep" not in sys.argv:
            window.destroy()


if __name__ == "__main__":
    ffmpeg_ok = main._check_ffmpeg()
    win = main.create_app(ffmpeg_ok)
    threading.Thread(target=probe, args=(win,), daemon=True).start()
    webview.start(http_server=True)
