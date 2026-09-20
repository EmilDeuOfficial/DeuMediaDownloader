import json

import pytest

import config
from api import LAUNCHER_SIZE, Api, format_geometry, parse_geometry
from config import T


class RecEmitter:
    def __init__(self):
        self.events = []

    def emit(self, name, payload):
        self.events.append((name, payload))

    def emit_progress(self, *a):
        pass


class FakeRuntime:
    def __init__(self, service):
        self.service = service
        self.configured = []
        self.submitted = []
        self.cleared = 0

    def configure(self, cfg):
        self.configured.append(cfg)

    def submit(self, url, out_dir, fmt):
        self.submitted.append((url, out_dir, fmt))

    def clear_done(self):
        self.cleared += 1
        return ["x"]

    def tasks(self):
        return []

    def pause(self, task_id):
        self.calls = getattr(self, "calls", []) + [("pause", task_id)]
        return True

    def resume(self, task_id):
        self.calls = getattr(self, "calls", []) + [("resume", task_id)]
        return True

    def cancel(self, task_id):
        self.calls = getattr(self, "calls", []) + [("cancel", task_id)]
        return False


class FakeWindow:
    def __init__(self):
        self.x, self.y, self.width, self.height = 10, 20, 820, 720
        self.calls = []

    def resize(self, w, h, *a):
        self.calls.append(("resize", w, h))
        self.width, self.height = w, h

    def move(self, x, y):
        self.calls.append(("move", x, y))
        self.x, self.y = x, y

    def minimize(self):
        self.calls.append(("minimize",))

    def maximize(self):
        self.calls.append(("maximize",))

    def restore(self):
        self.calls.append(("restore",))

    def destroy(self):
        self.calls.append(("destroy",))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "data" / "config.json")
    rts = {s: FakeRuntime(s) for s in ("spotify", "youtube", "tiktok")}
    api = Api(RecEmitter(), rts, ffmpeg_ok=True, spawn=lambda fn: fn())
    win = FakeWindow()
    api.attach_window(win)
    api._screen_size = lambda: (1920, 1080)
    return api, rts, win, tmp_path


def test_geometry_roundtrip():
    assert format_geometry(820, 720, 10, 20) == "820x720+10+20"
    assert parse_geometry("820x720+10+20") == (820, 720, 10, 20)
    assert parse_geometry("820x720+-8+-8") == (820, 720, -8, -8)
    assert parse_geometry("+30+40") == (None, None, 30, 40)
    assert parse_geometry("") == (None, None, None, None)
    assert parse_geometry("garbage") == (None, None, None, None)


def test_bootstrap_contains_strings_config_and_options(env):
    api, rts, *_ = env
    res = api.bootstrap()
    assert res["ok"] is True
    d = res["data"]
    assert d["version"] == config.APP_VERSION
    assert d["strings"]["download"] == T("download")
    assert d["config"]["default_format"] == config.DEFAULT_CONFIG["default_format"]
    assert d["ffmpeg_ok"] is True
    assert "MP3 (320 kbps)" in d["options"]["audio_formats"]
    assert "MP4 (1080p)" in d["options"]["video_formats"]
    assert d["options"]["yt_templates"][0] == ["{title}", "tmpl_title_only"]
    assert set(d["tasks"]) == {"spotify", "youtube", "tiktok"}


def test_bootstrap_configures_runtimes_once(env):
    api, rts, *_ = env
    api.bootstrap()
    api.bootstrap()
    assert all(len(r.configured) == 1 for r in rts.values())


def test_save_config_merges_and_persists(env):
    api, rts, _, tmp = env
    api.save_config({"output_dir": "D:/music"})
    api.save_config({"yt_media_type": "Video"})
    saved = json.loads((tmp / "data" / "config.json").read_text(encoding="utf-8"))
    assert saved["output_dir"] == "D:/music"
    assert saved["yt_media_type"] == "Video"
    assert saved["default_format"] == config.DEFAULT_CONFIG["default_format"]
    assert all(r.configured == [] for r in rts.values())


