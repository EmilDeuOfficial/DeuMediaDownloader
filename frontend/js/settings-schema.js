// Declarative description of the settings dialogs (ported from the three Tk dialogs).
//
// Section:  { titleKey, inside, fields }   inside=true draws the title inside the card
// Field types:
//   link      { labelKey, url }
//   readonly  { labelKey, value }
//   text      { key, labelKey, placeholderKey, secret?, enabledBy? }
//   slider    { key, labelKey?, min, max, default }
//   toggle    { key, labelKey, descKey, default }
//   select    { key, labelKey?, options, width, default }   options: name of a list in bootstrap
//                                                          options ("yt_templates", ...) or "rate"
//   note      { textKey }
//   file      { key, labelKey, descKey, placeholderKey }

export const RATE_OPTIONS = [
  ["", "yt_rate_no_limit"],
  ["1M", "yt_rate_1m"],
  ["5M", "yt_rate_5m"],
  ["10M", "yt_rate_10m"],
  ["50M", "yt_rate_50m"],
];

const filenameSection = (options, key, def) => ({
  titleKey: "filename_template_lbl",
  inside: false,
  fields: [
    { type: "note", textKey: "filename_template_desc" },
    { type: "select", key, options, width: 280, default: def },
  ],
});

export const SETTINGS_SCHEMA = {
  spotify: {
    titleKey: "settings_title",
    height: 580,
    sections: [
      {
        titleKey: "spotify_api_creds",
        inside: false,
        fields: [
          { type: "link", labelKey: "sp_open_dashboard", url: "https://developer.spotify.com/dashboard" },
          { type: "readonly", labelKey: "sp_redirect_uri_lbl", value: "http://127.0.0.1:8888/callback" },
          { type: "text", key: "spotify_client_id", labelKey: "client_id", placeholderKey: "client_id_ph" },
          { type: "text", key: "spotify_client_secret", labelKey: "client_secret", placeholderKey: "client_secret_ph", secret: true },
        ],
      },
      {
        titleKey: "concurrent_dl",
        inside: false,
        fields: [{ type: "slider", key: "concurrent_downloads", min: 1, max: 5, default: 2 }],
      },
      {
        titleKey: "sp_sec_options",
        inside: false,
        fields: [
          { type: "toggle", key: "sp_skip_existing", labelKey: "sp_skip_existing_lbl", descKey: "sp_skip_existing_desc", default: true },
          { type: "toggle", key: "sp_embed_cover", labelKey: "sp_embed_cover_lbl", descKey: "sp_embed_cover_desc", default: true },
          { type: "toggle", key: "sp_normalize", labelKey: "sp_normalize_lbl", descKey: "sp_normalize_desc", default: false },
          { type: "toggle", key: "sp_open_folder", labelKey: "sp_open_folder_lbl", descKey: "sp_open_folder_desc", default: false },
        ],
      },
      filenameSection("sp_templates", "sp_filename_template", "{artist} - {title}"),
    ],
  },

  youtube: {
    titleKey: "yt_settings_title",
    height: 560,
    sections: [
      {
        titleKey: "yt_sec_downloads",
        inside: true,
        fields: [{ type: "slider", key: "yt_concurrent", labelKey: "yt_concurrent_lbl", min: 1, max: 5, default: 2 }],
      },
      {
        titleKey: "yt_sec_media",
        inside: true,
        fields: [
          { type: "toggle", key: "yt_embed_thumbnail", labelKey: "yt_embed_thumb_lbl", descKey: "yt_embed_thumb_desc", default: true },
          { type: "toggle", key: "yt_sponsorblock", labelKey: "yt_sponsorblock_lbl", descKey: "yt_sponsorblock_desc", default: false },
          { type: "toggle", key: "yt_open_folder", labelKey: "sp_open_folder_lbl", descKey: "sp_open_folder_desc", default: true },
        ],
      },
      {
        titleKey: "yt_sec_subtitles",
        inside: true,
        fields: [
          { type: "toggle", key: "yt_write_subtitles", labelKey: "yt_subtitles_lbl", descKey: "yt_subtitles_desc", default: false },
          { type: "text", key: "yt_subtitle_langs", labelKey: "yt_subtitle_langs_lbl", placeholderKey: "yt_subtitle_langs_ph", enabledBy: "yt_write_subtitles" },
        ],
      },
      {
        titleKey: "yt_sec_network",
        inside: true,
        fields: [{ type: "select", key: "yt_rate_limit", labelKey: "yt_rate_limit_lbl", options: "rate", width: 200, default: "" }],
      },
      filenameSection("yt_templates", "yt_filename_template", "{title}"),
    ],
  },

  tiktok: {
    titleKey: "tt_settings_title",
    height: 600,
    sections: [
      {
        titleKey: "tt_sec_downloads",
        inside: true,
        fields: [{ type: "slider", key: "tt_concurrent", labelKey: "tt_concurrent_lbl", min: 1, max: 5, default: 2 }],
      },
      {
        titleKey: "tt_sec_media",
        inside: true,
        fields: [
          { type: "toggle", key: "tt_embed_thumbnail", labelKey: "tt_embed_thumb_lbl", descKey: "tt_embed_thumb_desc", default: true },
          { type: "toggle", key: "tt_open_folder", labelKey: "sp_open_folder_lbl", descKey: "sp_open_folder_desc", default: true },
        ],
      },
      {
        titleKey: "tt_sec_network",
        inside: true,
        fields: [{ type: "select", key: "tt_rate_limit", labelKey: "tt_rate_limit_lbl", options: "rate", width: 200, default: "" }],
      },
      {
        titleKey: "tt_sec_auth",
        inside: true,
        fields: [
          { type: "note", textKey: "tt_cookies_desc" },
          { type: "select", key: "tt_cookies_browser", labelKey: "tt_cookies_lbl", options: "cookie_browsers", width: 260, default: "" },
          { type: "file", key: "tt_cookies_file", labelKey: "tt_cookies_file_lbl", descKey: "tt_cookies_file_desc", placeholderKey: "tt_cookies_file_ph", clearKey: "tt_cookies_file_clear" },
        ],
      },
      filenameSection("tt_templates", "tt_filename_template", "{title}"),
    ],
  },
};

// Shared "Uninstall" tab.
export const UNINSTALL_ROWS = [
  { icon: "trash", titleKey: "clear_data_btn", descKey: "clear_data_desc", confirmKey: "confirm_clear_data", action: "clear_data", danger: false },
  { icon: "gear", titleKey: "uninstall_ffmpeg_btn", descKey: "uninstall_ffmpeg_desc", confirmKey: "confirm_uninstall_ffmpeg", action: "uninstall_ffmpeg", danger: false, doneKey: "uninstall_started" },
  { icon: "close", titleKey: "uninstall_app_btn", descKey: "uninstall_app_desc", confirmKey: "confirm_uninstall_app", action: "uninstall_app", danger: true },
];
