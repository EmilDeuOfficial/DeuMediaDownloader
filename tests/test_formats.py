from pathlib import Path
import subprocess

import pytest

import config
import downloader as d
from config import AUDIO_FORMATS, DEFAULT_CONFIG, VIDEO_FORMATS
from converter import embed_metadata, find_ffmpeg


# ------------------------------------------------------------------ format lists
def test_audio_formats_cover_all_qualities_but_nothing_under_129_kbps():
    names = list(AUDIO_FORMATS)
    assert [n for n in names if n.startswith("MP3")] == ["MP3 (320 kbps)", "MP3 (256 kbps)", "MP3 (192 kbps)"]
    assert [n for n in names if n.startswith("AAC")] == ["AAC (256 kbps)", "AAC (192 kbps)"]
    assert [n for n in names if n.startswith("OGG")] == [
        "OGG Vorbis (320 kbps)", "OGG Vorbis (256 kbps)", "OGG Vorbis (192 kbps)"]
    for name, info in AUDIO_FORMATS.items():
        if info["bitrate"]:
            assert int(info["bitrate"].rstrip("k")) >= 129, name
    assert AUDIO_FORMATS["FLAC (Lossless)"]["ext"] == "flac"
    assert AUDIO_FORMATS["AIFF (Lossless)"]["ext"] == "aiff"
    assert AUDIO_FORMATS["WAV (Lossless)"]["ext"] == "wav"


def test_video_formats_offer_1080p_down_to_360p_and_never_less():
    names = list(VIDEO_FORMATS)
    for container in ("MP4", "MOV", "AVI"):
        assert [n for n in names if n.startswith(container)] == [
            f"{container} (1080p)", f"{container} (720p)", f"{container} (480p)", f"{container} (360p)"]
    for container in ("MKV", "WebM"):
        assert [n for n in names if n.startswith(container)] == [
            f"{container} (Best)", f"{container} (1080p)", f"{container} (720p)",
            f"{container} (480p)", f"{container} (360p)"]
    assert not any("240p" in n or "144p" in n for n in names)
    assert VIDEO_FORMATS["MOV (1080p)"]["ext"] == "mov" and VIDEO_FORMATS["MOV (1080p)"]["convert"] is True
    assert VIDEO_FORMATS["AVI (360p)"]["ext"] == "avi" and VIDEO_FORMATS["AVI (360p)"]["convert"] is True


@pytest.mark.parametrize("name, needle", [
    ("MP4 (720p)", "height<=720"),
    ("MOV (480p)", "height<=480"),
    ("MKV (360p)", "height<=360"),
    ("WebM (1080p)", "height<=1080"),
])
def test_video_quality_limits_the_yt_dlp_format_string(name, needle):
    assert needle in VIDEO_FORMATS[name]["ydl_format"]


def test_best_quality_has_no_height_limit():
    assert "height" not in VIDEO_FORMATS["MKV (Best)"]["ydl_format"]
    assert "height" not in VIDEO_FORMATS["WebM (Best)"]["ydl_format"]


def test_saved_defaults_exist_in_the_format_lists():
    for key in ("default_format", "yt_format", "yt_format_audio", "tt_format_audio"):
        assert DEFAULT_CONFIG[key] in AUDIO_FORMATS, key
    for key in ("yt_format_video", "tt_format_video"):
        assert DEFAULT_CONFIG[key] in VIDEO_FORMATS, key


# ------------------------------------------------- format + quality for the two dropdowns
def test_groups_describe_format_and_its_qualities_for_the_ui():
    from config import AUDIO_GROUPS, VIDEO_GROUPS
    assert [g["format"] for g in AUDIO_GROUPS] == ["MP3", "AAC", "OGG Vorbis", "FLAC", "AIFF", "WAV"]
    assert [g["format"] for g in VIDEO_GROUPS] == ["MP4", "MOV", "AVI", "MKV", "WebM"]
    mp3 = AUDIO_GROUPS[0]
    assert [q["label"] for q in mp3["qualities"]] == ["320 kbps", "256 kbps", "192 kbps"]
    assert [q["name"] for q in mp3["qualities"]] == ["MP3 (320 kbps)", "MP3 (256 kbps)", "MP3 (192 kbps)"]
    flac = AUDIO_GROUPS[3]
    assert flac["qualities"] == [{"label": "Lossless", "name": "FLAC (Lossless)"}]


