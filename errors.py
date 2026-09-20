"""Short, translated versions of download errors for the queue list.

The complete message stays in the log panel (and on stderr); the queue only shows what
went wrong in a few words.
"""
import re

from config import T, WIKI_PAGES

_FALLBACK_MAX = 45

_HTTP = re.compile(r"HTTP Error (\d{3})", re.I)

# (pattern, translation key), checked in this order: "private video" must come before
# "sign in" because YouTube's private-video text also contains "Sign in".
_RULES = [
    (re.compile(r"private video", re.I), "err_short_private"),
    (re.compile(r"video (is )?unavailable|has been removed|no longer available|account associated with this video has been terminated", re.I), "err_short_unavailable"),
    (re.compile(r"sign in to confirm|confirm you.re not a bot|login required|log in to view|requires (a )?login", re.I), "err_short_signin"),
    (re.compile(r"not made this video available in your country|not available in your (country|region)|geo.?restrict", re.I), "err_short_geo"),
    (re.compile(r"downloaded file not found", re.I), "err_short_no_file"),
    (re.compile(r"ffmpeg[^\n]*not (found|installed)|ffprobe and ffmpeg not found", re.I), "err_short_ffmpeg"),
    (re.compile(r"getaddrinfo failed|name resolution|network is unreachable|timed out|connection (reset|aborted|refused|error)|max retries exceeded|urlopen error|remotedisconnected", re.I), "err_short_network"),
    (re.compile(r"winerror (2|3)\b|errno 2\b|no such file or directory|cannot find the (path|file)", re.I), "err_short_path"),
    (re.compile(r"permission denied|errno 13|winerror 5|access is denied|no space left|errno 28", re.I), "err_short_disk"),
]

_ERROR_PREFIX = re.compile(r"^\s*ERROR:\s*", re.I)
_EXTRACTOR_PREFIX = re.compile(r"^\[[\w:.-]+\]\s+[\w-]+:\s*")


def short_error(message: str) -> str:
    """A few words for `message`, in the active language."""
    text = (message or "").strip()
    if not text:
        return T("err_short_unknown")

    if WIKI_PAGES["tiktok_cookies"] in text:
        return T("err_short_tiktok_cookies")
    no_match_start = T("err_no_match").split("{}")[0].strip()
    if no_match_start and text.startswith(no_match_start):
        return T("err_short_no_match")

    for pattern, key in _RULES:
        if pattern.search(text):
            return T(key)

    http = _HTTP.search(text)
    if http:
        return T("err_short_http").format(http.group(1))

    # Unknown: first line without yt-dlp's "ERROR: [youtube] id:" noise.
    first = next((line for line in text.splitlines() if line.strip()), "")
    first = _EXTRACTOR_PREFIX.sub("", _ERROR_PREFIX.sub("", first)).strip()
    if not first:
        return T("err_short_unknown")
    return first if len(first) <= _FALLBACK_MAX else first[:_FALLBACK_MAX] + "…"
