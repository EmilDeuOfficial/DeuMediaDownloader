import json
import sys
import threading
import time
from pathlib import Path

import webview
from webview.window import FixPoint

HERE = Path(__file__).parent
report = {}


class SpikeApi:
    def __init__(self):
        self._window = None
        self._maximized = False

    def attach(self, window):
        self._window = window

    def minimize(self):
        self._window.minimize()

    def toggle_maximize(self):
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized

    def close(self):
        self._window.destroy()

    def set_size(self, w, h):
        self._window.resize(w, h)

    def get_rect(self):
        w = self._window
        return {"x": w.x, "y": w.y, "w": w.width, "h": w.height}

    def resize_to(self, w, h, fix):
        fp = FixPoint(0) if False else None
        flags = None
        if "E" in fix:
            flags = FixPoint.EAST
        if "S" in fix:
            flags = (flags | FixPoint.SOUTH) if flags else FixPoint.SOUTH
        if flags is None:
            flags = FixPoint.NORTH | FixPoint.WEST
        self._window.resize(int(w), int(h), flags)


def probe(window):
    """Exercise the window programmatically and record what happened."""
    time.sleep(2.5)
    try:
        report["initial"] = [window.width, window.height, window.x, window.y]
        window.resize(720, 360)
        time.sleep(0.5)
        report["after_resize_720x360"] = [window.width, window.height]
        window.resize(820, 720)
        time.sleep(0.5)
        report["after_resize_820x720"] = [window.width, window.height]
        window.resize(500, 400)
        time.sleep(0.5)
        report["after_resize_below_min"] = [window.width, window.height]
        window.move(100, 100)
        time.sleep(0.5)
        report["after_move"] = [window.x, window.y]
        window.maximize()
        time.sleep(0.7)
        report["after_maximize"] = [window.width, window.height]
        window.restore()
        time.sleep(0.7)
        report["after_restore"] = [window.width, window.height]
        window.minimize()
        time.sleep(0.5)
        window.restore()
        time.sleep(0.5)
        window.resize(820, 720)
        window.move(200, 150)
        time.sleep(0.6)
        report["before_drag"] = [window.x, window.y, window.width, window.height]
        js = '''
          (async () => {
            const drag = async (edge, dx, dy) => {
              const el = document.querySelector('.rz.' + edge);
              const r = el.getBoundingClientRect();
              const sx = screenX + r.left + r.width / 2, sy = screenY + r.top + r.height / 2;
              const opts = (x, y) => ({bubbles: true, pointerId: 1, screenX: x, screenY: y, clientX: r.left + 2, clientY: r.top + 2});
              el.dispatchEvent(new PointerEvent('pointerdown', opts(sx, sy)));
              await new Promise(r => setTimeout(r, 200));
              el.dispatchEvent(new PointerEvent('pointermove', opts(sx + dx, sy + dy)));
              await new Promise(r => setTimeout(r, 300));
              el.dispatchEvent(new PointerEvent('pointerup', opts(sx + dx, sy + dy)));
            };
            await drag('e', 60, 0);
            await drag('w', -40, 0);
            await drag('s', 0, 50);
            await drag('n', 0, -30);
            await drag('se', 20, 20);
            return 'done';
          })()
        '''
        report["js_drag"] = window.evaluate_js(js)
        time.sleep(5.0)
        report["after_drag"] = [window.x, window.y, window.width, window.height]
        report["dom_drag_regions"] = window.evaluate_js(
            "document.querySelectorAll('.pywebview-drag-region').length"
        )
        report["dom_inner"] = window.evaluate_js("[innerWidth, innerHeight]")
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        (HERE / "probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if "--keep" not in sys.argv:
            window.destroy()


def main():
    api = SpikeApi()
    window = webview.create_window(
        "Spike",
        str(HERE / "index.html"),
        js_api=api,
        width=820,
        height=720,
        min_size=(700, 600),
        frameless=True,
        easy_drag=False,
        resizable=True,
    )
    api.attach(window)
    threading.Thread(target=probe, args=(window,), daemon=True).start()
    webview.start()


if __name__ == "__main__":
    main()