def test_every_group_quality_points_at_a_real_format_and_best_is_translatable():
    from config import AUDIO_GROUPS, VIDEO_GROUPS
    for group in AUDIO_GROUPS:
        for q in group["qualities"]:
            assert q["name"] in AUDIO_FORMATS
    for group in VIDEO_GROUPS:
        for q in group["qualities"]:
            assert q["name"] in VIDEO_FORMATS
    mkv = next(g for g in VIDEO_GROUPS if g["format"] == "MKV")
    assert mkv["qualities"][0] == {"label": "Best", "name": "MKV (Best)", "label_key": "quality_best"}


def test_quality_strings_exist_in_every_language():
    for lang in config.STRINGS.values():
        assert lang["quality"] and lang["quality_best"]


@pytest.mark.parametrize("name", list(AUDIO_FORMATS))
def test_every_audio_format_has_what_the_downloaders_read(name):
    assert {"ext", "codec", "bitrate", "ydl_quality"} <= set(AUDIO_FORMATS[name])


@pytest.mark.parametrize("name", list(VIDEO_FORMATS))
def test_every_video_format_has_what_the_downloaders_read(name):
    assert {"ext", "ydl_format"} <= set(VIDEO_FORMATS[name])


def test_yt_dlp_supports_the_conversion_targets_we_rely_on():
    import yt_dlp.postprocessor as pp
    assert "flac" in pp.FFmpegExtractAudioPP.SUPPORTED_EXTS
    assert "aiff" not in pp.FFmpegExtractAudioPP.SUPPORTED_EXTS      # hence the converter for AIFF
    for ext in ("aiff", "mov", "avi"):
        assert ext in pp.FFmpegVideoConvertorPP.SUPPORTED_EXTS


