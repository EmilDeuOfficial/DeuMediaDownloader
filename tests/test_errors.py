import pytest

import config
from config import T, WIKI_PAGES
from errors import short_error


@pytest.mark.parametrize("message, key, args", [
    ("ERROR: [youtube] jNQXAC9IZ0k: This video is unavailable", "err_short_unavailable", ()),
    ("ERROR: [youtube] abc: Video unavailable. This video has been removed by the uploader", "err_short_unavailable", ()),
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access to this video", "err_short_private", ()),
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", "err_short_signin", ()),
    ("ERROR: [youtube] abc: The uploader has not made this video available in your country", "err_short_geo", ()),
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", "err_short_http", ("403",)),
    ("ERROR: unable to download video data: HTTP Error 416: Requested range not satisfiable", "err_short_http", ("416",)),
    ("Downloaded file not found in output directory.", "err_short_no_file", ()),
    ("Downloaded file not found.", "err_short_no_file", ()),
    ("ERROR: Postprocessing: ffprobe and ffmpeg not found. Please install or provide the path", "err_short_ffmpeg", ()),
    ("<urlopen error [Errno 11001] getaddrinfo failed>", "err_short_network", ()),
    ("HTTPSConnectionPool(host='x', port=443): Max retries exceeded", "err_short_network", ()),
    ("[Errno 13] Permission denied: 'C:\\\\out\\\\song.mp3'", "err_short_disk", ()),
    ("[Errno 28] No space left on device", "err_short_disk", ()),
    ("[WinError 3] Das System kann den angegebenen Pfad nicht finden: 'Z:\\\\'", "err_short_path", ()),
    ("ERROR: Unable to rename file: [WinError 32] Der Prozess kann nicht auf die Datei zugreifen, da sie von einem anderen Prozess verwendet wird: 'a.webm' -> 'a.webm'", "err_short_file_in_use", ()),
    ("[WinError 32] The process cannot access the file because it is being used by another process: 'a.webm'", "err_short_file_in_use", ()),
    ("[Errno 2] No such file or directory: 'C:\\\\out'", "err_short_path", ()),
])
def test_known_errors_get_a_short_translated_text(message, key, args):
    assert short_error(message) == T(key).format(*args)


def test_our_own_no_match_error_is_recognised():
    message = T("err_no_match").format("HARDX, NX!ZE - ELECTROSOULS")
    assert short_error(message) == T("err_short_no_match")


def test_tiktok_cookie_errors_are_recognised_by_their_tutorial_link():
    message = T("tt_err_dpapi").format(WIKI_PAGES["tiktok_cookies"])
    assert short_error(message) == T("err_short_tiktok_cookies")


def test_unknown_error_keeps_its_first_line_without_yt_dlp_noise():
    assert short_error("ERROR: [youtube] abc123: Something odd happened\nmore details\nand more") == "Something odd happened"


def test_long_unknown_error_is_cut_with_an_ellipsis():
    result = short_error("x" * 100)
    assert result == "x" * 45 + "\u2026"


def test_empty_message_gives_the_generic_text():
    assert short_error("") == T("err_short_unknown")
    assert short_error("   \n ") == T("err_short_unknown")


def test_texts_follow_the_active_language(monkeypatch):
    monkeypatch.setattr(config, "_lang", "de")
    assert short_error("ERROR: unable to download video data: HTTP Error 403: Forbidden") == "HTTP-Fehler 403"
    assert short_error("This video is unavailable") == "Video nicht verf\u00fcgbar"


def test_every_language_has_all_short_texts():
    keys = ["err_short_unavailable", "err_short_private", "err_short_signin", "err_short_geo",
            "err_short_http", "err_short_network", "err_short_no_match", "err_short_no_file",
            "err_short_ffmpeg", "err_short_disk", "err_short_path", "err_short_tiktok_cookies", "err_short_unknown"]
    for lang in config.STRINGS.values():
        for key in keys:
            assert key in lang and lang[key], key
            assert len(lang[key]) <= 32, key       # short means short


def test_unknown_os_error_loses_its_error_code_prefix():
    assert short_error("[WinError 1234] Something odd happened") == "Something odd happened"