def test_save_settings_reconfigures_only_that_service(env):
    api, rts, *_ = env
    res = api.save_settings("youtube", {"yt_concurrent": 4})
    assert res["ok"] and res["data"]["yt_concurrent"] == 4
    assert len(rts["youtube"].configured) == 1
    assert rts["youtube"].configured[0]["yt_concurrent"] == 4
    assert rts["spotify"].configured == [] and rts["tiktok"].configured == []


def test_unknown_service_returns_error_not_exception(env):
    api, *_ = env
    res = api.submit("vimeo", "http://x", "out", "MP3")
    assert res["ok"] is False and "vimeo" in res["error"]
    assert api.clear_done("vimeo")["ok"] is False
    assert api.save_settings("vimeo", {})["ok"] is False


def test_submit_rejects_empty_url_and_outdir(env):
    api, rts, *_ = env
    r1 = api.submit("youtube", "  ", "out", "MP3")
    assert r1["ok"] is False
    assert r1["error"] == T("mb_no_url_youtube")
    assert r1["title"] == T("mb_no_url_title")
    r2 = api.submit("youtube", "http://x", " ", "MP3")
    assert r2["error"] == T("mb_no_outdir") and r2["title"] == T("mb_no_outdir_title")
    assert rts["youtube"].submitted == []


def test_submit_forwards_trimmed_values(env):
    api, rts, *_ = env
    res = api.submit("youtube", " http://x ", " C:/out ", "MP3 (320 kbps)")
    assert res["ok"] is True
    assert rts["youtube"].submitted == [("http://x", "C:/out", "MP3 (320 kbps)")]


def test_clear_done_delegates(env):
    api, rts, *_ = env
    assert api.clear_done("tiktok") == {"ok": True, "data": ["x"]}
    assert rts["tiktok"].cleared == 1


def test_set_view_tool_uses_saved_geometry(env):
    api, rts, win, _ = env
    api.save_config({"yt_win_geo": "900x700+50+60"})
    assert api.set_view("youtube")["ok"]
    assert ("resize", 900, 700) in win.calls and ("move", 50, 60) in win.calls