# ----------------------------------------------------------- post-processor choice
def test_audio_postprocessor_uses_the_audio_extractor_where_possible():
    assert d._audio_postprocessor(AUDIO_FORMATS["MP3 (320 kbps)"]) == {
        "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}
    assert d._audio_postprocessor(AUDIO_FORMATS["FLAC (Lossless)"]) == {
        "key": "FFmpegExtractAudio", "preferredcodec": "flac"}
    assert d._audio_postprocessor(AUDIO_FORMATS["WAV (Lossless)"]) == {
        "key": "FFmpegExtractAudio", "preferredcodec": "wav"}


def test_aiff_goes_through_the_converter_because_the_extractor_cannot_write_it():
    assert d._audio_postprocessor(AUDIO_FORMATS["AIFF (Lossless)"]) == {
        "key": "FFmpegVideoConvertor", "preferedformat": "aiff"}


# -------------------------------------------- options handed to yt-dlp per format
class CaptureYDL:
    opts = None

    def __init__(self, opts):
        CaptureYDL.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        pass


@pytest.fixture
def capture(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "cfg" / "config.json")
    monkeypatch.setattr(d.yt_dlp, "YoutubeDL", CaptureYDL)
    CaptureYDL.opts = None
    return tmp_path / "out"


def youtube_opts(out, fmt):
    task = d.YouTubeTask(task_id="t", url="http://x", title="Song", output_dir=str(out), format_name=fmt)
    d.download_youtube_task(task, True)      # ends in "file not found": the fake downloads nothing
    return CaptureYDL.opts


@pytest.mark.parametrize("fmt, expected", [
    ("AIFF (Lossless)", [{"key": "FFmpegVideoConvertor", "preferedformat": "aiff"}]),
    ("FLAC (Lossless)", [{"key": "FFmpegExtractAudio", "preferredcodec": "flac"}, {"key": "EmbedThumbnail"}]),
    ("MOV (1080p)", [{"key": "FFmpegVideoConvertor", "preferedformat": "mov"}]),
    ("AVI (1080p)", [{"key": "FFmpegVideoConvertor", "preferedformat": "avi"}]),
])
def test_youtube_task_adds_the_right_postprocessors(capture, fmt, expected):
    assert youtube_opts(capture, fmt)["postprocessors"] == expected


def test_plain_mp4_needs_no_postprocessor(capture):
    assert "postprocessors" not in youtube_opts(capture, "MP4 (720p)")


def test_tiktok_task_converts_to_mov(capture):
    task = d.TikTokTask(task_id="t", url="http://x", title="Clip", output_dir=str(capture), format_name="MOV (1080p)")
    d.download_tiktok_task(task, True)
    assert CaptureYDL.opts["postprocessors"] == [{"key": "FFmpegVideoConvertor", "preferedformat": "mov"}]


@pytest.mark.skipif(find_ffmpeg() is None, reason="ffmpeg not installed")
def test_spotify_task_converts_to_aiff(capture, monkeypatch):
    monkeypatch.setattr(d, "_find_best_youtube_match", lambda *a: "http://x")
    track = d.TrackInfo("id", "Title", "Artist", "Album", None, 1000, "2024")
    task = d.DownloadTask("t", track, str(capture), "AIFF (Lossless)")
    d.download_spotify_track(task, True)
    assert CaptureYDL.opts["postprocessors"] == [{"key": "FFmpegVideoConvertor", "preferedformat": "aiff"}]


# ------------------------------------------------------------- AIFF cover and tags
@pytest.mark.skipif(find_ffmpeg() is None, reason="ffmpeg not installed")
def test_aiff_files_get_title_artist_album_and_cover(tmp_path):
    path = tmp_path / "t.aiff"
    subprocess.run([find_ffmpeg(), "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    str(path)], check=True)
    embed_metadata(str(path), "aiff", "Title", "Artist", "Album", "2024", b"\xff\xd8\xff fake jpeg")

    from mutagen.aiff import AIFF
    tags = AIFF(str(path)).tags
    assert str(tags["TIT2"]) == "Title"
    assert str(tags["TPE1"]) == "Artist"
    assert str(tags["TALB"]) == "Album"
    assert any(key.startswith("APIC") for key in tags.keys())


# ----------------------------------------------- regressions found with real downloads
def test_every_extractor_codec_we_ask_for_is_supported_by_yt_dlp():
    """OGG used to fail with KeyError 'ogg': yt-dlp's extractor calls that codec 'vorbis'."""
    import yt_dlp.postprocessor as pp
    for name, info in AUDIO_FORMATS.items():
        post = d._audio_postprocessor(info)
        if post["key"] == "FFmpegExtractAudio":
            assert post["preferredcodec"] in pp.FFmpegExtractAudioPP.SUPPORTED_EXTS, name


def test_ogg_uses_the_vorbis_codec_name_and_keeps_the_bitrate():
    assert d._audio_postprocessor(AUDIO_FORMATS["OGG Vorbis (192 kbps)"]) == {
        "key": "FFmpegExtractAudio", "preferredcodec": "vorbis", "preferredquality": "192"}


@pytest.mark.parametrize("fmt, container", [
    ("MKV (720p)", "mkv"),        # yt-dlp would otherwise merge AV1 + Opus into .webm
    ("MKV (Best)", "mkv"),
    ("WebM (480p)", "webm"),
    ("MP4 (1080p)", "mp4"),
    ("MOV (1080p)", "mp4"),       # merged as mp4 first, then converted to mov
    ("AVI (360p)", "mp4"),
])
def test_video_is_merged_into_the_chosen_container(capture, fmt, container):
    assert youtube_opts(capture, fmt)["merge_output_format"] == container


def test_audio_download_has_no_merge_format(capture):
    assert "merge_output_format" not in youtube_opts(capture, "MP3 (192 kbps)")


def test_tiktok_video_is_merged_into_the_chosen_container(capture):
    task = d.TikTokTask(task_id="t", url="http://x", title="Clip", output_dir=str(capture), format_name="MKV (Best)")
    d.download_tiktok_task(task, True)
    assert CaptureYDL.opts["merge_output_format"] == "mkv"


def test_download_is_written_to_a_private_work_folder_not_the_output_folder(capture):
    opts = youtube_opts(capture, "MP3 (192 kbps)")
    outtmpl = Path(opts["outtmpl"])
    assert outtmpl.parent.name.startswith(".dmd-")
    assert outtmpl.parent.parent == capture


def test_the_same_title_in_two_formats_gets_two_work_folders(capture):
    def outtmpl(task_id, fmt):
        task = d.YouTubeTask(task_id=task_id, url="http://x", title="Song", output_dir=str(capture), format_name=fmt)
        d.download_youtube_task(task, True)
        return CaptureYDL.opts["outtmpl"]
    assert outtmpl("11111111-a", "MP3 (192 kbps)") != outtmpl("22222222-b", "WAV (Lossless)")


def test_failed_download_leaves_no_work_folder_behind(capture):
    youtube_opts(capture, "MP3 (192 kbps)")      # the fake downloads nothing, so the task fails
    assert not any(p.name.startswith(".dmd-") for p in capture.iterdir())
