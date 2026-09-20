from dataclasses import dataclass, field
from typing import Callable, Optional

import pytest

from config import T, WIKI_PAGES
from downloader import DownloadStatus
from services import ServiceRuntime, ServiceSpec, serialize_task


class RecEmitter:
    def __init__(self):
        self.events = []

    def emit(self, name, payload):
        self.events.append((name, payload))

    def emit_progress(self, service, task_id, progress):
        self.events.append(("task_progress", {"service": service, "id": task_id, "progress": progress}))

    def names(self):
        return [n for n, _ in self.events]

    def payloads(self, name):
        return [p for n, p in self.events if n == name]


@dataclass
class FakeTask:
    task_id: str
    title: str
    output_dir: str
    format_name: str
    status: DownloadStatus = DownloadStatus.QUEUED
    progress: float = 0.0
    error_msg: str = ""
    stop: Optional[str] = None
    run_id: int = 0
    on_progress: Optional[Callable] = field(default=None, repr=False)
    on_status: Optional[Callable] = field(default=None, repr=False)
    on_done: Optional[Callable] = field(default=None, repr=False)


class FakeManager:
    instances = []

    def __init__(self, n, ffmpeg_ok):
        self.n = n
        self.submitted = []
        FakeManager.instances.append(self)

    def submit(self, task):
        self.submitted.append(task)


def make_runtime(items=("a", "b"), resolve_exc=None, opened=None, open_flag=True):
    FakeManager.instances = []

    def resolve(url, ctx):
        ctx.log("fetching")
        if resolve_exc:
            raise resolve_exc
        return list(items)

    spec = ServiceSpec(
        id="youtube",
        concurrency_key="yt_concurrent",
        open_folder_key="yt_open_folder",
        make_manager=FakeManager,
        resolve=resolve,
        make_task=lambda item, out_dir, fmt: FakeTask(f"id-{item}", item, out_dir, fmt),
        task_name=lambda task, cfg: task.title.upper(),
        log_name=lambda task: task.title,
        queued_key="queued_n_videos",
    )
    em = RecEmitter()
    opened = opened if opened is not None else []
    rt = ServiceRuntime(spec, em, ffmpeg_ok=True, opener=opened.append,
                        spawn=lambda fn: fn())
    rt.configure({"yt_concurrent": 2, "yt_open_folder": open_flag})
    return rt, em, opened


def test_serialize_task_shape():
    spec = make_runtime()[0]._spec
    task = FakeTask("t1", "song", "out", "MP3", status=DownloadStatus.ERROR,
                    progress=0.4, error_msg="x" * 80)
    d = serialize_task(spec, task, {})
    assert d["id"] == "t1"
    assert d["service"] == "youtube"
    assert d["name"] == "SONG"
    assert d["status"] == "ERROR"
    assert d["progress"] == 0.4
    assert d["label"] == "Error: " + "x" * 45 + "\u2026"      # short version; d["error"] keeps everything
    assert d["error"] == "x" * 80


def test_serialize_label_for_normal_status():
    spec = make_runtime()[0]._spec
    task = FakeTask("t1", "song", "out", "MP3", status=DownloadStatus.DOWNLOADING)
    assert serialize_task(spec, task, {})["label"] == DownloadStatus.DOWNLOADING.value


def test_submit_emits_log_added_done():
    rt, em, _ = make_runtime()
    rt.submit("http://x", "out", "MP3 (320 kbps)")
    assert em.names() == ["log", "log", "task_added", "log", "task_added", "log", "resolve_done"]
    assert em.payloads("log")[0] == {"service": "youtube", "msg": "fetching"}
    assert em.payloads("log")[1]["msg"] == T("queued_n_videos").format(2, "MP3 (320 kbps)")
    added = em.payloads("task_added")
    assert [t["id"] for t in added] == ["id-a", "id-b"]
    assert added[0]["name"] == "A"
    assert [t.title for t in FakeManager.instances[-1].submitted] == ["a", "b"]


def test_resolve_error_emits_error_and_no_done():
    rt, em, _ = make_runtime(resolve_exc=ValueError("boom"))
    rt.submit("http://x", "out", "MP3")
    assert "resolve_done" not in em.names()
    assert em.payloads("resolve_error") == [
        {"service": "youtube", "message": "boom", "kind": "error"}
    ]
    assert any(p["msg"] == T("err_resolving").format("boom") for p in em.payloads("log"))


def test_status_and_progress_forwarded():
    rt, em, _ = make_runtime(items=("a",))
    rt.submit("http://x", "out", "MP3")
    task = FakeManager.instances[-1].submitted[0]
    task.status = DownloadStatus.DOWNLOADING
    task.on_status(task)
    task.progress = 0.5
    task.on_progress(task)
    st = em.payloads("task_status")[-1]
    assert st["status"] == "DOWNLOADING" and st["id"] == "id-a"
    assert em.payloads("task_progress")[-1] == {"service": "youtube", "id": "id-a", "progress": 0.5}
    assert any("a" in p["msg"] for p in em.payloads("log"))


