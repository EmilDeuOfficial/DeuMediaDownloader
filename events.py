import json
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple


class Emitter:
    """Pushes events from Python threads to the JS side of the pywebview window.

    JS receives them in `window.__bridge.emit(name, payload)`.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 min_interval: float = 0.1):
        self._clock = clock
        self._min_interval = min_interval
        self._evaluate_js: Optional[Callable[[str], Any]] = None
        self._lock = threading.Lock()
        self._last_progress: Dict[Tuple[str, str], float] = {}

    def attach(self, evaluate_js: Callable[[str], Any]) -> None:
        self._evaluate_js = evaluate_js

    def detach(self) -> None:
        self._evaluate_js = None

    def emit(self, name: str, payload: dict) -> None:
        fn = self._evaluate_js
        if fn is None:
            return
        script = f"window.__bridge.emit({json.dumps(name)}, {json.dumps(payload)})"
        with self._lock:
            try:
                fn(script)
            except Exception:
                # Window closed or page not ready; events are best effort.
                pass

    def emit_progress(self, service: str, task_id: str, progress: float) -> None:
        key = (service, task_id)
        now = self._clock()
        last = self._last_progress.get(key)
        finished = progress >= 1.0
        if not finished and last is not None and now - last < self._min_interval:
            return
        self._last_progress[key] = now
        self.emit("task_progress", {"service": service, "id": task_id, "progress": progress})
