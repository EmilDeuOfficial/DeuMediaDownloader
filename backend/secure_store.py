"""Encrypts secrets (Spotify client secret, login tokens) with the Windows Data
Protection API, so they are bound to the Windows user account and useless when the
files are copied to another account or machine.

Encrypted text looks like "dpapi:<base64>". Older versions stored everything in plain
text; reading such a value works and the callers write it back encrypted.
"""
import base64
import ctypes
import json
import logging
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

PREFIX = "dpapi:"
_ENTROPY = b"DeuMediaDownloader"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(buf) -> _Blob:
    """Blob pointing into `buf`; the caller keeps `buf` alive while the blob is used."""
    return _Blob(len(buf), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _crypt(fn_name: str, data: bytes) -> bytes:
    """Call CryptProtectData or CryptUnprotectData (same signature) on `data`."""
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    data_buf = ctypes.create_string_buffer(data, len(data))
    entropy_buf = ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY))
    out = _Blob()
    ok = getattr(crypt32, fn_name)(
        ctypes.byref(_blob(data_buf)), None, ctypes.byref(_blob(entropy_buf)), None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out),
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), f"{fn_name} failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def available() -> bool:
    return sys.platform == "win32"


def is_protected(text: str) -> bool:
    return isinstance(text, str) and text.startswith(PREFIX)


def protect(text: str) -> str:
    """Encrypt for the current Windows user. Empty strings stay empty."""
    if not text or is_protected(text) or not available():
        return text
    return PREFIX + base64.b64encode(_crypt("CryptProtectData", text.encode("utf-8"))).decode("ascii")


def unprotect(text: str) -> str:
    """Decrypt a protected value; plain text (from older versions) is returned as is.
    Raises ValueError if the value belongs to another Windows user or is damaged."""
    if not is_protected(text):
        return text
    try:
        raw = base64.b64decode(text[len(PREFIX):], validate=True)
        return _crypt("CryptUnprotectData", raw).decode("utf-8")
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot decrypt secret: {exc}") from exc


_cache_class = None


def token_cache(cache_path: str):
    """A spotipy cache handler for `cache_path` that stores the token encrypted.
    spotipy is imported only here, so the settings code does not depend on it."""
    global _cache_class
    if _cache_class is None:
        from spotipy.cache_handler import CacheHandler
        _cache_class = type("ProtectedCacheFile", (_ProtectedCacheFile, CacheHandler), {})
    return _cache_class(cache_path)


class _ProtectedCacheFile:
    """spotipy token cache that keeps the token file encrypted. A plain JSON file from
    an older version is read once and rewritten encrypted."""

    def __init__(self, cache_path: str):
        self.cache_path = cache_path

    def get_cached_token(self) -> Optional[dict]:
        path = Path(self.cache_path)
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        except OSError as exc:
            log.warning("Could not read token cache %s: %s", path.name, exc)
            return None
        try:
            token = json.loads(unprotect(text))
        except ValueError as exc:
            log.warning("Token cache %s is unusable, a new login is needed: %s", path.name, exc)
            return None
        if not is_protected(text):
            log.info("Encrypting old plain token cache %s", path.name)
            self.save_token_to_cache(token)
        return token

    def save_token_to_cache(self, token_info: dict) -> None:
        from .config import write_atomic
        try:
            write_atomic(Path(self.cache_path), protect(json.dumps(token_info)).encode("ascii"))
        except OSError as exc:
            log.warning("Could not write token cache %s: %s", Path(self.cache_path).name, exc)
