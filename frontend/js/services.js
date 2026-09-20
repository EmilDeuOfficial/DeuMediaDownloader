// One descriptor per service. ToolView and the launcher are driven entirely by these.
export const SERVICES = {
  spotify: {
    id: "spotify",
    title: "Spotify",
    launcher: { btn: "#1db954", btnHover: "#17a347", btnText: "#ffffff", descKey: "spotify_desc", openKey: "open_spotify" },
    urlLabelKey: "spotify_url",
    urlPlaceholderKey: "spotify_url_ph",
    queueGlyph: "note",
    mediaToggle: false,
    dropdownWidth: 220,
    cfg: { outDir: "output_dir", format: "default_format", formatDefault: "MP3 (320 kbps)" },
  },
  youtube: {
    id: "youtube",
    title: "YouTube",
    launcher: { btn: "#cc2222", btnHover: "#aa1111", btnText: "#ffffff", descKey: "youtube_desc", openKey: "open_youtube" },
    urlLabelKey: "youtube_url",
    urlPlaceholderKey: "youtube_url_ph",
    queueGlyph: "play",
    mediaToggle: true,
    dropdownWidth: 220,
    cfg: {
      outDir: "yt_output_dir",
      formatAudio: "yt_format_audio",
      formatVideo: "yt_format_video",
      mediaType: "yt_media_type",
      mediaDefault: "Audio",
    },
  },
  tiktok: {
    id: "tiktok",
    title: "TikTok",
    launcher: { btn: "#dc1a4b", btnHover: "#c71542", btnText: "#ffffff", descKey: "tiktok_desc", openKey: "open_tiktok" },
    urlLabelKey: "tiktok_url",
    urlPlaceholderKey: "tiktok_url_ph",
    queueGlyph: "note",
    mediaToggle: true,
    dropdownWidth: 220,
    cfg: {
      outDir: "tt_output_dir",
      formatAudio: "tt_format_audio",
      formatVideo: "tt_format_video",
      mediaType: "tt_media_type",
      mediaDefault: "Video",
    },
  },
};

export const SERVICE_ORDER = ["spotify", "youtube", "tiktok"];
export const AUDIO_DEFAULT = "MP3 (320 kbps)";
export const VIDEO_DEFAULT = "MP4 (1080p)";
