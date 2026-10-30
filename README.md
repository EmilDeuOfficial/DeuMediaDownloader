# DeuMediaDownloader

A modern Windows desktop app to download **music and videos** from Spotify, YouTube, TikTok, SoundCloud and Instagram.
Save audio (MP3, AAC, OGG, Opus, FLAC, AIFF, WAV) or video (MP4, MOV, AVI, MKV, WebM) in the quality you choose.

![Version](https://img.shields.io/badge/version-v7.3.1-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-blue)
![Backend](https://img.shields.io/badge/backend-Python%203.10%2B-lightgrey)
![Frontend](https://img.shields.io/badge/frontend-HTML%20%2B%20CSS%20%2B%20JS-lightgrey)
![Languages](https://img.shields.io/badge/languages-2-orange)

---

## Features

- **Audio and video** - Music as MP3, AAC, OGG Vorbis, Opus, FLAC, AIFF, WAV or the untouched original; videos as MP4, MOV, AVI, MKV or WebM up to 4K
- **Five sources** - Spotify (tracks, playlists, albums), YouTube (videos, playlists, channels), TikTok (videos, profiles, hashtags, sounds), SoundCloud (tracks, sets, profiles), Instagram (reels, posts, stories, profiles)
- **Pick what to download** - A playlist, channel, set or profile is listed first; tick or untick single entries (with a filter and Shift-click ranges) before anything is queued
- **Drop a link** - Drag a link from your browser onto a downloader window and it lands in the URL field
- **Format and quality** - Pick the format and the quality separately; the quality list follows the format
- **Queue** - Live progress, plus pause, resume and cancel for every download
- **Spotify recording** - Instead of a YouTube match, record the real Spotify stream in a hidden player (Premium, real time, Windows 10 2004 or newer)
- **Metadata** - Title, artist, album, year and cover art are embedded in the audio files
- **YouTube extras** - Subtitles, SponsorBlock and a speed limit
- **Two languages** - German and English interface
- **Installer** - Sets up FFmpeg and the WebView2 runtime when they are missing
- **App updates** - The title bar shows a dot when a newer release is on GitHub; one click shows the release notes, downloads the setup, installs it and restarts the app

Full documentation is in the [wiki](https://github.com/EmilDeuOfficial/DeuMediaDownloader/wiki).

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| Microsoft Edge WebView2 Runtime | Renders the UI (preinstalled on Windows 11, the installer adds it if missing) |
| FFmpeg | Audio conversion & quality control |
| Deno | JavaScript runtime yt-dlp needs for YouTube (the installer adds it if missing) |
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
The YouTube, TikTok and SoundCloud downloaders work without any credentials. Instagram usually
needs your browser login, see the [Instagram cookies tutorial](https://github.com/EmilDeuOfficial/DeuMediaDownloader/wiki/Instagram-Cookies).

---

## Usage

1. Open the launcher and pick **Spotify**, **YouTube**, **TikTok**, **SoundCloud** or **Instagram**
2. Copy a URL and paste it into the URL field (or click **Paste**):
   a Spotify track, playlist or album, a YouTube video, playlist or channel,
   a TikTok video, profile, hashtag or sound, a SoundCloud track, set or profile,
   or an Instagram reel, post, story or profile.
   You can also drag a link from your browser onto the window
3. YouTube, TikTok and Instagram: choose **Audio** or **Video** (Spotify and SoundCloud downloads are audio)
4. Choose a **Format** and a **Quality** (MP3 320 kbps, FLAC, MP4 1080p, MKV 4K, ...)
5. Select an output folder with **Browse**
6. Click **Download**. For a playlist, channel, set or profile a list opens first: untick what you
   do not want (or filter by title) and click **Download**

Items are added to the queue and downloaded in parallel; every entry can be paused,
resumed or cancelled. Audio files get title, artist, album and cover art embedded automatically.

---

## Spotify recording

The Spotify view has a switch between **YouTube download** (default) and **Spotify recording**.
Recording plays each track in a hidden Spotify player window and captures only that window's
audio.

1. Open the settings (gear icon) and click **Log in** under **Spotify Account**: the Spotify login
   opens in your default browser (Spotify Premium account; the API credentials from the settings
   are used, add `http://127.0.0.1:8888/callback` as Redirect URI). Clicking **Record** while
   logged out offers the login as well.
2. Switch to **Spotify recording**, paste a track, playlist or album URL, choose a format and
   click **Record**

Good to know:

- It runs in **real time**, one track at a time (a Spotify account plays one stream). The quality
  is the one of Spotify's web player, not better.
- The player runs silently, so you do not hear the recording, and nothing else the PC plays ends
  up in the file.
- Every recording gets one second of silence at the start and the end.
- Starting a recording takes over playback on your other Spotify devices.
- Recording can be cancelled but not paused.
- Recording streams may violate Spotify's Terms of Service and can get an account blocked. Use it
  only for your own account and for personal copies.

---

## Project Structure

```
DeuMediaDownloader/
├── main.py                 Entry point - dependency checks, creates the pywebview window
├── backend/                Python backend (package)
│   ├── api.py              Object exposed to JavaScript (window.pywebview.api)
│   ├── events.py           Pushes events from Python threads to the page
│   ├── services.py         Per-service runtimes: resolve URL, queue tasks, forward updates
│   ├── downloader.py       Download logic for all sites (yt-dlp)
│   ├── record.py           Spotify recording pipeline (play, record, encode, tag)
│   ├── recorder.py         Per-process audio capture (WASAPI process loopback)
│   ├── spotify_session.py  Hidden Spotify player window: login, playback, state
│   ├── login_page.py       Page shown in the browser after the Spotify login
│   ├── converter.py        FFmpeg helpers + mutagen metadata embedding
│   ├── clipboard.py        Windows clipboard access for the Paste button
│   ├── app_update.py       Finds, downloads and verifies a newer app release (GitHub)
│   ├── updater.py          Keeps yt-dlp current inside the .exe (downloads from PyPI)
│   ├── secure_store.py     Encrypts the Spotify secret and login tokens (Windows DPAPI)
│   ├── logs.py             Rotating log file in the data folder
│   ├── errors.py           Short, translated error texts for the queue
│   └── config.py           Constants, format definitions, translations, config I/O
├── frontend/               HTML, CSS and JavaScript UI (vanilla ES modules)
│   ├── index.html          Main window
│   ├── recorder.html       Hidden Spotify player page (Web Playback SDK)
│   ├── css/                Styles (motion.css holds all animations)
│   ├── js/                 Views, components, bridge to Python
│   └── tests/              Node unit tests
├── img/                    App icon
├── tools/                  Dev helpers (smoke test, mock data, icon generator)
├── build.py                PyInstaller + Inno Setup build (optional code signing, see the file header)
├── installer.iss           Inno Setup script
└── requirements.txt
```

### Development

```
node --test frontend/tests/*.test.mjs     # frontend unit tests
python tools/smoke_test.py                # drive the real window (no downloads)
```

Tutorials linked from the app live in the GitHub wiki; the app links to
`https://github.com/EmilDeuOfficial/DeuMediaDownloader/wiki/<page>` (see `WIKI_PAGES` in
`backend/config.py`).

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
| Opus | 256 / 192 / 160 kbps | Modern open format, small files |
| FLAC | Lossless | Compressed, tags and cover art |
| AIFF | Lossless | Uncompressed, tags and cover art (Spotify downloads) |
| WAV | Lossless | Uncompressed, large files |
| Original | Best | The audio exactly as the site delivers it, no re-encoding (usually `.opus` or `.m4a`) |

**Original** is the fastest choice and loses nothing; it is not offered for Spotify recording
and is never normalized. **Normalize Audio** in the settings of each downloader evens out
the volume (FFmpeg `loudnorm`).

The audio source is YouTube (about 256 kbps at best), so the lossless formats are
convenient containers, not better sound than a 320 kbps MP3.

Video (YouTube, TikTok and Instagram):

| Format | Qualities | Notes |
|---|---|---|
| MP4 | 2160p (4K) / 1440p (2K) / 1080p / 720p / 480p / 360p | Widely compatible |
| MOV | 2160p (4K) / 1440p (2K) / 1080p / 720p / 480p / 360p | Converted with FFmpeg |
| AVI | 2160p (4K) / 1440p (2K) / 1080p / 720p / 480p / 360p | Converted with FFmpeg (Xvid) |
| MKV | Best / 2160p (4K) / 1440p (2K) / 1080p / 720p / 480p / 360p | Best available quality |
| WebM | Best / 2160p (4K) / 1440p (2K) / 1080p / 720p / 480p / 360p | Open format |

The heights are upper bounds: a video that only exists in 1080p is saved in 1080p. Above
1080p YouTube only offers AV1 and VP9 streams, so 2K and 4K files use those codecs (some
older players need an AV1 extension). 4K files are large, and MOV and AVI are re-encoded
after the download, so 4K in those two takes a long time.

The lists are generated from two small tables in `config.py` (`_AUDIO_SPEC`,
`_VIDEO_SPEC`); audio below 129 kbps and video below 360p are not offered.

---

## Troubleshooting

**"FFmpeg ✗" shown in the header** - FFmpeg is not on your PATH.
Install it and restart the app.

**"No Spotify API credentials"** - Open Settings and enter your credentials.

**Track not found / wrong match** - yt-dlp searches YouTube Music;
rare tracks may not be available there.

**Some YouTube formats are missing** - yt-dlp needs the Deno JavaScript runtime for
YouTube. Install it with `winget install DenoLand.Deno` and restart the app.

**Something else went wrong** - the app writes a log file to
`%USERPROFILE%/.spotify_downloader/logs/app.log`. Please attach it to a bug report.

---

## Legal Notice

This tool is intended for personal use with content you have the right to download.
Respect the Spotify Terms of Service and applicable copyright laws.
