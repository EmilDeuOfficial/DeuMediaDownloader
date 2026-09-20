# DeuMediaDownloader

A modern Windows desktop app to download **music and videos** from Spotify, YouTube and TikTok.
Save audio (MP3, AAC, OGG, FLAC, AIFF, WAV) or video (MP4, MOV, AVI, MKV, WebM) in the quality you choose.

![Version](https://img.shields.io/badge/version-v1.7.0-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-blue)
![Backend](https://img.shields.io/badge/backend-Python%203.10%2B-lightgrey)
![Frontend](https://img.shields.io/badge/frontend-HTML%20%2B%20CSS%20%2B%20JS-lightgrey)
![Languages](https://img.shields.io/badge/languages-2-orange)

---

## Features

- **Audio and video** - Music as MP3, AAC, OGG Vorbis, FLAC, AIFF or WAV; videos as MP4, MOV, AVI, MKV or WebM up to 1080p
- **Three sources** - Spotify (tracks, playlists, albums), YouTube (videos, playlists), TikTok (videos, profiles, hashtags, sounds)
- **Format and quality** - Pick the format and the quality separately; the quality list follows the format
- **Queue** - Live progress, plus pause, resume and cancel for every download
- **Metadata** - Title, artist, album, year and cover art are embedded in the audio files
- **YouTube extras** - Subtitles, SponsorBlock and a speed limit
- **Two languages** - German and English interface
- **Installer** - Sets up FFmpeg and the WebView2 runtime when they are missing

Full documentation is in the [wiki](https://github.com/EmilDeuOfficial/DeuMediaDownloader/wiki).

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| Microsoft Edge WebView2 Runtime | Renders the UI (preinstalled on Windows 11, the installer adds it if missing) |
| FFmpeg | Audio conversion & quality control |
| Spotify Developer Account | API credentials (free, only for the Spotify downloader) |

---

## Quick Start

### 1 - Install FFmpeg

**Windows (recommended - winget):**
```
winget install ffmpeg
```
Or download from https://ffmpeg.org/download.html and add `bin/` to your PATH.

**Verify:**
```
ffmpeg -version
```

---

### 2 - Install Python dependencies

```
pip install -r requirements.txt
```

---

### 3 - Get Spotify API credentials (free, Spotify downloader only)

1. Go to https://developer.spotify.com/dashboard
2. Log in and click **Create app**
3. Set any name/description; Redirect URI: `http://127.0.0.1:8888/callback`
4. Copy your **Client ID** and **Client Secret**

---

### 4 - Run the application

```
python main.py
```

On first launch, open the Spotify downloader, click the **gear icon** in the
top-right and paste your Spotify Client ID and Client Secret, then click **Save**.
The YouTube and TikTok downloaders work without any credentials.

---

## Usage

1. Open the launcher and pick **Spotify**, **YouTube** or **TikTok**
2. Copy a URL and paste it into the URL field (or click **Paste**):
   a Spotify track, playlist or album, a YouTube video or playlist,
   or a TikTok video, profile, hashtag or sound
3. YouTube and TikTok: choose **Audio** or **Video** (Spotify downloads are audio)
4. Choose a **Format** and a **Quality** (MP3 320 kbps, FLAC, MP4 1080p, MKV Best, ...)
5. Select an output folder with **Browse**
6. Click **Download**

Items are added to the queue and downloaded in parallel; every entry can be paused,
resumed or cancelled. Audio files get title, artist, album and cover art embedded automatically.

---

## Project Structure

```
DeuMediaDownloader/
├── main.py          Entry point - dependency checks, creates the pywebview window
├── api.py           Object exposed to JavaScript (window.pywebview.api)
├── events.py        Pushes events from Python threads to the page
├── services.py      Per-service runtimes: resolve URL, queue tasks, forward updates
├── downloader.py    Spotify / YouTube / TikTok download logic (yt-dlp)
├── converter.py     FFmpeg helpers + mutagen metadata embedding
├── clipboard.py     Windows clipboard access for the Paste button
├── config.py        Constants, format definitions, translations, config I/O
├── frontend/        HTML, CSS and JavaScript UI (vanilla ES modules)
├── tests/           pytest tests for the backend
├── tools/           Dev helpers (smoke test, mock data, icon generator)
├── build.py         PyInstaller + Inno Setup build
└── requirements.txt
```

### Development

```
python -m pytest                          # backend tests
node --test frontend/tests/*.test.mjs     # frontend unit tests
python tools/smoke_test.py                # drive the real window (no downloads)
```

Tutorials linked from the app are drafted in `docs/wiki/`. Copy those pages into the
GitHub wiki (page names `TikTok-Cookies` and `Spotify-API-Setup`); the app links to
`https://github.com/EmilDeuOfficial/DeuMediaDownloader/wiki/<page>` (see `WIKI_PAGES` in `config.py`).

To work on the UI without Python, serve `frontend/` (for example
`python -m http.server --directory frontend`) and open `index.html?mock=1`;
a simulated backend answers the API calls.

---

## Supported Output Formats

Pick a **Format** and then a **Quality**; the quality list changes with the format.

Audio:

| Format | Qualities | Notes |
|---|---|---|
| MP3 | 320 / 256 / 192 kbps | Widely compatible |
| AAC (M4A) | 256 / 192 kbps | Great for Apple devices |
| OGG Vorbis | 320 / 256 / 192 kbps | Open format |
| FLAC | Lossless | Compressed, tags and cover art |
| AIFF | Lossless | Uncompressed, tags and cover art (Spotify downloads) |
| WAV | Lossless | Uncompressed, large files |

The audio source is YouTube (about 256 kbps at best), so the lossless formats are
convenient containers, not better sound than a 320 kbps MP3.

Video (YouTube and TikTok):

| Format | Qualities | Notes |
|---|---|---|
| MP4 | 1080p / 720p / 480p / 360p | Widely compatible |
| MOV | 1080p / 720p / 480p / 360p | Converted with FFmpeg |
| AVI | 1080p / 720p / 480p / 360p | Converted with FFmpeg (Xvid) |
| MKV | Best / 1080p / 720p / 480p / 360p | Best available quality |
| WebM | Best / 1080p / 720p / 480p / 360p | Open format |

The lists are generated from two small tables in `config.py` (`_AUDIO_SPEC`,
`_VIDEO_SPEC`); audio below 129 kbps and video below 360p are not offered.

---

## Troubleshooting

**"FFmpeg ✗" shown in the header** - FFmpeg is not on your PATH.
Install it and restart the app.

**"No Spotify API credentials"** - Open Settings and enter your credentials.

**Track not found / wrong match** - yt-dlp searches YouTube Music;
rare tracks may not be available there.

---

## Legal Notice

This tool is intended for personal use with content you have the right to download.
Respect the Spotify Terms of Service and applicable copyright laws.
