import json
from pathlib import Path

APP_NAME = "DeuDownloader"
APP_VERSION = "1.5.0"
CONFIG_FILE   = Path.home() / ".spotify_downloader" / "config.json"
LANGUAGE_FILE = Path.home() / ".spotify_downloader" / "language"

# Source is YouTube Music (max ~256 kbps AAC/Opus) — lossless formats are intentionally excluded
AUDIO_FORMATS = {
    "MP3 128 kbps":  {"ext": "mp3", "codec": "libmp3lame", "bitrate": "128k", "ydl_quality": "128"},
    "MP3 192 kbps":  {"ext": "mp3", "codec": "libmp3lame", "bitrate": "192k", "ydl_quality": "192"},
    "MP3 256 kbps":  {"ext": "mp3", "codec": "libmp3lame", "bitrate": "256k", "ydl_quality": "256"},
    "MP3 320 kbps":  {"ext": "mp3", "codec": "libmp3lame", "bitrate": "320k", "ydl_quality": "320"},
    "AAC 256 kbps":        {"ext": "m4a", "codec": "aac",       "bitrate": "256k", "ydl_quality": "256"},
    "OGG Vorbis (320 kbps)": {"ext": "ogg", "codec": "libvorbis", "bitrate": "320k", "ydl_quality": "320"},
    "WAV (Lossless)":      {"ext": "wav", "codec": "pcm_s16le", "bitrate": None,   "ydl_quality": "0"},
}