def test_set_view_tool_defaults_to_centered_820x720(env):
    api, rts, win, _ = env
    api.set_view("spotify")
    assert ("resize", 820, 720) in win.calls
    assert ("move", (1920 - 820) // 2, (1080 - 720) // 2) in win.calls


def test_set_view_enforces_tool_minimum(env):
    api, rts, win, _ = env
    api.save_config({"tt_win_geo": "300x200+0+0"})
    api.set_view("tiktok")
    assert ("resize", 700, 600) in win.calls


def test_set_view_launcher_size_and_saved_position(env):
    api, rts, win, _ = env
    api.save_config({"launcher_pos": "+100+120"})
    api.set_view("launcher")
    assert ("resize", *LAUNCHER_SIZE) in win.calls and ("move", 100, 120) in win.calls


def test_leaving_a_view_saves_its_geometry(env):
    api, rts, win, tmp = env
    api.set_view("youtube")
    win.x, win.y, win.width, win.height = 5, 6, 800, 650
    api.set_view("launcher")
    saved = json.loads((tmp / "data" / "config.json").read_text(encoding="utf-8"))
    assert saved["yt_win_geo"] == "800x650+5+6"


def test_save_geometry_skips_while_maximized(env):
    api, rts, win, tmp = env
    api.set_view("spotify")
    api.save_geometry("spotify")
    api.toggle_maximize()
    win.width, win.height = 1920, 1080
    api.save_geometry("spotify")
    saved = json.loads((tmp / "data" / "config.json").read_text(encoding="utf-8"))
    assert saved["sp_win_geo"].startswith("820x720")


def test_toggle_maximize_and_minimize(env):
    api, rts, win, _ = env
    api.toggle_maximize()
    api.toggle_maximize()
    api.minimize()
    assert [c[0] for c in win.calls if c[0] in ("maximize", "restore", "minimize")] == [
        "maximize", "restore", "minimize"]


def test_close_saves_geometry_and_destroys(env):
    api, rts, win, tmp = env
    api.set_view("tiktok")
    api.close()
    assert win.calls[-1] == ("destroy",)
    saved = json.loads((tmp / "data" / "config.json").read_text(encoding="utf-8"))
    assert "tt_win_geo" in saved


def test_clear_data_removes_dir_and_blocks_later_saves(env):
    api, rts, win, tmp = env
    api.save_config({"output_dir": "D:/x"})
    data_dir = tmp / "data"
    assert data_dir.exists()
    assert api.clear_data()["ok"]
    assert not data_dir.exists()
    api.set_view("spotify")
    api.close()
    assert not data_dir.exists()


def test_exception_is_wrapped(env):
    api, rts, win, _ = env
    api._window = None
    res = api.minimize()
    assert res["ok"] is False and res["error"]


def test_get_rect(env):
    api, rts, win, _ = env
    assert api.get_rect() == {"ok": True, "data": {"x": 10, "y": 20, "w": 820, "h": 720}}


def test_resize_to_clamps_to_tool_minimum_and_sets_fix_point(env):
    from webview.window import FixPoint

    api, rts, win, _ = env
    seen = []
    win.resize = lambda w, h, *a: seen.append((w, h, a))
    api.set_view("spotify")
    seen.clear()
    api.resize_to(650, 500, "")
    api.resize_to(900, 800, "ES")
    assert seen[0] == (700, 600, (FixPoint.NORTH | FixPoint.WEST,))
    assert seen[1] == (900, 800, (FixPoint.EAST | FixPoint.SOUTH,))


def test_resize_to_ignored_in_launcher_and_when_maximized(env):
    api, rts, win, _ = env
    seen = []
    win.resize = lambda *a: seen.append(a)
    api.set_view("launcher")
    seen.clear()
    api.resize_to(900, 800, "")
    api.set_view("spotify")
    seen.clear()
    api.toggle_maximize()
    api.resize_to(900, 800, "")
    assert seen == []


def test_paste_returns_stripped_clipboard_text(env, monkeypatch):
    import clipboard
    monkeypatch.setattr(clipboard, "read_text", lambda: "  https://example.com/x \r\n")
    api, *_ = env
    assert api.paste() == {"ok": True, "data": "https://example.com/x"}


def test_bootstrap_includes_app_name(env):
    api, *_ = env
    assert api.bootstrap()["data"]["app_name"] == config.APP_NAME


def test_pause_resume_cancel_delegate_to_the_service_runtime(env):
    api, rts, *_ = env
    assert api.pause_task("spotify", "t1") == {"ok": True, "data": True}
    assert api.resume_task("spotify", "t1") == {"ok": True, "data": True}
    assert api.cancel_task("spotify", "t1") == {"ok": True, "data": False}
    assert rts["spotify"].calls == [("pause", "t1"), ("resume", "t1"), ("cancel", "t1")]


def test_task_control_with_unknown_service_returns_error(env):
    api, *_ = env
    for call in (api.pause_task, api.resume_task, api.cancel_task):
        res = call("vimeo", "t1")
        assert res["ok"] is False and "vimeo" in res["error"]


def test_bootstrap_offers_wiki_pages(env):
    api, *_ = env
    wiki = api.bootstrap()["data"]["options"]["wiki"]
    assert wiki == config.WIKI_PAGES
    assert all(url.startswith("https://github.com/") and "/wiki/" in url for url in wiki.values())


def test_toggle_maximize_reports_the_new_state(env):
    api, rts, win, _ = env
    assert api.toggle_maximize() == {"ok": True, "data": True}
    assert api.toggle_maximize() == {"ok": True, "data": False}


def test_leaving_a_maximized_view_restores_the_window(env):
    api, rts, win, _ = env
    api.set_view("youtube")
    api.toggle_maximize()
    api.set_view("launcher")
    assert ("restore",) in win.calls
    assert api.toggle_maximize()["data"] is True      # the next toggle maximizes again
