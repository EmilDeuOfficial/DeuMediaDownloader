import subprocess
import shutil
import os
import requests
from pathlib import Path
from typing import Optional


def find_ffmpeg() -> Optional[str]:
    """Return the ffmpeg executable path or None if not found."""
    path = shutil.which("ffmpeg")
    if path:
        return path

    # Search WinGet packages directory for any ffmpeg installation
    winget_base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_base.exists():
        for pkg_dir in winget_base.iterdir():
            if "ffmpeg" in pkg_dir.name.lower() or "yt-dlp.FFmpeg" in pkg_dir.name:
                for exe in pkg_dir.rglob("ffmpeg.exe"):
                    return str(exe)

    # Common Windows install locations
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def check_ffmpeg() -> bool:
    return find_ffmpeg() is not None


def embed_metadata_mp3(filepath: str, title: str, artist: str, album: str,
                       year: Optional[str], cover_data: Optional[bytes]) -> None:
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC, ID3NoHeaderError
    try:
        tags = ID3(filepath)
    except ID3NoHeaderError:
        tags = ID3()

    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    if year:
        tags.add(TDRC(encoding=3, text=year))
    if cover_data:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_data))
    tags.save(filepath, v2_version=3)


def embed_metadata_flac(filepath: str, title: str, artist: str, album: str,
                        year: Optional[str], cover_data: Optional[bytes]) -> None:
    from mutagen.flac import FLAC, Picture
    audio = FLAC(filepath)
    audio["title"]  = [title]
    audio["artist"] = [artist]
    audio["album"]  = [album]
    if year:
        audio["date"] = [year]
    if cover_data:
        pic = Picture()
        pic.data = cover_data
        pic.mime = "image/jpeg"
        pic.type = 3
        audio.clear_pictures()
        audio.add_picture(pic)
    audio.save()


def embed_metadata_ogg(filepath: str, title: str, artist: str, album: str,
                       year: Optional[str], cover_data: Optional[bytes]) -> None:
    from mutagen.oggvorbis import OggVorbis
    import base64
    from mutagen.flac import Picture

    audio = OggVorbis(filepath)
    audio["title"]  = [title]
    audio["artist"] = [artist]
    audio["album"]  = [album]
    if year:
        audio["date"] = [year]
    if cover_data:
        pic = Picture()
        pic.data = cover_data
        pic.mime = "image/jpeg"
        pic.type = 3
        encoded = base64.b64encode(pic.write()).decode("ascii")
        audio["metadata_block_picture"] = [encoded]
    audio.save()


def embed_metadata_m4a(filepath: str, title: str, artist: str, album: str,
                       year: Optional[str], cover_data: Optional[bytes]) -> None:
    from mutagen.mp4 import MP4, MP4Cover
    audio = MP4(filepath)
    audio["\xa9nam"] = [title]
    audio["\xa9ART"] = [artist]
    audio["\xa9alb"] = [album]
    if year:
        audio["\xa9day"] = [year]
    if cover_data:
        audio["covr"] = [MP4Cover(cover_data, MP4Cover.FORMAT_JPEG)]
    audio.save()


def embed_metadata_wav(filepath: str, title: str, artist: str, album: str,
                       year: Optional[str], cover_data: Optional[bytes]) -> None:
    # WAV uses ID3 tags via mutagen
    from mutagen.wave import WAVE
    from mutagen.id3 import TIT2, TPE1, TALB, TDRC, APIC
    audio = WAVE(filepath)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text=album))
    if year:
        audio.tags.add(TDRC(encoding=3, text=year))
    if cover_data:
        audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_data))
    audio.save()


def embed_metadata(filepath: str, ext: str, title: str, artist: str, album: str,
                   year: Optional[str], cover_data: Optional[bytes]) -> None:
    """Dispatch to the correct tagger based on file extension."""
    handlers = {
        "mp3":  embed_metadata_mp3,
        "flac": embed_metadata_flac,
        "ogg":  embed_metadata_ogg,
        "m4a":  embed_metadata_m4a,
        "wav":  embed_metadata_wav,
    }
    handler = handlers.get(ext.lower())
    if handler:
        handler(filepath, title, artist, album, year, cover_data)


def fetch_cover(url: str) -> Optional[bytes]:
    """Download cover art bytes from a URL; return None on failure."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None
