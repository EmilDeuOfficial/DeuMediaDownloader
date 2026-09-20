import subprocess

import pytest

import config
import downloader as d
from config import AUDIO_FORMATS, DEFAULT_CONFIG, VIDEO_FORMATS
from converter import embed_metadata, find_ffmpeg


# ------------------------------------------------------------------ format lists
def test_audio_formats_offer_only_the_best_mp3_and_add_flac_and_aiff():
    names = list(AUDIO_FORMATS)
    assert [n for n in names if n.startswith("MP3")] == ["MP3 (320 kbps)"]
    assert AUDIO_FORMATS["FLAC (Lossless)"]["ext"] == "flac"
    assert AUDIO_FORMATS["AIFF (Lossless)"]["ext"] == "aiff"
    assert {"AAC (256 kbps)", "OGG Vorbis (320 kbps)", "WAV (Lossless)"} <= set(names)


def test_video_formats_start_at_720p_and_add_mov_and_avi():
    names = list(VIDEO_FORMATS)
    assert [n for n in names if n.startswith("MP4")] == ["MP4 (1080p)", "MP4 (720p)"]
    assert not any(low in " ".join(names) for low in ("480p", "360p"))
    assert VIDEO_FORMATS["MOV (1080p)"]["ext"] == "mov"
    assert VIDEO_FORMATS["AVI (1080p)"]["ext"] == "avi"
    assert {"MKV (Best)", "WebM (Best)"} <= set(names)


def test_saved_defaults_exist_in_the_format_lists():
    for key in ("default_format", "yt_format", "yt_format_audio", "tt_format_audio"):
        assert DEFAULT_CONFIG[key] in AUDIO_FORMATS, key
    for key in ("yt_format_video", "tt_format_video"):
        assert DEFAULT_CONFIG[key] in VIDEO_FORMATS, key


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
