# Spotify Song Downloader

A modern desktop application to download Spotify tracks, playlists, and albums
as high-quality audio files (MP3, FLAC, WAV, AAC, OGG).

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| FFmpeg | Audio conversion & quality control |
| Spotify Developer Account | API credentials (free) |

---

## Quick Start

### 1 — Install FFmpeg

**Windows (recommended — winget):**
```
winget install ffmpeg
```
Or download from https://ffmpeg.org/download.html and add `bin/` to your PATH.

**Verify:**
```
ffmpeg -version
```

---

### 2 — Install Python dependencies

```
pip install -r requirements.txt
```

---

### 3 — Get Spotify API credentials (free)

1. Go to https://developer.spotify.com/dashboard
2. Log in and click **Create app**
3. Set any name/description; Redirect URI: `http://localhost:8888`
4. Copy your **Client ID** and **Client Secret**

---

### 4 — Run the application

```
python main.py
```

On first launch, click **⚙ Settings** in the top-right and paste your
Spotify Client ID and Client Secret, then click **Save**.

---

## Usage

1. Copy a Spotify URL (track, playlist, or album)
2. Paste it into the URL field (or click **Paste**)
3. Choose your output **Format** (MP3 320, FLAC, WAV, …)
4. Select an output folder with **Browse**
5. Click **Download**

Tracks are added to the queue and downloaded in parallel.
Metadata (title, artist, album, cover art) is automatically embedded.

---

## Project Structure

```
spotify_downloader/
├── main.py          Entry point — dependency checks + launch
├── downloader.py    Spotify metadata + yt-dlp download logic
├── converter.py     FFmpeg helpers + mutagen metadata embedding
├── ui.py            CustomTkinter GUI
├── config.py        Constants, format definitions, config I/O
├── requirements.txt
└── README.md
```

---

## Supported Output Formats

| Format | Bitrate | Notes |
|---|---|---|
| MP3 | 128 / 192 / 256 / 320 kbps | Widely compatible |
| FLAC | Lossless | Highest quality |
| WAV | Lossless | Uncompressed, large files |
| AAC | 256 kbps | Great for Apple devices |
| OGG Vorbis | ~320 kbps | Open format |

---

## Troubleshooting

**"FFmpeg ✗" shown in the header** — FFmpeg is not on your PATH.
Install it and restart the app.

**"No Spotify API credentials"** — Open Settings and enter your credentials.

**Track not found / wrong match** — yt-dlp searches YouTube Music;
rare tracks may not be available there.

---

## Legal Notice

This tool is intended for personal use with content you have the right to download.
Respect the Spotify Terms of Service and applicable copyright laws.
