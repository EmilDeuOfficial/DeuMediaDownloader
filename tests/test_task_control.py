import threading
import time

import pytest

import config
import downloader as d
from downloader import DownloadStatus, TaskInterrupted, YouTubeTask, _TaskManager, remove_partial_files


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def make_task(tmp_path, task_id="t1-abcdef", **kw):
    return YouTubeTask(task_id=task_id, url="http://x", title="Artist - Song", output_dir=str(tmp_path),
                       format_name="MP3 (320 kbps)", **kw)


def put(folder, *names):
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"x")


# ------------------------------------------------------------------- work folder
def test_work_folders_of_two_tasks_with_the_same_title_differ(tmp_path):
    """One song in two formats used to write the same temp file and fail with WinError 32."""
    a, b = make_task(tmp_path, "aaaaaaaa-1"), make_task(tmp_path, "bbbbbbbb-2")
    assert d._work_dir(a) != d._work_dir(b)
    assert d._work_dir(a).parent == tmp_path


def test_remove_partial_files_deletes_only_the_work_folder_of_this_task(tmp_path):
    task, other = make_task(tmp_path, "aaaaaaaa-1"), make_task(tmp_path, "bbbbbbbb-2")
    put(d._work_dir(task), "song.webm.part", "song.webp")
    put(d._work_dir(other), "song.webm.part")
    put(tmp_path, "song.mp3")
    remove_partial_files(task)
    assert not d._work_dir(task).exists()
    assert (d._work_dir(other) / "song.webm.part").exists()
    assert (tmp_path / "song.mp3").exists()


def test_remove_partial_files_without_work_folder_is_noop(tmp_path):
    remove_partial_files(make_task(tmp_path))


def test_has_partial_files_only_counts_unfinished_downloads(tmp_path):
    task = make_task(tmp_path)
    assert d._has_partial_files(task) is False
    put(d._work_dir(task), "song.webm")
    assert d._has_partial_files(task) is False
    put(d._work_dir(task), "song.webm.part")
    assert d._has_partial_files(task) is True


def test_publish_result_moves_the_file_next_to_the_downloads_and_removes_the_work_folder(tmp_path):
    task = make_task(tmp_path)
    put(d._work_dir(task), "song.mp3", "song.webp")
    final = d._publish_result(task, "song", "mp3")
    assert final == tmp_path / "song.mp3"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["song.mp3"]


def test_publish_result_overwrites_an_older_file(tmp_path):
    task = make_task(tmp_path)
    (tmp_path / "song.mp3").write_bytes(b"old")
    put(d._work_dir(task), "song.mp3")
    d._publish_result(task, "song", "mp3")
    assert (tmp_path / "song.mp3").read_bytes() == b"x"


def test_publish_result_takes_the_other_container_when_the_expected_one_is_missing(tmp_path):
    task = make_task(tmp_path)
    put(d._work_dir(task), "song.webm", "song.webp", "song.webm.part")
    assert d._publish_result(task, "song", "mp3") == tmp_path / "song.webm"


def test_publish_result_handles_glob_characters_in_the_name(tmp_path):
    task = make_task(tmp_path)
    put(d._work_dir(task), "a [b].webm", "a b.webm")
    assert d._publish_result(task, "a [b]", "mp3") == tmp_path / "a [b].webm"


def test_publish_result_without_a_file_raises_file_not_found(tmp_path):
    task = make_task(tmp_path)
    put(d._work_dir(task), "song.webm.part")
    with pytest.raises(FileNotFoundError, match="Downloaded file not found"):
        d._publish_result(task, "song", "mp3")


# ---------------------------------------------------------------------- manager
class RecordingManager(_TaskManager):
    def __init__(self, gate, **kw):
        self.ran = []
        self._gate = gate
        super().__init__(**kw)

    def _run(self, task):
        self.ran.append(task.task_id)
        if task.task_id == "first":
            self._gate.wait(3)


def task_named(tmp_path, name):
    t = make_task(tmp_path)
    t.task_id = name
    return t


def test_paused_task_waiting_in_queue_is_skipped_and_runs_once_after_resume(tmp_path):
    gate = threading.Event()
    mgr = RecordingManager(gate, max_workers=1)
    first, second = task_named(tmp_path, "first"), task_named(tmp_path, "second")
    mgr.submit(first)
    assert wait_for(lambda: mgr.ran == ["first"])
    mgr.submit(second)
    second.stop = "pause"                      # paused while it waits for a free worker
    gate.set()
    time.sleep(0.5)
    assert mgr.ran == ["first"]                # skipped
    second.stop = None                         # resume = clear the flag and submit again
    mgr.submit(second)
    assert wait_for(lambda: mgr.ran == ["first", "second"])
    time.sleep(0.5)
    assert mgr.ran == ["first", "second"]      # the stale queue entry did not start it twice


def test_cancelled_task_waiting_in_queue_never_runs(tmp_path):
    gate = threading.Event()
    mgr = RecordingManager(gate, max_workers=1)
    first, second = task_named(tmp_path, "first"), task_named(tmp_path, "second")
    mgr.submit(first)
    assert wait_for(lambda: mgr.ran == ["first"])
    mgr.submit(second)
    second.stop = "cancel"
    gate.set()
    time.sleep(0.5)
    assert mgr.ran == ["first"]