def test_done_logs_and_emits_final_status():
    rt, em, _ = make_runtime(items=("a",))
    rt.submit("http://x", "out", "MP3")
    task = FakeManager.instances[-1].submitted[0]
    task.status = DownloadStatus.DONE
    task.progress = 1.0
    task.on_status(task)
    task.on_done(task)
    assert em.payloads("task_status")[-1]["progress"] == 1.0
    assert T("log_done").format("a") in [p["msg"] for p in em.payloads("log")]


def test_open_folder_after_all_done():
    rt, em, opened = make_runtime()
    rt.submit("http://x", "C:/out", "MP3")
    t1, t2 = FakeManager.instances[-1].submitted
    t1.status = DownloadStatus.DONE
    t1.on_done(t1)
    assert opened == []
    t2.status = DownloadStatus.ERROR
    t2.on_done(t2)
    assert opened == ["C:/out"]


def test_open_folder_disabled():
    rt, em, opened = make_runtime(open_flag=False)
    rt.submit("http://x", "C:/out", "MP3")
    for t in FakeManager.instances[-1].submitted:
        t.status = DownloadStatus.DONE
        t.on_done(t)
    assert opened == []


def test_clear_done_removes_only_finished():
    rt, em, _ = make_runtime()
    rt.submit("http://x", "out", "MP3")
    t1, t2 = FakeManager.instances[-1].submitted
    t1.status = DownloadStatus.DONE
    removed = rt.clear_done()
    assert removed == ["id-a"]
    assert [t["id"] for t in rt.tasks()] == ["id-b"]


def test_configure_recreates_manager_only_when_concurrency_changes():
    rt, em, _ = make_runtime()
    assert len(FakeManager.instances) == 1
    rt.configure({"yt_concurrent": 2, "yt_open_folder": True})
    assert len(FakeManager.instances) == 1
    rt.configure({"yt_concurrent": 4, "yt_open_folder": True})
    assert len(FakeManager.instances) == 2
    assert FakeManager.instances[-1].n == 4


def test_missing_client_emits_api_error_without_resolving():
    rt, em, _ = make_runtime()
    rt._spec.needs_client = True
    rt._client = None
    rt.submit("http://x", "out", "MP3")
    assert em.payloads("resolve_error") == [
        {"service": "youtube", "message": T("mb_api_msg").format(WIKI_PAGES["spotify_api"]), "kind": "api"}
    ]
    assert "log" not in em.names()


def test_spotify_resolve_dispatches_by_kind():
    from services import ResolveContext, _spotify_resolve

    class FakeClient:
        def parse_url(self, url):
            return url.split("|")

        def get_track_info(self, i):
            return f"track:{i}"

        def get_playlist_tracks(self, i):
            return [f"pl:{i}"]

        def get_album_tracks(self, i):
            return [f"al:{i}"]

    logs = []
    ctx = ResolveContext(log=logs.append, client=FakeClient(), config={})
    assert _spotify_resolve("track|1", ctx) == ["track:1"]
    assert _spotify_resolve("playlist|2", ctx) == ["pl:2"]
    assert _spotify_resolve("album|3", ctx) == ["al:3"]
    assert logs == [T("fetching_spotify").format(k) for k in ("track", "playlist", "album")]
    with pytest.raises(ValueError):
        _spotify_resolve("show|4", ctx)
    with pytest.raises(ValueError):
        _spotify_resolve("track|1", ResolveContext(log=logs.append, client=None, config={}))


def test_status_label_and_log_line_follow_active_language(monkeypatch):
    import config
    monkeypatch.setattr(config, "_lang", "de")
    spec = make_runtime()[0]._spec
    task = FakeTask("t1", "song", "out", "MP3", status=DownloadStatus.DOWNLOADING)
    assert serialize_task(spec, task, {})["label"] == T("status_downloading")
    assert serialize_task(spec, task, {})["label"] != DownloadStatus.DOWNLOADING.value
    task.status = DownloadStatus.ERROR
    task.error_msg = "boom"
    assert serialize_task(spec, task, {})["label"] == T("status_error") + ": boom"


# ------------------------------------------------------------ pause / resume / cancel
def queued_runtime(n=2, **kw):
    rt, em, opened = make_runtime(items=tuple("abcdef"[:n]), **kw)
    rt.submit("http://x", "C:/out", "MP3")
    return rt, em, opened, FakeManager.instances[-1].submitted


def test_pause_waiting_task_pauses_immediately_and_sets_stop_flag():
    rt, em, _, tasks = queued_runtime()
    assert rt.pause("id-a") is True
    assert tasks[0].stop == "pause"
    assert tasks[0].status == DownloadStatus.PAUSED
    assert em.payloads("task_status")[-1]["status"] == "PAUSED"


def test_pause_running_task_only_sets_flag_the_worker_reports_the_state():
    rt, em, _, tasks = queued_runtime()
    tasks[0].status = DownloadStatus.DOWNLOADING
    assert rt.pause("id-a") is True
    assert tasks[0].stop == "pause"
    assert tasks[0].status == DownloadStatus.DOWNLOADING


