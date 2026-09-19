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
    e.emit("log", {})


def test_evaluate_js_failure_is_swallowed():
    e = Emitter()

    def boom(_):
        raise RuntimeError("window closed")

    e.attach(boom)
    e.emit("log", {})


def test_detach_stops_delivery():
    e, calls, _ = make()
    e.detach()
    e.emit("log", {})
    assert calls == []


def test_progress_throttled_per_task():
    e, calls, now = make()
    e.emit_progress("youtube", "t1", 0.10)
    now[0] = 0.05
    e.emit_progress("youtube", "t1", 0.20)
    e.emit_progress("youtube", "t2", 0.20)
    now[0] = 0.20
    e.emit_progress("youtube", "t1", 0.30)
    assert len(calls) == 3


def test_progress_completion_always_sent():
    e, calls, now = make()
    e.emit_progress("youtube", "t1", 0.10)
    now[0] = 0.01
    e.emit_progress("youtube", "t1", 1.0)
    assert len(calls) == 2
    payload = json.loads(calls[1].split(", ", 1)[1].rstrip(")"))
    assert payload == {"service": "youtube", "id": "t1", "progress": 1.0}


def test_payload_with_unicode_and_quotes_is_valid_json():
    e, calls, _ = make()
    e.emit("log", {"msg": 'He said "hi" – naïve'})
    body = calls[0][len('window.__bridge.emit("log", '):-1]
    assert json.loads(body) == {"msg": 'He said "hi" – naïve'}