# ---------------------------------------------------- download function behaviour
class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: feeds one 'downloading' progress event to the hook."""
    hook_calls = 0

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        FakeYDL.hook_calls += 1
        self.opts["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 10, "total_bytes": 100})
        self.opts["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "cfg" / "config.json")
    monkeypatch.setattr(d.yt_dlp, "YoutubeDL", FakeYDL)
    FakeYDL.hook_calls = 0
    out = tmp_path / "out"
    return out


def run_youtube(out, stop_when_hook=None):
    events = []
    task = YouTubeTask(task_id="t1", url="http://x", title="Artist - Song", output_dir=str(out),
                       format_name="MP3 (320 kbps)")
    task.on_status = lambda t: events.append(("status", t.status.name))
    task.on_done = lambda t: events.append(("done", t.status.name))
    if stop_when_hook:
        original = FakeYDL.download

        def download(self, urls):
            task.stop = stop_when_hook
            (d._work_dir(task) / "Song.webm.part").write_bytes(b"partial")
            return original(self, urls)

        FakeYDL.download = download
        try:
            d.download_youtube_task(task, True)
        finally:
            FakeYDL.download = original
    else:
        d.download_youtube_task(task, True)
    return task, events


def test_pause_keeps_partial_file_and_progress_and_does_not_finish(isolated):
    task, events = run_youtube(isolated, stop_when_hook="pause")
    assert task.status == DownloadStatus.PAUSED
    assert (d._work_dir(task) / "Song.webm.part").exists()
    assert ("done", "PAUSED") not in events and not any(e[0] == "done" for e in events)


def test_cancel_removes_partial_file_and_finishes_as_cancelled(isolated):
    task, events = run_youtube(isolated, stop_when_hook="cancel")
    assert task.status == DownloadStatus.CANCELLED
    assert task.progress == 0.0
    assert not d._work_dir(task).exists()
    assert events[-1] == ("done", "CANCELLED")


def test_stop_flag_set_before_start_never_calls_yt_dlp(isolated):
    task = YouTubeTask(task_id="t1", url="http://x", title="Song", output_dir=str(isolated),
                       format_name="MP3 (320 kbps)", stop="pause")
    d.download_youtube_task(task, True)
    assert task.status == DownloadStatus.PAUSED
    assert FakeYDL.hook_calls == 0


def test_task_interrupted_is_a_yt_dlp_download_cancelled():
    assert issubclass(TaskInterrupted, d.yt_dlp.utils.DownloadCancelled)
    assert TaskInterrupted("pause").reason == "pause"


# ----------------------------------------------------------------- resume fallback
class Flaky416:
    """First download attempt fails like YouTube does when it refuses to resume a .part file."""
    attempts = 0

    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        Flaky416.attempts += 1
        if Flaky416.attempts == 1:
            raise d.yt_dlp.utils.DownloadError("ERROR: unable to download video data: HTTP Error 416: Requested range not satisfiable")


def test_run_ydl_starts_over_once_when_server_refuses_to_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(d.yt_dlp, "YoutubeDL", Flaky416)
    Flaky416.attempts = 0
    task = make_task(tmp_path)
    put(d._work_dir(task), "song.webm.part")
    d._run_ydl(task, {}, "http://x")
    assert Flaky416.attempts == 2
    assert not (d._work_dir(task) / "song.webm.part").exists()


def test_run_ydl_416_without_partial_file_is_a_real_error(tmp_path, monkeypatch):
    monkeypatch.setattr(d.yt_dlp, "YoutubeDL", Flaky416)
    Flaky416.attempts = 0
    with pytest.raises(d.yt_dlp.utils.DownloadError):
        d._run_ydl(make_task(tmp_path), {}, "http://x")
    assert Flaky416.attempts == 1


def test_run_ydl_lets_pause_and_cancel_through(tmp_path, monkeypatch):
    class Stopper(Flaky416):
        def download(self, urls):
            raise TaskInterrupted("pause")

    monkeypatch.setattr(d.yt_dlp, "YoutubeDL", Stopper)
    with pytest.raises(TaskInterrupted):
        d._run_ydl(make_task(tmp_path), {}, "http://x")


# ------------------------------------------------------------ friendly tiktok errors
def test_tiktok_cookie_errors_point_to_the_wiki_tutorial():
    from config import WIKI_PAGES
    url = WIKI_PAGES["tiktok_cookies"]
    assert url in d._friendly_tiktok_error("Failed to decrypt with DPAPI")
    assert url in d._friendly_tiktok_error("could not find chrome cookies database")
    assert d._friendly_tiktok_error("something else") == "something else"


def test_long_explanations_are_short_and_point_to_a_tutorial():
    from config import STRINGS
    for lang in STRINGS.values():
        for key in ("tt_cookies_desc", "tt_cookies_file_desc"):
            assert len(lang[key]) <= 100, key
        for key in ("tt_err_dpapi", "tt_err_no_browser", "mb_api_msg"):
            assert "{}" in lang[key], key      # the tutorial URL is filled in