@pytest.mark.parametrize("status", [DownloadStatus.CONVERTING, DownloadStatus.EMBEDDING,
                                    DownloadStatus.DONE, DownloadStatus.ERROR])
def test_pause_and_cancel_ignored_in_non_interruptible_states(status):
    rt, em, _, tasks = queued_runtime()
    tasks[0].status = status
    assert rt.pause("id-a") is False
    assert rt.cancel("id-a") is False
    assert tasks[0].stop is None


def test_unknown_task_id_returns_false():
    rt, *_ = queued_runtime()
    assert rt.pause("nope") is False and rt.resume("nope") is False and rt.cancel("nope") is False


def test_resume_requeues_paused_task_and_clears_flag():
    rt, em, _, tasks = queued_runtime()
    rt.pause("id-a")
    submitted_before = len(FakeManager.instances[-1].submitted)
    assert rt.resume("id-a") is True
    assert tasks[0].stop is None
    assert tasks[0].status == DownloadStatus.QUEUED
    assert len(FakeManager.instances[-1].submitted) == submitted_before + 1
    assert FakeManager.instances[-1].submitted[-1] is tasks[0]


def test_resume_only_works_for_paused_tasks():
    rt, _, _, tasks = queued_runtime()
    assert rt.resume("id-a") is False


def test_cancel_waiting_task_finishes_it_as_cancelled():
    rt, em, _, tasks = queued_runtime()
    tasks[0].progress = 0.4
    assert rt.cancel("id-a") is True
    assert tasks[0].stop == "cancel"
    assert tasks[0].status == DownloadStatus.CANCELLED
    assert tasks[0].progress == 0.0
    assert em.payloads("task_status")[-1]["status"] == "CANCELLED"


def test_cancel_paused_task_removes_partial_files(tmp_path):
    rt, em, _, tasks = queued_runtime()
    tasks[0].output_dir = str(tmp_path)
    work = tmp_path / f".dmd-{tasks[0].task_id[:8]}"
    work.mkdir()
    (work / "song.webm.part").write_bytes(b"x")
    (tmp_path / "song.mp3").write_bytes(b"x")
    rt.pause("id-a")
    assert rt.cancel("id-a") is True
    assert sorted(p.name for p in tmp_path.iterdir()) == ["song.mp3"]


def test_cancel_running_task_only_sets_flag():
    rt, em, _, tasks = queued_runtime()
    tasks[0].status = DownloadStatus.DOWNLOADING
    assert rt.cancel("id-a") is True
    assert tasks[0].stop == "cancel"
    assert tasks[0].status == DownloadStatus.DOWNLOADING


def test_cancelled_tasks_count_as_finished_for_clear_and_open_folder():
    rt, em, opened, tasks = queued_runtime()
    tasks[0].status = DownloadStatus.DONE
    tasks[0].on_done(tasks[0])
    assert opened == []
    rt.cancel("id-b")                       # cancelling the last open task finishes the batch
    assert opened == ["C:/out"]
    assert sorted(rt.clear_done()) == ["id-a", "id-b"]


def test_paused_task_blocks_open_folder_until_resolved():
    rt, em, opened, tasks = queued_runtime()
    tasks[0].status = DownloadStatus.DONE
    tasks[0].on_done(tasks[0])
    rt.pause("id-b")
    assert opened == []
    assert rt.clear_done() == ["id-a"]      # the paused task stays in the queue


def test_on_done_is_handled_once_per_task_even_if_reported_twice():
    rt, em, opened, tasks = queued_runtime(n=1)
    rt.cancel("id-a")
    tasks[0].on_done(tasks[0])              # worker reports the same cancel a second time
    assert opened == ["C:/out"]


def test_paused_label_follows_active_language(monkeypatch):
    import config
    monkeypatch.setattr(config, "_lang", "de")
    rt, em, _, tasks = queued_runtime()
    rt.pause("id-a")
    assert em.payloads("task_status")[-1]["label"] == T("status_paused")


def test_queue_label_is_short_but_log_and_task_keep_the_full_error(capsys):
    rt, em, _ = make_runtime(items=("a",))
    rt.submit("http://x", "out", "MP3 (320 kbps)")
    task = FakeManager.instances[-1].submitted[0]
    full = "ERROR: [youtube] abc: unable to download video data: HTTP Error 403: Forbidden (long details " + "y" * 200 + ")"
    task.status = DownloadStatus.ERROR
    task.error_msg = full
    task.on_status(task)
    status = em.payloads("task_status")[-1]
    assert status["label"] == "Error: HTTP error 403"
    assert status["error"] == full                               # full text for the tooltip
    assert T("log_error").format("a", full) in [p["msg"] for p in em.payloads("log")]
    assert full in capsys.readouterr().err                      # and on stderr


def test_no_stderr_output_for_normal_status(capsys):
    rt, em, _ = make_runtime(items=("a",))
    rt.submit("http://x", "out", "MP3 (320 kbps)")
    task = FakeManager.instances[-1].submitted[0]
    task.status = DownloadStatus.DOWNLOADING
    task.on_status(task)
    assert capsys.readouterr().err == ""