VIDEO_FORMATS = {
    "MP4 1080p (H.264)":  {"ext": "mp4",  "ydl_format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"},
    "MP4 720p (H.264)":   {"ext": "mp4",  "ydl_format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"},
    "MP4 480p (H.264)":   {"ext": "mp4",  "ydl_format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"},
    "MP4 360p (H.264)":   {"ext": "mp4",  "ydl_format": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best"},
    "MKV (Best Quality)": {"ext": "mkv",  "ydl_format": "bestvideo+bestaudio/best"},
    "WebM (VP9)":         {"ext": "webm", "ydl_format": "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best"},
}

QUALITY_LABELS = {
    "Standard (128 kbps)": "128",
    "High (256 kbps)":     "256",
    "Ultra (320 kbps)":    "320",
    "Lossless":            "0",
}

# Map from ext to mutagen format tag for cover art MIME
COVER_MIME = "image/jpeg"

COLORS = {
    "bg_primary":    "#0d1117",
    "bg_secondary":  "#161b22",
    "bg_card":       "#21262d",
    "bg_input":      "#1c2128",
    "accent":        "#1DB954",   # Spotify green
    "accent_hover":  "#17a347",
    "accent_dim":    "#145c30",
    "text_primary":  "#e6edf3",
    "text_secondary":"#8b949e",
    "text_muted":    "#484f58",
    "success":       "#1DB954",
    "warning":       "#e3b341",
    "error":         "#f85149",
    "progress_bg":   "#21262d",
    "progress_fill": "#1DB954",
    "border":        "#30363d",
}

FONT_FAMILY = "Segoe UI"

DEFAULT_CONFIG = {
    "spotify_client_id":     "",
    "spotify_client_secret": "",
    "output_dir":            str(Path.home() / "Music" / "Spotify Downloads"),
    "default_format":        "MP3 256 kbps",
    "yt_format":             "MP3 256 kbps",
    "yt_format_audio":       "MP3 256 kbps",
    "yt_format_video":       "MP4 1080p (H.264)",
    "yt_media_type":         "Audio",
    "concurrent_downloads":  2,
    # Spotify download options
    "sp_skip_existing":      True,
    "sp_embed_cover":        True,
    "sp_normalize":          False,
    "sp_open_folder":        False,
    # YouTube-specific settings
    "yt_concurrent":         2,
    "yt_embed_thumbnail":    True,
    "yt_write_subtitles":    False,
    "yt_subtitle_langs":     "en",
    "yt_sponsorblock":       False,
    "yt_rate_limit":         "",
    # TikTok-specific settings
    "tt_format_video":       "MP4 1080p (H.264)",
    "tt_format_audio":       "MP3 256 kbps",
    "tt_media_type":         "Video",
    "tt_concurrent":         2,
    "tt_embed_thumbnail":    True,
    "tt_rate_limit":         "",
    "tt_win_geo":            "820x720",
    # Filename templates
    "sp_filename_template":  "{artist} - {title}",
    "yt_filename_template":  "{title}",
    "tt_filename_template":  "{title}",
}

# Filename template options  {format_string: translation_key}
SP_FILENAME_TEMPLATES = {
    "{artist} - {title}":        "tmpl_artist_title",
    "{title} - {artist}":        "tmpl_title_artist",
    "{title}":                   "tmpl_title_only",
    "{artist} - {title} ({year})": "tmpl_artist_title_year",
    "{title} [{album}]":         "tmpl_title_album",
}

YT_FILENAME_TEMPLATES = {
    "{title}":        "tmpl_title_only",
    "{artist} - {title}": "tmpl_artist_title",
    "{title} - {artist}": "tmpl_title_artist",
}

TT_FILENAME_TEMPLATES = {
    "{title}":        "tmpl_title_only",
    "{artist} - {title}": "tmpl_artist_title",
    "{title} - {artist}": "tmpl_title_artist",
}

# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # Labels
        "spotify_url":         "Spotify URL",
        "youtube_url":         "YouTube URL",
        "format":              "Format",
        "save_to":             "Save to",
        "type":                "Type",
        # Buttons
        "browse":              "Browse",
        "download":            "  Download",
        "loading":             "  Loading\u2026",
        "paste":               "Paste",
        "clear":               "Clear",
        "audio_btn":           "\u266a  Audio",
        "video_btn":           "\u25b6  Video",
        "clear_done":          "Clear Done",
        "clear_log":           "Clear",
        "save_btn":            "Save",
        "cancel_btn":          "Cancel",
        # Panel titles
        "download_queue":      "Download Queue",
        "log_panel":           "Log",
        # Settings dialog
        "settings_title":      "Settings",
        "spotify_api_creds":   "Spotify API Credentials",
        "redirect_hint":       "developer.spotify.com  \u2192  Redirect URI: http://127.0.0.1:8888/callback",
        "client_id":           "Client ID",
        "client_id_ph":        "Paste your Client ID\u2026",
        "client_secret":       "Client Secret",
        "client_secret_ph":    "Paste your Client Secret\u2026",
        "concurrent_dl":       "Concurrent Downloads",
        # Spotify download options
        "sp_open_dashboard":       "Open Spotify Developer Dashboard",
        "sp_redirect_uri_lbl":     "Redirect URI (select & copy):",
        "sp_sec_options":          "Download Options",
        "sp_skip_existing_lbl":    "Skip Existing Files",
        "sp_skip_existing_desc":   "Don't re-download tracks that already exist on disk",
        "sp_embed_cover_lbl":      "Embed Cover Art",
        "sp_embed_cover_desc":     "Embed the album artwork into the audio file",
        "sp_normalize_lbl":        "Normalize Audio",
        "sp_normalize_desc":       "Apply loudnorm filter for consistent volume across tracks",
        "sp_open_folder_lbl":      "Open Folder When Done",
        "sp_open_folder_desc":     "Open the output folder once all queued downloads finish",
        # Launcher
        "launcher_title":      "DeuDownloader",
        "choose_downloader":   "Choose a Downloader",
        "spotify_desc":        "Tracks, playlists\nand albums",
        "youtube_desc":        "Videos and\nplaylists",
        "open_spotify":        "Open Spotify",
        "open_youtube":        "Open YouTube",
        "open_tiktok":         "Open TikTok",
        "tiktok_desc":         "Videos and\naudio",
        # Window titles
        "spotify_win_title":   f"{APP_NAME}  v{APP_VERSION}",
        "youtube_win_title":   "YouTube Downloader",
        "tiktok_win_title":    "TikTok Downloader",
        # Log / status messages
        "no_credentials":      "No Spotify API credentials. Open Settings to configure them.",
        "spotify_init":        "Spotify client initialised.",
        "spotify_auth_err":    "Spotify auth error: {}",
        "settings_saved":      "Settings saved.",
        "fetching_spotify":    "Fetching {} info from Spotify\u2026",
        "fetching_youtube":    "Fetching YouTube info\u2026",
        "fetching_tiktok":     "Fetching TikTok info\u2026",
        "queued_n_tracks":     "Queued {} track(s)  [{}]",
        "queued_n_videos":     "Queued {} video(s)  [{}]",
        "err_resolving":       "Error resolving URL: {}",
        "log_done":            "Done:  {}",
        "log_error":           "Error: {} \u2014 {}",
        "log_queued":          "Queued: {}",
        "ffmpeg_ok":           "FFmpeg \u2713",
        "ffmpeg_fail":         "FFmpeg \u2717",
        # Messageboxes
        "mb_no_url_title":     "No URL",
        "mb_no_url_spotify":   "Please paste a Spotify URL first.",
        "mb_no_url_youtube":   "Please paste a YouTube URL first.",
        "mb_no_url_tiktok":    "Please paste a TikTok URL first.",
        "mb_no_outdir_title":  "No Output Directory",
        "mb_no_outdir":        "Please choose an output directory.",
        "mb_api_title":        "API Credentials Required",
        "mb_api_msg":          "Please open Settings and enter your Spotify API credentials\n(Client ID and Client Secret).\n\nGet them for free at: developer.spotify.com",
        "mb_error_title":      "Error",
        "select_outdir":       "Select Output Directory",
        # FFmpeg install note
        "ffmpeg_will_install": "FFmpeg: will be installed automatically",
        # Settings tabs
        "tab_settings":           "Settings",
        "tab_uninstall":          "Uninstall",
        # Uninstall tab
        "uninstall_section":      "Uninstall & Cleanup",
        "clear_data_btn":         "Clear Config Data",
        "clear_data_desc":        "Removes settings, API credentials and cached data.",
        "uninstall_ffmpeg_btn":   "Uninstall FFmpeg",
        "uninstall_ffmpeg_desc":  "Removes FFmpeg from your system via winget.",
        "uninstall_app_btn":      "Uninstall DeuDownloader",
        "uninstall_app_desc":     "Runs the uninstaller and closes the app.",
        "confirm_clear_data":     "Delete all settings and credentials?\nThis cannot be undone.",
        "confirm_uninstall_ffmpeg": "Uninstall FFmpeg from your system?",
        "confirm_uninstall_app":  "Uninstall DeuDownloader?\nThe app will close now.",
        "no_uninstaller":         "Uninstaller not found.\nPlease use Windows Settings \u2192 Apps.",
        "uninstall_started":      "Uninstall started in background.",
        "yes_btn":                "Yes",
        "no_btn":                 "No",
        # YouTube settings dialog
        "yt_settings_title":      "YouTube Settings",
        "yt_sec_downloads":       "Downloads",
        "yt_concurrent_lbl":      "Parallel Downloads",
        "yt_sec_media":           "Media Processing",
        "yt_embed_thumb_lbl":     "Embed Thumbnail",
        "yt_embed_thumb_desc":    "Embed the video thumbnail into audio files",
        "yt_sponsorblock_lbl":    "Skip Sponsors (SponsorBlock)",
        "yt_sponsorblock_desc":   "Automatically skip sponsored segments via SponsorBlock",
        "yt_sec_subtitles":       "Subtitles",
        "yt_subtitles_lbl":       "Download & Embed Subtitles",
        "yt_subtitles_desc":      "Download subtitles and embed them into the file",
        "yt_subtitle_langs_lbl":  "Languages (comma-separated)",
        "yt_subtitle_langs_ph":   "e.g. en, de",
        "yt_sec_network":         "Network",
        "yt_rate_limit_lbl":      "Speed Limit",
        "yt_rate_no_limit":       "No limit",
        "yt_rate_1m":             "1 MB/s",
        "yt_rate_5m":             "5 MB/s",
        "yt_rate_10m":            "10 MB/s",
        "yt_rate_50m":            "50 MB/s",
        # Filename templates
        "filename_template_lbl":  "Filename",
        "filename_template_desc": "Placeholders: {artist}, {title}, {year}, {album}",
        "tmpl_artist_title":      "Artist — Title",
        "tmpl_title_artist":      "Title — Artist",
        "tmpl_title_only":        "Title only",
        "tmpl_artist_title_year": "Artist — Title (Year)",
        "tmpl_title_album":       "Title [Album]",
        # TikTok settings dialog
        "tt_settings_title":      "TikTok Settings",
        "tt_sec_downloads":       "Downloads",
        "tt_concurrent_lbl":      "Parallel Downloads",
        "tt_sec_media":           "Media Processing",
        "tt_embed_thumb_lbl":     "Embed Thumbnail",
        "tt_embed_thumb_desc":    "Embed the video cover into audio files",
        "tt_sec_network":         "Network",
        "tt_rate_limit_lbl":      "Speed Limit",
    },
    "de": {
        # Labels
        "spotify_url":         "Spotify URL",
        "youtube_url":         "YouTube URL",
        "format":              "Format",
        "save_to":             "Speichern in",
        "type":                "Typ",
        # Buttons
        "browse":              "Durchsuchen",
        "download":            "  Herunterladen",
        "loading":             "  L\u00e4dt\u2026",
        "paste":               "Einf\u00fcgen",
        "clear":               "L\u00f6schen",
        "audio_btn":           "\u266a  Audio",
        "video_btn":           "\u25b6  Video",
        "clear_done":          "Erledigte leeren",
        "clear_log":           "L\u00f6schen",
        "save_btn":            "Speichern",
        "cancel_btn":          "Abbrechen",
        # Panel titles
        "download_queue":      "Download-Warteschlange",
        "log_panel":           "Protokoll",
        # Settings dialog
        "settings_title":      "Einstellungen",
        "spotify_api_creds":   "Spotify-API-Zugangsdaten",
        "redirect_hint":       "developer.spotify.com  \u2192  Redirect URI: http://127.0.0.1:8888/callback",
        "client_id":           "Client-ID",
        "client_id_ph":        "Client-ID einf\u00fcgen\u2026",
        "client_secret":       "Client-Secret",
        "client_secret_ph":    "Client-Secret einf\u00fcgen\u2026",
        "concurrent_dl":       "Gleichzeitige Downloads",
        # Spotify download options
        "sp_open_dashboard":       "Spotify Developer Dashboard \u00f6ffnen",
        "sp_redirect_uri_lbl":     "Redirect URI (markieren & kopieren):",
        "sp_sec_options":          "Download-Optionen",
        "sp_skip_existing_lbl":    "Vorhandene Dateien \u00fcberspringen",
        "sp_skip_existing_desc":   "Tracks nicht erneut herunterladen, wenn sie bereits vorhanden sind",
        "sp_embed_cover_lbl":      "Cover einbetten",
        "sp_embed_cover_desc":     "Albumcover in die Audiodatei einbetten",
        "sp_normalize_lbl":        "Audio normalisieren",
        "sp_normalize_desc":       "Loudnorm-Filter f\u00fcr gleichm\u00e4\u00dfige Lautst\u00e4rke anwenden",
        "sp_open_folder_lbl":      "Ordner nach Fertigstellung \u00f6ffnen",
        "sp_open_folder_desc":     "Ausgabeordner \u00f6ffnen, wenn alle Downloads abgeschlossen sind",
        # Launcher
        "launcher_title":      "DeuDownloader",
        "choose_downloader":   "Downloader w\u00e4hlen",
        "spotify_desc":        "Tracks, Playlisten\nund Alben",
        "youtube_desc":        "Videos und\nPlaylisten",
        "open_spotify":        "Spotify \u00f6ffnen",
        "open_youtube":        "YouTube \u00f6ffnen",
        "open_tiktok":         "TikTok \u00f6ffnen",
        "tiktok_desc":         "Videos und\nAudio",
        # Window titles
        "spotify_win_title":   f"{APP_NAME}  v{APP_VERSION}",
        "youtube_win_title":   "YouTube Downloader",
        "tiktok_win_title":    "TikTok Downloader",
        # Log / status messages
        "no_credentials":      "Keine Spotify-API-Zugangsdaten. Einstellungen \u00f6ffnen.",
        "spotify_init":        "Spotify-Client initialisiert.",
        "spotify_auth_err":    "Spotify-Authentifizierungsfehler: {}",
        "settings_saved":      "Einstellungen gespeichert.",
        "fetching_spotify":    "{}-Info von Spotify wird geladen\u2026",
        "fetching_youtube":    "YouTube-Info wird geladen\u2026",
        "fetching_tiktok":     "TikTok-Info wird geladen\u2026",
        "queued_n_tracks":     "{} Track(s) in Warteschlange  [{}]",
        "queued_n_videos":     "{} Video(s) in Warteschlange  [{}]",
        "err_resolving":       "Fehler beim Laden der URL: {}",
        "log_done":            "Fertig:  {}",
        "log_error":           "Fehler: {} \u2014 {}",
        "log_queued":          "Eingereiht: {}",
        "ffmpeg_ok":           "FFmpeg \u2713",
        "ffmpeg_fail":         "FFmpeg \u2717",
        # Messageboxes
        "mb_no_url_title":     "Keine URL",
        "mb_no_url_spotify":   "Bitte zuerst eine Spotify-URL einf\u00fcgen.",
        "mb_no_url_youtube":   "Bitte zuerst eine YouTube-URL einf\u00fcgen.",
        "mb_no_url_tiktok":    "Bitte zuerst eine TikTok-URL einf\u00fcgen.",
        "mb_no_outdir_title":  "Kein Ausgabeordner",
        "mb_no_outdir":        "Bitte einen Ausgabeordner w\u00e4hlen.",
        "mb_api_title":        "API-Zugangsdaten erforderlich",
        "mb_api_msg":          "Bitte \u00f6ffne die Einstellungen und gib deine Spotify-API-Zugangsdaten ein\n(Client-ID und Client-Secret).\n\nKostenlos erh\u00e4ltlich unter: developer.spotify.com",
        "mb_error_title":      "Fehler",
        "select_outdir":       "Ausgabeordner w\u00e4hlen",
        # FFmpeg install note
        "ffmpeg_will_install": "FFmpeg: wird automatisch installiert",
        # Settings tabs
        "tab_settings":           "Einstellungen",
        "tab_uninstall":          "Deinstallieren",
        # Uninstall tab
        "uninstall_section":      "Deinstallation & Bereinigung",
        "clear_data_btn":         "Konfigurationsdaten l\u00f6schen",
        "clear_data_desc":        "Entfernt Einstellungen, API-Zugangsdaten und Cache.",
        "uninstall_ffmpeg_btn":   "FFmpeg deinstallieren",
        "uninstall_ffmpeg_desc":  "Entfernt FFmpeg \u00fcber winget vom System.",
        "uninstall_app_btn":      "DeuDownloader deinstallieren",
        "uninstall_app_desc":     "Startet den Deinstaller und schlie\u00dft die App.",
        "confirm_clear_data":     "Alle Einstellungen und Zugangsdaten l\u00f6schen?\nDies kann nicht r\u00fcckg\u00e4ngig gemacht werden.",
        "confirm_uninstall_ffmpeg": "FFmpeg vom System deinstallieren?",
        "confirm_uninstall_app":  "DeuDownloader deinstallieren?\nDie App wird jetzt geschlossen.",
        "no_uninstaller":         "Deinstaller nicht gefunden.\nBitte \u00fcber Windows-Einstellungen \u2192 Apps deinstallieren.",
        "uninstall_started":      "Deinstallation im Hintergrund gestartet.",
        "yes_btn":                "Ja",
        "no_btn":                 "Nein",
        # YouTube settings dialog
        "yt_settings_title":      "YouTube Einstellungen",
        "yt_sec_downloads":       "Downloads",
        "yt_concurrent_lbl":      "Parallele Downloads",
        "yt_sec_media":           "Medienverarbeitung",
        "yt_embed_thumb_lbl":     "Thumbnail einbetten",
        "yt_embed_thumb_desc":    "Video-Thumbnail in Audiodateien einbetten",
        "yt_sponsorblock_lbl":    "Werbung \u00fcberspringen (SponsorBlock)",
        "yt_sponsorblock_desc":   "Gesponserte Segmente automatisch \u00fcberspringen",
        "yt_sec_subtitles":       "Untertitel",
        "yt_subtitles_lbl":       "Untertitel herunterladen & einbetten",
        "yt_subtitles_desc":      "Untertitel herunterladen und in die Datei einbetten",
        "yt_subtitle_langs_lbl":  "Sprachen (kommagetrennt)",
        "yt_subtitle_langs_ph":   "z.B. de, en",
        "yt_sec_network":         "Netzwerk",
        "yt_rate_limit_lbl":      "Geschwindigkeitsbegrenzung",
        "yt_rate_no_limit":       "Kein Limit",
        "yt_rate_1m":             "1 MB/s",
        "yt_rate_5m":             "5 MB/s",
        "yt_rate_10m":            "10 MB/s",
        "yt_rate_50m":            "50 MB/s",
        # Filename templates
        "filename_template_lbl":  "Dateiname",
        "filename_template_desc": "Platzhalter: {artist}, {title}, {year}, {album}",
        "tmpl_artist_title":      "Künstler — Titel",
        "tmpl_title_artist":      "Titel — Künstler",
        "tmpl_title_only":        "Nur Titel",
        "tmpl_artist_title_year": "Künstler — Titel (Jahr)",
        "tmpl_title_album":       "Titel [Album]",
        # TikTok settings dialog
        "tt_settings_title":      "TikTok Einstellungen",
        "tt_sec_downloads":       "Downloads",
        "tt_concurrent_lbl":      "Parallele Downloads",
        "tt_sec_media":           "Medienverarbeitung",
        "tt_embed_thumb_lbl":     "Thumbnail einbetten",
        "tt_embed_thumb_desc":    "Video-Cover in Audiodateien einbetten",
        "tt_sec_network":         "Netzwerk",
        "tt_rate_limit_lbl":      "Geschwindigkeitsbegrenzung",
    },
}

_lang = "en"


def load_language() -> None:
    global _lang
    try:
        if LANGUAGE_FILE.exists():
            code = LANGUAGE_FILE.read_text(encoding="utf-8").strip()
            if code in STRINGS:
                _lang = code
    except Exception:
        pass


def T(key: str) -> str:
    return STRINGS.get(_lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))


def load_config() -> dict:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
