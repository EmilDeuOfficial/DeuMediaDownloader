import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

import customtkinter as ctk

from assets import spotify_icon, youtube_icon, tiktok_icon, warmup_icons
from config import (
    AUDIO_FORMATS, VIDEO_FORMATS, COLORS, FONT_FAMILY, APP_NAME, APP_VERSION,
    load_config, save_config, T,
)
from downloader import (
    # Shared
    DownloadStatus, _apply_template,
    # Spotify
    SpotifyClient, SpotifyDownloadManager, DownloadTask, TrackInfo,
    # YouTube
    YouTubeTask, YouTubeDownloadManager, extract_youtube_entries,
    # TikTok
    TikTokTask, TikTokDownloadManager, extract_tiktok_entries,
)

# Global CustomTkinter appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

C = COLORS  # alias


# ---------------------------------------------------------------------------
# Custom Dropdown Widget
# ---------------------------------------------------------------------------

def _bring_to_front(root: ctk.CTk):
    """Temporarily set topmost so the window appears in front of other apps on startup."""
    try:
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
        root.after(300, lambda: root.attributes("-topmost", False))
    except Exception:
        pass


def _center_geometry(root: ctk.CTk, w: int, h: int) -> str:
    """Return a geometry string centered on the primary screen."""
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    return f"{w}x{h}+{x}+{y}"


def _apply_win11_rounded(hwnd, radius: int = 2):
    """Apply Windows 11 rounded corners via DWM (DWMWCP_ROUND=2).
    Walks up to the real OS top-level HWND via GetAncestor so it works even
    when passed the child HWND returned by winfo_id()."""
    try:
        import ctypes
        top = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            top or hwnd, 33, ctypes.byref(ctypes.c_int(radius)), ctypes.sizeof(ctypes.c_int)
        )
    except Exception:
        pass


def _apply_taskbar_button(root: ctk.CTk):
    """Force the overrideredirect window to appear in the taskbar with the app icon."""
    try:
        import ctypes
        GWL_EXSTYLE      = -20
        WS_EX_APPWINDOW  = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        SWP_FLAGS        = 0x0001 | 0x0002 | 0x0004 | 0x0020
        child = root.winfo_id()
        hwnd  = ctypes.windll.user32.GetAncestor(child, 2) or child
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)

        base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        ico  = str(base / "img" / "app.ico")

        # Set via tkinter so the window class icon and alt-tab thumbnail also update
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

        # Load big and small icons at the correct system-metric sizes
        cx_big   = ctypes.windll.user32.GetSystemMetrics(11)   # SM_CXICON   (32 or 48)
        cx_small = ctypes.windll.user32.GetSystemMetrics(49)   # SM_CXSMICON (16 or 24)
        LR_LOADFROMFILE = 0x0010
        hbig   = ctypes.windll.user32.LoadImageW(None, ico, 1, cx_big,   cx_big,   LR_LOADFROMFILE)
        hsmall = ctypes.windll.user32.LoadImageW(None, ico, 1, cx_small, cx_small, LR_LOADFROMFILE)
        if hbig:
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hbig)    # WM_SETICON ICON_BIG
        if hsmall:
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hsmall)  # WM_SETICON ICON_SMALL
    except Exception:
        pass


class CustomDropdown(ctk.CTkFrame):
    """Dropdown styled to match CTkEntry fields."""

    def __init__(self, parent, variable: ctk.StringVar, values: list,
                 width: int = 210, accent: str = None, accent_dim: str = None, **kwargs):
        super().__init__(parent, width=width, height=34,
                         fg_color=C["border"], corner_radius=6,
                         border_width=0, **kwargs)
        self.pack_propagate(False)
        self.grid_propagate(False)

        self._var       = variable
        self._values    = values
        self._width     = width
        self._popup     = None
        self._accent     = accent     or C["accent"]
        self._accent_dim = accent_dim or C["accent_dim"]

        self._inner = ctk.CTkFrame(self, fg_color=C["bg_input"], corner_radius=5)
        self._inner.pack(fill="both", expand=True, padx=1, pady=1)

        self._label = ctk.CTkLabel(
            self._inner, text=self._var.get(),
            font=(FONT_FAMILY, 12),
            text_color=C["text_primary"],
            anchor="w", cursor="hand2", fg_color="transparent",
        )
        self._label.pack(side="left", fill="both", expand=True, padx=(10, 4))

        self._arrow = ctk.CTkLabel(
            self._inner, text="∨", font=(FONT_FAMILY, 11, "bold"),
            text_color=self._accent, fg_color="transparent",
            width=20, cursor="hand2",
        )
        self._arrow.pack(side="right", padx=(0, 10))

        for w in (self, self._inner, self._label, self._arrow):
            w.bind("<Button-1>", self._toggle)
            w.bind("<Enter>",    lambda e: self._set_hover(True))
            w.bind("<Leave>",    lambda e: self._set_hover(False))

        self._var.trace_add("write", lambda *_: self._label.configure(text=self._var.get()))

    def _set_hover(self, on: bool):
        if self._popup and self._popup.winfo_exists():
            return
        border = self._accent if on else C["border"]
        bg     = C["bg_card"] if on else C["bg_input"]
        self.configure(fg_color=border)
        self._inner.configure(fg_color=bg)

    def _toggle(self, event=None):
        if self._popup and self._popup.winfo_exists():
            self._close_popup()
        else:
            self._open_popup()

    def _open_popup(self):
        self._arrow.configure(text="∧")
        self.configure(fg_color=self._accent)
        self._inner.configure(fg_color=C["bg_card"])

        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 4

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=C["bg_card"])

        item_h   = 36
        padding  = 6
        p_height = len(self._values) * item_h + padding * 2 + 4
        popup.geometry(f"{self._width}x{p_height}+{x}+{y}")

        popup.update_idletasks()
        _apply_win11_rounded(popup.winfo_id())

        outer = tk.Frame(popup, bg=self._accent, bd=0)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        inner = tk.Frame(outer, bg=C["bg_card"], bd=0)
        inner.pack(fill="both", expand=True, padx=0, pady=0)

        tk.Frame(inner, bg=C["bg_card"], height=padding).pack(fill="x")

        for val in self._values:
            is_sel = val == self._var.get()
            row_bg = self._accent_dim if is_sel else C["bg_card"]
            row_fg = self._accent     if is_sel else C["text_primary"]

            row = tk.Frame(inner, bg=row_bg, cursor="hand2", height=item_h)
            row.pack_propagate(False)
            row.pack(fill="x", padx=6)

            bar = tk.Frame(row, bg=self._accent if is_sel else row_bg, width=3)
            bar.pack(side="left", fill="y")

            lbl = tk.Label(row, text=val, font=(FONT_FAMILY, 12),
                           bg=row_bg, fg=row_fg, anchor="w",
                           padx=10, pady=0, cursor="hand2")
            lbl.pack(side="left", fill="both", expand=True)

            def _bind(v, r, l, b):
                def _sel(e=None):
                    self._var.set(v)
                    self._close_popup()
                def _enter(e=None):
                    r.configure(bg=C["bg_secondary"])
                    l.configure(bg=C["bg_secondary"])
                    b.configure(bg=C["bg_secondary"] if v != self._var.get() else self._accent)
                def _leave(e=None):
                    sel = v == self._var.get()
                    rb = self._accent_dim if sel else C["bg_card"]
                    r.configure(bg=rb); l.configure(bg=rb)
                    b.configure(bg=self._accent if sel else rb)
                for w in (r, l):
                    w.bind("<Button-1>", _sel)
                    w.bind("<Enter>",    _enter)
                    w.bind("<Leave>",    _leave)
            _bind(val, row, lbl, bar)

        tk.Frame(inner, bg=C["bg_card"], height=padding).pack(fill="x")

        self._popup = popup
        popup.bind("<FocusOut>", lambda e: self._after_focus_out())
        popup.focus_set()

    def _after_focus_out(self):
        self.after(80, self._close_popup)

    def _close_popup(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
        self._popup = None
        self._arrow.configure(text="∨")
        self.configure(fg_color=C["border"])
        self._inner.configure(fg_color=C["bg_input"])


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, config: dict, on_save: callable,
                 on_quit: callable = None, show_spotify: bool = True):
        super().__init__(parent)
        self.title(T("settings_title"))
        h = 580 if show_spotify else 380
        self.geometry(f"520x{h}")
        self.resizable(False, False)
        self.overrideredirect(True)
        self._config       = dict(config)
        self._on_save      = on_save
        self._on_quit      = on_quit
        self._show_spotify = show_spotify
        self._drag_x = 0
        self._drag_y = 0
        self.configure(fg_color=C["bg_primary"])
        self.after(10,  lambda: _apply_win11_rounded(self.winfo_id()))
        self._build_titlebar()
        self._build()
        self.after(30,  self._center_on_parent)
        self.after(100, self.grab_set)

    def _center_on_parent(self):
        self.update_idletasks()
        px, py = self.master.winfo_x(), self.master.winfo_y()
        pw, ph = self.master.winfo_width(), self.master.winfo_height()
        w,  h  = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _build_titlebar(self):
        bar = ctk.CTkFrame(self, fg_color=C["bg_secondary"], corner_radius=0, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        for w in (bar,):
            w.bind("<ButtonPress-1>", self._titlebar_press)
            w.bind("<B1-Motion>",     self._titlebar_drag)

        icon = ctk.CTkLabel(bar, text="⚙", font=(FONT_FAMILY, 14),
                            text_color=C["accent"])
        icon.pack(side="left", padx=(12, 4))
        icon.bind("<ButtonPress-1>", self._titlebar_press)
        icon.bind("<B1-Motion>",     self._titlebar_drag)

        lbl = ctk.CTkLabel(bar, text=T("settings_title"), font=(FONT_FAMILY, 13, "bold"),
                           text_color=C["text_primary"])
        lbl.pack(side="left")
        lbl.bind("<ButtonPress-1>", self._titlebar_press)
        lbl.bind("<B1-Motion>",     self._titlebar_drag)

        ctk.CTkButton(bar, text="✕", width=36, height=28,
                      fg_color="transparent", hover_color=C["error"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self.destroy).pack(side="right", padx=6)

    def _titlebar_press(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _titlebar_drag(self, event):
        self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _build(self):
        if self._show_spotify:
            tabs = ctk.CTkTabview(self, fg_color=C["bg_secondary"],
                                   segmented_button_fg_color=C["bg_card"],
                                   segmented_button_selected_color=C["accent"],
                                   segmented_button_selected_hover_color=C["accent_hover"],
                                   segmented_button_unselected_color=C["bg_card"],
                                   segmented_button_unselected_hover_color=C["border"],
                                   text_color=C["text_primary"])
            tabs.pack(fill="both", expand=True, padx=12, pady=(8, 12))
            self._build_settings_tab(tabs.add(T("tab_settings")))
            self._build_uninstall_tab(tabs.add(T("tab_uninstall")))
        else:
            # YouTube: only show uninstall section, no tabview needed
            self._build_uninstall_tab(self)

    # ------------------------------------------------------------------ settings tab
    def _build_settings_tab(self, frame):
        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent",
                                        scrollbar_button_color=C["bg_card"],
                                        scrollbar_button_hover_color=C["border"])
        scroll.pack(fill="both", expand=True)

        # --- API credentials ---
        ctk.CTkLabel(scroll, text=T("spotify_api_creds"),
                     font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_secondary"]).pack(anchor="w", padx=14, pady=(10, 2))
        card_api = ctk.CTkFrame(scroll, fg_color=C["bg_secondary"], corner_radius=10)
        card_api.pack(fill="x", padx=0, pady=(0, 8))

        # Dashboard link
        link_row = ctk.CTkFrame(card_api, fg_color="transparent")
        link_row.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(link_row, text="🔗", font=(FONT_FAMILY, 11),
                     text_color=C["accent"]).pack(side="left", padx=(0, 4))
        link_lbl = ctk.CTkLabel(link_row, text=T("sp_open_dashboard"),
                                font=(FONT_FAMILY, 11), text_color=C["accent"],
                                cursor="hand2")
        link_lbl.pack(side="left")
        link_lbl.bind("<Button-1>", lambda _: __import__("webbrowser").open(
            "https://developer.spotify.com/dashboard"))
        link_lbl.bind("<Enter>", lambda _: link_lbl.configure(text_color=C["accent_hover"]))
        link_lbl.bind("<Leave>", lambda _: link_lbl.configure(text_color=C["accent"]))

        # Selectable redirect URI
        ctk.CTkLabel(card_api, text=T("sp_redirect_uri_lbl"), font=(FONT_FAMILY, 10),
                     text_color=C["text_muted"]).pack(anchor="w", padx=14, pady=(0, 2))
        uri_frame = ctk.CTkFrame(card_api, fg_color=C["border"], corner_radius=6)
        uri_frame.pack(fill="x", padx=14, pady=(0, 10))
        uri_inner = ctk.CTkFrame(uri_frame, fg_color=C["bg_input"], corner_radius=5)
        uri_inner.pack(fill="both", expand=True, padx=1, pady=1)
        uri_entry = tk.Entry(uri_inner, state="readonly",
                             readonlybackground=C["bg_input"], bg=C["bg_input"],
                             fg=C["text_primary"], insertbackground=C["text_primary"],
                             font=(FONT_FAMILY, 11), relief="flat", bd=0,
                             selectbackground=C["accent_dim"], selectforeground=C["text_primary"])
        uri_entry.pack(fill="x", padx=8, pady=6)
        uri_entry.configure(state="normal")
        uri_entry.insert(0, "http://127.0.0.1:8888/callback")
        uri_entry.configure(state="readonly")

        ctk.CTkLabel(card_api, text=T("client_id"), font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"]).pack(anchor="w", padx=14, pady=(4, 2))
        self._id_var = ctk.StringVar(value=self._config.get("spotify_client_id", ""))
        ctk.CTkEntry(card_api, textvariable=self._id_var, height=32,
                     fg_color=C["bg_input"], border_color=C["border"],
                     placeholder_text=T("client_id_ph")).pack(fill="x", padx=14)
        ctk.CTkLabel(card_api, text=T("client_secret"), font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"]).pack(anchor="w", padx=14, pady=(8, 2))
        self._secret_var = ctk.StringVar(value=self._config.get("spotify_client_secret", ""))
        ctk.CTkEntry(card_api, textvariable=self._secret_var, height=32, show="*",
                     fg_color=C["bg_input"], border_color=C["border"],
                     placeholder_text=T("client_secret_ph")).pack(fill="x", padx=14, pady=(0, 12))

        # --- Concurrent downloads ---
        ctk.CTkLabel(scroll, text=T("concurrent_dl"),
                     font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_secondary"]).pack(anchor="w", padx=14, pady=(2, 2))
        card_conc = ctk.CTkFrame(scroll, fg_color=C["bg_secondary"], corner_radius=10)
        card_conc.pack(fill="x", pady=(0, 8))
        row_c = ctk.CTkFrame(card_conc, fg_color="transparent")
        row_c.pack(fill="x", padx=14, pady=12)
        row_c.grid_columnconfigure(1, weight=1)
        self._conc_var = ctk.IntVar(value=self._config.get("concurrent_downloads", 2))
        self._conc_lbl = ctk.CTkLabel(row_c, text=str(self._conc_var.get()),
                                       font=(FONT_FAMILY, 12, "bold"),
                                       text_color=C["accent"], width=20)
        self._conc_lbl.grid(row=0, column=2, padx=(8, 0))
        ctk.CTkSlider(row_c, from_=1, to=5, number_of_steps=4,
                      variable=self._conc_var, width=220,
                      progress_color=C["accent"], button_color=C["accent"],
                      command=lambda v: self._conc_lbl.configure(text=str(int(float(v))))
                      ).grid(row=0, column=1, sticky="ew")

        # --- Download options ---
        ctk.CTkLabel(scroll, text=T("sp_sec_options"),
                     font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_secondary"]).pack(anchor="w", padx=14, pady=(2, 2))
        card_opts = ctk.CTkFrame(scroll, fg_color=C["bg_secondary"], corner_radius=10)
        card_opts.pack(fill="x", pady=(0, 8))
        self._sp_toggle(card_opts, "sp_skip_existing", True)
        self._sp_toggle(card_opts, "sp_embed_cover",   True)
        self._sp_toggle(card_opts, "sp_normalize",     False)
        self._sp_toggle(card_opts, "sp_open_folder",   False)

        # --- Filename template ---
        ctk.CTkLabel(scroll, text=T("filename_template_lbl"),
                     font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_secondary"]).pack(anchor="w", padx=14, pady=(2, 2))
        card_fn = ctk.CTkFrame(scroll, fg_color=C["bg_secondary"], corner_radius=10)
        card_fn.pack(fill="x", pady=(0, 8))
        fn_row = ctk.CTkFrame(card_fn, fg_color="transparent")
        fn_row.pack(fill="x", padx=14, pady=10)
        fn_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(fn_row, text=T("filename_template_desc"), font=(FONT_FAMILY, 10),
                     text_color=C["text_secondary"]).grid(row=0, column=0, columnspan=2,
                     sticky="w", pady=(0, 6))
        from config import SP_FILENAME_TEMPLATES
        _sp_tmpl_labels = [T(v) for v in SP_FILENAME_TEMPLATES.values()]
        _sp_tmpl_keys   = list(SP_FILENAME_TEMPLATES.keys())
        cur_sp_tmpl = self._config.get("sp_filename_template", "{artist} - {title}")
        cur_sp_idx  = _sp_tmpl_keys.index(cur_sp_tmpl) if cur_sp_tmpl in _sp_tmpl_keys else 0
        self._sp_tmpl_var = ctk.StringVar(value=_sp_tmpl_labels[cur_sp_idx])
        CustomDropdown(fn_row, variable=self._sp_tmpl_var,
                       values=_sp_tmpl_labels, width=280,
                       accent=C["accent"], accent_dim=C["accent_dim"]
                       ).grid(row=1, column=0, columnspan=2, sticky="w")
        self._sp_tmpl_keys = _sp_tmpl_keys
        self._sp_tmpl_labels = _sp_tmpl_labels

        # --- Buttons ---
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(6, 4))
        ctk.CTkButton(btn_frame, text=T("cancel_btn"), fg_color=C["bg_card"],
                      hover_color=C["bg_secondary"], command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text=T("save_btn"), fg_color=C["accent"],
                      hover_color=C["accent_hover"], command=self._save).pack(side="right")

    def _sp_toggle(self, parent, cfg_key: str, default: bool):
        lbl_key  = f"{cfg_key}_lbl"
        desc_key = f"{cfg_key}_desc"
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(6, 6))
        row.grid_columnconfigure(0, weight=1)

        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(text_col, text=T(lbl_key), font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(text_col, text=T(desc_key), font=(FONT_FAMILY, 10),
                     text_color=C["text_secondary"], anchor="w", wraplength=330).pack(anchor="w")

        var = ctk.BooleanVar(value=self._config.get(cfg_key, default))
        ctk.CTkSwitch(row, text="", variable=var, width=44,
                      progress_color=C["accent"], button_color=C["text_primary"]
                      ).grid(row=0, column=1, padx=(8, 0))
        setattr(self, f"_var_{cfg_key}", var)

    def _save(self):
        self._config["spotify_client_id"]     = self._id_var.get().strip()
        self._config["spotify_client_secret"] = self._secret_var.get().strip()
        self._config["concurrent_downloads"]  = int(self._conc_var.get())
        self._config["sp_skip_existing"]      = self._var_sp_skip_existing.get()
        self._config["sp_embed_cover"]        = self._var_sp_embed_cover.get()
        self._config["sp_normalize"]          = self._var_sp_normalize.get()
        self._config["sp_open_folder"]        = self._var_sp_open_folder.get()
        lbl = self._sp_tmpl_var.get()
        idx = self._sp_tmpl_labels.index(lbl) if lbl in self._sp_tmpl_labels else 0
        self._config["sp_filename_template"]  = self._sp_tmpl_keys[idx]
        self._on_save(self._config)
        self.destroy()

    # ------------------------------------------------------------------ uninstall tab
    def _build_uninstall_tab(self, frame):
        ctk.CTkLabel(frame, text=T("uninstall_section"),
                     font=(FONT_FAMILY, 14, "bold"),
                     text_color=C["error"]).pack(anchor="w", padx=16, pady=(10, 6))

        self._uninstall_row(
            frame,
            icon="🗑",
            title=T("clear_data_btn"),
            desc=T("clear_data_desc"),
            action=self._do_clear_data,
        )
        self._uninstall_row(
            frame,
            icon="⚙",
            title=T("uninstall_ffmpeg_btn"),
            desc=T("uninstall_ffmpeg_desc"),
            action=self._do_uninstall_ffmpeg,
        )
        self._uninstall_row(
            frame,
            icon="✕",
            title=T("uninstall_app_btn"),
            desc=T("uninstall_app_desc"),
            action=self._do_uninstall_app,
            danger=True,
        )

    def _uninstall_row(self, parent, icon: str, title: str, desc: str,
                       action: callable, danger: bool = False):
        row = ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=8)
        row.pack(fill="x", padx=16, pady=4)
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=icon, font=(FONT_FAMILY, 20),
                     text_color=C["error"] if danger else C["text_secondary"],
                     width=36).grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=10)

        ctk.CTkLabel(row, text=title, font=(FONT_FAMILY, 12, "bold"),
                     text_color=C["text_primary"], anchor="w").grid(
            row=0, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        ctk.CTkLabel(row, text=desc, font=(FONT_FAMILY, 10),
                     text_color=C["text_secondary"], anchor="w").grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 8))

        btn_color = C["error"] if danger else C["bg_secondary"]
        btn_hover = "#c0392b" if danger else C["border"]
        ctk.CTkButton(row, text=title, width=180, height=30,
                      font=(FONT_FAMILY, 11), fg_color=btn_color,
                      hover_color=btn_hover, command=action).grid(
            row=0, column=2, rowspan=2, padx=(0, 12))

    # ------------------------------------------------------------------ actions
    def _confirm(self, message: str) -> bool:
        return messagebox.askyesno(T("settings_title"), message,
                                   icon="warning", parent=self)

    def _do_clear_data(self):
        if not self._confirm(T("confirm_clear_data")):
            return
        import shutil
        from config import CONFIG_FILE, LANGUAGE_FILE
        data_dir = CONFIG_FILE.parent
        try:
            shutil.rmtree(data_dir, ignore_errors=True)
        except Exception:
            pass
        self.destroy()

    def _do_uninstall_ffmpeg(self):
        if not self._confirm(T("confirm_uninstall_ffmpeg")):
            return
        import subprocess
        subprocess.Popen(
            ["winget", "uninstall", "yt-dlp.FFmpeg",
             "--accept-source-agreements"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        messagebox.showinfo(T("settings_title"), T("uninstall_started"), parent=self)
        self.destroy()

    def _do_uninstall_app(self):
        if not self._confirm(T("confirm_uninstall_app")):
            return
        uninstaller = self._find_uninstaller()
        if not uninstaller:
            messagebox.showerror(T("settings_title"), T("no_uninstaller"), parent=self)
            return
        import ctypes
        # ShellExecuteW with runas ensures UAC elevation for the uninstaller
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", uninstaller, None, None, 1
        )
        self.destroy()
        if self._on_quit:
            self._on_quit()

    @staticmethod
    def _find_uninstaller() -> Optional[str]:
        import sys, winreg
        app_id = "{8F3A2B1C-4D5E-6F7A-8B9C-0D1E2F3A4B5C}_is1"

        # 1. Registry lookup (Inno Setup registers here)
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (
                rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{app_id}",
                rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{app_id}",
            ):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        raw, _ = winreg.QueryValueEx(k, "UninstallString")
                        # Registry value may be wrapped in quotes
                        path = raw.strip().strip('"')
                        if Path(path).exists():
                            return path
                except Exception:
                    continue

        # 2. Next to the running EXE (works when installed normally)
        exe_dir = Path(sys.executable).parent
        for name in ("unins000.exe", "uninstall.exe"):
            candidate = exe_dir / name
            if candidate.exists():
                return str(candidate)

        # 3. Common install locations
        for base in (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ):
            candidate = base / "DeuDownloader" / "unins000.exe"
            if candidate.exists():
                return str(candidate)

        return None


# ---------------------------------------------------------------------------
# Queue item widget
# ---------------------------------------------------------------------------

class QueueItemWidget(ctk.CTkFrame):
    STATUS_COLORS = {
        DownloadStatus.QUEUED:      C["text_secondary"],
        DownloadStatus.SEARCHING:   C["warning"],
        DownloadStatus.DOWNLOADING: C["accent"],
        DownloadStatus.CONVERTING:  C["warning"],
        DownloadStatus.EMBEDDING:   C["warning"],
        DownloadStatus.DONE:        C["success"],
        DownloadStatus.ERROR:       C["error"],
    }

    def __init__(self, parent, task: DownloadTask, **kwargs):
        super().__init__(parent, fg_color=C["bg_card"], corner_radius=8, **kwargs)
        self._task = task
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="♪", font=(FONT_FAMILY, 18),
                     text_color=C["accent"], width=32).grid(row=0, column=0, rowspan=2,
                     padx=(12,6), pady=10)

        cfg  = load_config()
        tmpl = cfg.get("sp_filename_template", "{artist} - {title}")
        t    = self._task.track
        name = _apply_template(tmpl, artist=t.artist, title=t.title,
                               album=t.album or "", year=t.year or "")
        if len(name) > 60:
            name = name[:57] + "…"
        self._name_lbl = ctk.CTkLabel(self, text=name, font=(FONT_FAMILY, 13, "bold"),
                                       text_color=C["text_primary"], anchor="w")
        self._name_lbl.grid(row=0, column=1, sticky="ew", padx=(0,12), pady=(8,2))

        self._status_lbl = ctk.CTkLabel(self, text=self._task.status.value,
                                         font=(FONT_FAMILY, 11),
                                         text_color=C["text_secondary"], anchor="w")
        self._status_lbl.grid(row=1, column=1, sticky="ew", padx=(0,12), pady=(0,4))

        self._bar = ctk.CTkProgressBar(self, height=6, corner_radius=3,
                                        fg_color=C["bg_secondary"],
                                        progress_color=C["progress_fill"])
        self._bar.set(0)
        self._bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(0,10))

    def update_status(self, status: DownloadStatus, error_msg: str = ""):
        color = self.STATUS_COLORS.get(status, C["text_secondary"])
        label = status.value
        if status == DownloadStatus.ERROR and error_msg:
            short_err = error_msg[:60] + ("…" if len(error_msg) > 60 else "")
            label = f"Error: {short_err}"
        self._status_lbl.configure(text=label, text_color=color)

    def update_progress(self, pct: float):
        self._bar.set(pct)
        if pct >= 1.0:
            self._bar.configure(progress_color=C["success"])


# ---------------------------------------------------------------------------
# Main application window — Spotify
# ---------------------------------------------------------------------------

class DeuDownloaderApp:
    def __init__(self, ffmpeg_available: bool = True, show_back: bool = False):
        self._ffmpeg_ok  = ffmpeg_available
        self._show_back  = show_back
        self._went_back  = False
        self._config     = load_config()
        self._sp_client: Optional[SpotifyClient] = None
        self._manager:   Optional[SpotifyDownloadManager] = None
        self._task_widgets: Dict[str, QueueItemWidget] = {}

        self._root = ctk.CTk()
        self._root.title(T("spotify_win_title"))
        _sp_geo = self._config.get("sp_win_geo", "")
        if not _sp_geo:
            _sp_geo = _center_geometry(self._root, 820, 720)
        self._root.geometry(_sp_geo)
        self._root.minsize(700, 600)
        self._root.configure(fg_color=C["bg_primary"])
        self._root.overrideredirect(True)
        self._root.attributes("-alpha", 0)

        self._drag_x = 0
        self._drag_y = 0
        self._maximized = False
        self._restore_geometry = _sp_geo

        self._build_ui()
        self._root.update()
        self._root.update()
        self._root.attributes("-alpha", 1)
        self._root.bind("<Destroy>", lambda e: self._save_sp_geo() if e.widget is self._root else None)
        self._root.after(10, lambda: _apply_win11_rounded(self._root.winfo_id()))
        self._root.after(10, lambda: _apply_taskbar_button(self._root))
        self._root.after(50, lambda: _bring_to_front(self._root))
        self._init_client()

    # ------------------------------------------------------------------
    def run(self) -> bool:
        self._root.mainloop()
        return self._went_back

    def _save_sp_geo(self):
        geo = self._restore_geometry if self._maximized else self._root.geometry()
        self._config["sp_win_geo"] = geo
        save_config(self._config)

    def _go_back(self):
        self._went_back = True
        self._root.destroy()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._root.grid_rowconfigure(3, weight=1)
        self._root.grid_rowconfigure(4, weight=1)
        self._root.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_input_panel()
        self._build_options_panel()
        self._build_queue_panel()
        self._build_log_panel()

    # --- Custom title bar ---------------------------------------------
    def _build_header(self):
        bar = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"],
                           corner_radius=0, height=46)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)

        bar.bind("<ButtonPress-1>",   self._titlebar_press)
        bar.bind("<B1-Motion>",       self._titlebar_drag)
        bar.bind("<Double-Button-1>", self._toggle_maximize)

        col = 0

        PY = (6, 0)  # top padding for all bar items

        if self._show_back:
            back_btn = ctk.CTkButton(bar, text="←", width=36, height=28,
                          fg_color="transparent", hover_color=C["bg_card"],
                          font=(FONT_FAMILY, 15), text_color=C["text_secondary"],
                          command=self._go_back)
            back_btn.grid(row=0, column=col, padx=(6, 0), pady=PY)
            col += 1

        dot = ctk.CTkLabel(bar, image=spotify_icon(22), text="", cursor="fleur")
        dot.grid(row=0, column=col, padx=(14, 4), pady=PY)
        dot.bind("<ButtonPress-1>",   self._titlebar_press)
        dot.bind("<B1-Motion>",       self._titlebar_drag)
        col += 1

        title_lbl = ctk.CTkLabel(bar, text=APP_NAME, font=(FONT_FAMILY, 14, "bold"),
                                  text_color=C["text_primary"], cursor="fleur")
        title_lbl.grid(row=0, column=col, sticky="w", pady=PY)
        title_lbl.bind("<ButtonPress-1>",   self._titlebar_press)
        title_lbl.bind("<B1-Motion>",       self._titlebar_drag)
        title_lbl.bind("<Double-Button-1>", self._toggle_maximize)
        col += 1

        bar.grid_columnconfigure(col, weight=1)
        col += 1

        ffmpeg_color = C["success"] if self._ffmpeg_ok else C["error"]
        ffmpeg_text  = T("ffmpeg_ok") if self._ffmpeg_ok else T("ffmpeg_fail")
        ctk.CTkLabel(bar, text=ffmpeg_text, font=(FONT_FAMILY, 10),
                     text_color=ffmpeg_color).grid(row=0, column=col, padx=(0, 8), pady=PY)
        col += 1

        ctk.CTkButton(bar, text="⚙", width=36, height=28,
                      fg_color="transparent", hover_color=C["bg_card"],
                      font=(FONT_FAMILY, 14), text_color=C["text_secondary"],
                      command=self._open_settings
                      ).grid(row=0, column=col, padx=(0, 2), pady=PY)
        col += 1

        ctk.CTkButton(bar, text="─", width=36, height=28,
                      fg_color="transparent", hover_color=C["bg_card"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._minimize
                      ).grid(row=0, column=col, padx=0, pady=PY)
        col += 1

        self._max_btn = ctk.CTkButton(bar, text="□", width=36, height=28,
                      fg_color="transparent", hover_color=C["bg_card"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._toggle_maximize
                      )
        self._max_btn.grid(row=0, column=col, padx=0, pady=PY)
        col += 1

        ctk.CTkButton(bar, text="✕", width=36, height=28,
                      fg_color="transparent", hover_color=C["error"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._root.destroy
                      ).grid(row=0, column=col, padx=(0, 6), pady=PY)

    # --- Titlebar drag & window controls ----------------------------
    def _titlebar_press(self, event):
        self._drag_x = event.x_root - self._root.winfo_x()
        self._drag_y = event.y_root - self._root.winfo_y()

    def _titlebar_drag(self, event):
        if self._maximized:
            self._restore_maximize()
            self._drag_x = self._root.winfo_width() // 2
            self._drag_y = 20
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self._root.geometry(f"+{x}+{y}")

    def _minimize(self):
        import ctypes
        child = self._root.winfo_id()
        hwnd  = ctypes.windll.user32.GetAncestor(child, 2) or child
        ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE

    def _toggle_maximize(self, event=None):
        if self._maximized:
            self._restore_maximize()
        else:
            self._restore_geometry = self._root.geometry()
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            self._root.geometry(f"{sw}x{sh}+0+0")
            self._maximized = True
            self._max_btn.configure(text="❐")

    def _restore_maximize(self):
        self._root.geometry(self._restore_geometry)
        self._maximized = False
        self._max_btn.configure(text="□")

    # --- URL input panel ---------------------------------------------
    def _build_input_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(12,6))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text=T("spotify_url"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=0, column=0, sticky="w",
                     padx=16, pady=(10,2))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(0,12))
        inner.grid_columnconfigure(0, weight=1)

        self._url_var = ctk.StringVar()
        self._url_entry = ctk.CTkEntry(
            inner, textvariable=self._url_var, height=38,
            font=(FONT_FAMILY, 13), fg_color=C["bg_input"],
            placeholder_text="Paste a Spotify or YouTube URL…",
            border_color=C["border"],
        )
        self._url_entry.grid(row=0, column=0, sticky="ew", padx=(0,8))
        self._url_entry.bind("<Return>", lambda _: self._start_download())

        ctk.CTkButton(inner, text=T("paste"), width=72, height=38,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      command=self._paste_url).grid(row=0, column=1, padx=(0,8))

        ctk.CTkButton(inner, text=T("clear"), width=66, height=38,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      command=lambda: self._url_var.set("")).grid(row=0, column=2)

    # --- Options panel -----------------------------------------------
    def _build_options_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=2, column=0, sticky="ew", padx=16, pady=6)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(frame, text=T("format"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=0, column=0, padx=(16,8), pady=14)
        saved_fmt = self._config.get("default_format", "MP3 256 kbps")
        if saved_fmt not in AUDIO_FORMATS:
            saved_fmt = "MP3 256 kbps"
        self._format_var = ctk.StringVar(value=saved_fmt)
        self._format_var.trace_add("write", lambda *_: self._save_ui_prefs())
        fmt_keys = list(AUDIO_FORMATS.keys())
        CustomDropdown(frame, variable=self._format_var,
                       values=fmt_keys,
                       width=270,
                       accent=C["accent"], accent_dim=C["accent_dim"],
                       ).grid(row=0, column=1, sticky="w", padx=(0,20), pady=8)

        ctk.CTkLabel(frame, text=T("save_to"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=0, column=2, padx=(0,8))

        self._outdir_var = ctk.StringVar(value=self._config.get("output_dir", ""))
        self._outdir_var.trace_add("write", lambda *_: self._save_ui_prefs())
        self._outdir_entry = ctk.CTkEntry(frame, textvariable=self._outdir_var,
                                           height=34, font=(FONT_FAMILY, 12),
                                           fg_color=C["bg_input"], border_color=C["border"])
        self._outdir_entry.grid(row=0, column=3, sticky="ew", padx=(0,8))

        ctk.CTkButton(frame, text=T("browse"), width=80, height=34,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      command=self._browse_outdir).grid(row=0, column=4, padx=(0,8))

        self._dl_btn = ctk.CTkButton(
            frame, text=T("download"), width=130, height=38,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color=C["accent"], hover_color=C["accent_hover"],
            command=self._start_download,
        )
        self._dl_btn.grid(row=0, column=5, padx=(4,16))

    # --- Queue panel -------------------------------------------------
    def _build_queue_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=6)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(10,4))
        ctk.CTkLabel(hdr, text=T("download_queue"), font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_primary"]).pack(side="left")
        self._queue_count_lbl = ctk.CTkLabel(hdr, text="", font=(FONT_FAMILY, 11),
                                              text_color=C["text_secondary"])
        self._queue_count_lbl.pack(side="left", padx=8)

        ctk.CTkButton(hdr, text=T("clear_done"), width=90, height=26,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      font=(FONT_FAMILY, 11),
                      command=self._clear_done).pack(side="right")

        self._queue_scroll = ctk.CTkScrollableFrame(
            frame, fg_color="transparent",
            scrollbar_button_color=C["bg_card"],
            scrollbar_button_hover_color=C["border"],
        )
        self._queue_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0,8))
        self._queue_scroll.grid_columnconfigure(0, weight=1)

        self._queue_row = 0

    # --- Log panel ---------------------------------------------------
    def _build_log_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=4, column=0, sticky="nsew", padx=16, pady=(6,14))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(8,4))
        ctk.CTkLabel(hdr, text=T("log_panel"), font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_primary"]).pack(side="left")
        ctk.CTkButton(hdr, text=T("clear_log"), width=60, height=24,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      font=(FONT_FAMILY, 11),
                      command=self._clear_log).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            frame, font=("Consolas", 11), fg_color=C["bg_input"],
            text_color=C["text_secondary"], state="disabled",
            border_color=C["border"], border_width=1,
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0,8))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str, color: Optional[str] = None):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _save_ui_prefs(self):
        self._config["default_format"] = self._format_var.get()
        self._config["output_dir"]     = self._outdir_var.get()
        save_config(self._config)

    def _paste_url(self):
        try:
            text = self._root.clipboard_get().strip()
            self._url_var.set(text)
        except Exception:
            pass

    def _browse_outdir(self):
        d = filedialog.askdirectory(title=T("select_outdir"),
                                    initialdir=self._outdir_var.get())
        if d:
            self._outdir_var.set(d)

    def _clear_done(self):
        done_ids = [tid for tid, w in list(self._task_widgets.items())
                    if w._task.status in (DownloadStatus.DONE, DownloadStatus.ERROR)]
        for tid in done_ids:
            w = self._task_widgets.pop(tid)
            w.destroy()
        for row, (_, w) in enumerate(self._task_widgets.items()):
            w.grid(row=row, column=0, sticky="ew", padx=4, pady=4)
        self._queue_row = len(self._task_widgets)
        self._update_queue_count()

    def _update_queue_count(self):
        n = len(self._task_widgets)
        if n:
            self._queue_count_lbl.configure(text=f"({n} item{'s' if n!=1 else ''})")
        else:
            self._queue_count_lbl.configure(text="")

    # ------------------------------------------------------------------
    # Spotify client init
    # ------------------------------------------------------------------

    def _init_client(self):
        cid  = self._config.get("spotify_client_id", "")
        csec = self._config.get("spotify_client_secret", "")
        if cid and csec:
            try:
                self._sp_client = SpotifyClient(cid, csec)
                n_workers = self._config.get("concurrent_downloads", 2)
                self._manager = SpotifyDownloadManager(n_workers, self._ffmpeg_ok)
                self._log(T("spotify_init"))
            except Exception as exc:
                self._log(T("spotify_auth_err").format(exc))
                self._sp_client = None
        else:
            self._log(T("no_credentials"))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self):
        def on_save(new_cfg):
            self._config.update(new_cfg)
            save_config(self._config)
            self._outdir_var.set(self._config["output_dir"])
            self._init_client()
            self._log(T("settings_saved"))
        SettingsDialog(self._root, self._config, on_save, on_quit=self._root.destroy)

    # ------------------------------------------------------------------
    # Download flow
    # ------------------------------------------------------------------

    def _start_download(self):
        url = self._url_var.get().strip()
        if not url:
            messagebox.showwarning(T("mb_no_url_title"), T("mb_no_url_spotify"))
            return

        if not self._sp_client:
            messagebox.showerror(T("mb_api_title"), T("mb_api_msg"))
            return

        out_dir = self._outdir_var.get().strip()
        if not out_dir:
            messagebox.showwarning(T("mb_no_outdir_title"), T("mb_no_outdir"))
            return

        self._dl_btn.configure(state="disabled", text=T("loading"))
        self._url_var.set("")

        threading.Thread(
            target=self._resolve_and_queue,
            args=(url, out_dir),
            daemon=True,
        ).start()

    def _resolve_and_queue(self, url: str, out_dir: str):
        try:
            from downloader import is_youtube_url, YouTubeClient

            if is_youtube_url(url):
                self._root.after(0, lambda: self._log(T("fetching_youtube")))
                yt = YouTubeClient()
                is_playlist = (
                    "playlist?list=" in url or
                    ("/playlist" in url and "watch?v=" not in url)
                )
                if is_playlist:
                    tracks = yt.get_playlist_tracks(url)
                else:
                    tracks = [yt.get_track_info(url)]
            else:
                if not self._sp_client:
                    raise ValueError(T("no_credentials"))
                kind, sp_id = self._sp_client.parse_url(url)
                self._root.after(0, lambda: self._log(T("fetching_spotify").format(kind)))
                if kind == "track":
                    tracks = [self._sp_client.get_track_info(sp_id)]
                elif kind == "playlist":
                    tracks = self._sp_client.get_playlist_tracks(sp_id)
                elif kind == "album":
                    tracks = self._sp_client.get_album_tracks(sp_id)
                else:
                    raise ValueError(f"Unknown type: {kind}")

            fmt = self._format_var.get()
            self._root.after(0, lambda: self._log(T("queued_n_tracks").format(len(tracks), fmt)))
            for track in tracks:
                self._root.after(0, lambda t=track: self._queue_track(t, out_dir, fmt))

        except Exception as exc:
            msg = str(exc)
            self._root.after(0, lambda m=msg: (
                self._log(T("err_resolving").format(m)),
                messagebox.showerror(T("mb_error_title"), m),
            ))
        finally:
            self._root.after(0, lambda: self._dl_btn.configure(
                state="normal", text=T("download")
            ))

    def _queue_track(self, track: TrackInfo, out_dir: str, fmt: str):
        task_id = str(uuid.uuid4())

        task = DownloadTask(
            task_id    = task_id,
            track      = track,
            output_dir = out_dir,
            format_name= fmt,
        )

        def on_progress(t: DownloadTask):
            self._root.after(0, lambda: widget.update_progress(t.progress))

        def on_status(t: DownloadTask):
            self._root.after(0, lambda: (
                widget.update_status(t.status, t.error_msg),
                self._log(_status_log_line(t)),
            ))

        def on_done(t: DownloadTask):
            self._root.after(0, lambda: self._on_track_done(widget, t, out_dir))

        task.on_progress = on_progress
        task.on_status   = on_status
        task.on_done     = on_done

        widget = QueueItemWidget(self._queue_scroll, task)
        widget.grid(row=self._queue_row, column=0, sticky="ew", padx=4, pady=4)
        self._queue_row += 1
        self._task_widgets[task_id] = widget
        self._update_queue_count()

        self._log(T("log_queued").format(track.display_name()))
        self._manager.submit(task)

    def _on_track_done(self, widget: "QueueItemWidget", t: DownloadTask, out_dir: str):
        widget.update_status(t.status, t.error_msg)
        widget.update_progress(t.progress)
        if self._config.get("sp_open_folder", False):
            all_done = all(
                w._task.status in (DownloadStatus.DONE, DownloadStatus.ERROR)
                for w in self._task_widgets.values()
            )
            if all_done:
                import os
                try:
                    os.startfile(out_dir)
                except Exception:
                    pass


def _status_log_line(task: DownloadTask) -> str:
    name = task.track.display_name()
    if task.status == DownloadStatus.DONE:
        return T("log_done").format(name)
    if task.status == DownloadStatus.ERROR:
        return T("log_error").format(name, task.error_msg)
    return f"{task.status.value}: {name}"


def _yt_status_log_line(task: YouTubeTask) -> str:
    name = task.display_name()
    if task.status == DownloadStatus.DONE:
        return T("log_done").format(name)
    if task.status == DownloadStatus.ERROR:
        return T("log_error").format(name, task.error_msg)
    return f"{task.status.value}: {name}"


# ---------------------------------------------------------------------------
# YouTube queue item widget
# ---------------------------------------------------------------------------

class YouTubeQueueItemWidget(ctk.CTkFrame):
    YT_RED = "#FF4444"
    STATUS_COLORS = {
        DownloadStatus.QUEUED:      C["text_secondary"],
        DownloadStatus.DOWNLOADING: "#FF4444",
        DownloadStatus.CONVERTING:  C["warning"],
        DownloadStatus.DONE:        "#FF4444",
        DownloadStatus.ERROR:       C["error"],
    }

    def __init__(self, parent, task: YouTubeTask, **kwargs):
        super().__init__(parent, fg_color=C["bg_card"], corner_radius=8, **kwargs)
        self._task = task
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="▶", font=(FONT_FAMILY, 18),
                     text_color="#FF4444", width=32).grid(row=0, column=0, rowspan=2,
                     padx=(12, 6), pady=10)

        cfg   = load_config()
        tmpl  = cfg.get("yt_filename_template", "{title}")
        raw   = self._task.display_name()
        parts = raw.split(" - ", 1) if " - " in raw else ["", raw]
        name  = _apply_template(tmpl, artist=parts[0].strip(), title=parts[1].strip())
        if len(name) > 60:
            name = name[:57] + "…"
        self._name_lbl = ctk.CTkLabel(self, text=name, font=(FONT_FAMILY, 13, "bold"),
                                       text_color=C["text_primary"], anchor="w")
        self._name_lbl.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(8, 2))

        self._status_lbl = ctk.CTkLabel(self, text=self._task.status.value,
                                         font=(FONT_FAMILY, 11),
                                         text_color=C["text_secondary"], anchor="w")
        self._status_lbl.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 4))

        self._bar = ctk.CTkProgressBar(self, height=6, corner_radius=3,
                                        fg_color=C["bg_secondary"],
                                        progress_color="#FF4444")
        self._bar.set(0)
        self._bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 10))

    def update_status(self, status: DownloadStatus, error_msg: str = ""):
        color = self.STATUS_COLORS.get(status, C["text_secondary"])
        label = status.value
        if status == DownloadStatus.ERROR and error_msg:
            short_err = error_msg[:60] + ("…" if len(error_msg) > 60 else "")
            label = f"Error: {short_err}"
        self._status_lbl.configure(text=label, text_color=color)

    def update_progress(self, pct: float):
        self._bar.set(pct)
        if pct >= 1.0:
            self._bar.configure(progress_color=self.YT_RED)


# ---------------------------------------------------------------------------
# YouTube Settings Dialog
# ---------------------------------------------------------------------------

class YouTubeSettingsDialog(ctk.CTkToplevel):
    YT_RED = "#CC2222"
    YT_RED_HOVER = "#AA1111"

    RATE_LABELS = ["yt_rate_no_limit", "yt_rate_1m", "yt_rate_5m", "yt_rate_10m", "yt_rate_50m"]
    RATE_VALUES = ["", "1M", "5M", "10M", "50M"]

    def __init__(self, parent, config: dict, on_save: callable, on_quit: callable = None):
        super().__init__(parent)
        self.title(T("yt_settings_title"))
        self.geometry("520x560")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.configure(fg_color=C["bg_primary"])
        self._config  = dict(config)
        self._on_save = on_save
        self._on_quit = on_quit
        self._drag_x  = 0
        self._drag_y  = 0
        self.after(10,  lambda: _apply_win11_rounded(self.winfo_id()))
        self._build_titlebar()
        self._build()
        self.after(30,  self._center_on_parent)
        self.after(100, self.grab_set)

    def _center_on_parent(self):
        self.update_idletasks()
        px, py = self.master.winfo_x(), self.master.winfo_y()
        pw, ph = self.master.winfo_width(), self.master.winfo_height()
        w,  h  = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _build_titlebar(self):
        bar = ctk.CTkFrame(self, fg_color=C["bg_secondary"], corner_radius=0, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        bar.bind("<ButtonPress-1>", self._titlebar_press)
        bar.bind("<B1-Motion>",     self._titlebar_drag)

        icon = ctk.CTkLabel(bar, image=youtube_icon(18), text="")
        icon.pack(side="left", padx=(12, 4))
        icon.bind("<ButtonPress-1>", self._titlebar_press)
        icon.bind("<B1-Motion>",     self._titlebar_drag)

        lbl = ctk.CTkLabel(bar, text=T("yt_settings_title"), font=(FONT_FAMILY, 13, "bold"),
                           text_color=C["text_primary"])
        lbl.pack(side="left")
        lbl.bind("<ButtonPress-1>", self._titlebar_press)
        lbl.bind("<B1-Motion>",     self._titlebar_drag)

        ctk.CTkButton(bar, text="✕", width=36, height=28,
                      fg_color="transparent", hover_color=C["error"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self.destroy).pack(side="right", padx=6)

    def _titlebar_press(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _titlebar_drag(self, event):
        self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _build(self):
        tabs = ctk.CTkTabview(self, fg_color=C["bg_secondary"],
                              segmented_button_fg_color=C["bg_card"],
                              segmented_button_selected_color=self.YT_RED,
                              segmented_button_selected_hover_color=self.YT_RED_HOVER,
                              segmented_button_unselected_color=C["bg_card"],
                              segmented_button_unselected_hover_color=C["border"],
                              text_color=C["text_primary"])
        tabs.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        settings_tab  = tabs.add(T("tab_settings"))
        uninstall_tab = tabs.add(T("tab_uninstall"))

        # ---- Settings tab ----
        scroll = ctk.CTkScrollableFrame(settings_tab, fg_color="transparent",
                                        scrollbar_button_color=C["bg_card"],
                                        scrollbar_button_hover_color=C["border"])
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)
        self._build_section_downloads(scroll)
        self._build_section_media(scroll)
        self._build_section_subtitles(scroll)
        self._build_section_network(scroll)

        btn_frame = ctk.CTkFrame(settings_tab, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(8, 4))
        ctk.CTkButton(btn_frame, text=T("cancel_btn"), fg_color=C["bg_card"],
                      hover_color=C["bg_secondary"], command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text=T("save_btn"), fg_color=self.YT_RED,
                      hover_color=self.YT_RED_HOVER, command=self._save).pack(side="right")

        # ---- Uninstall tab ----
        self._build_section_uninstall(uninstall_tab)

    # ---------------------------------------------------------------- section helpers
    def _section_card(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=C["bg_secondary"], corner_radius=10)
        card.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(card, text=title, font=(FONT_FAMILY, 12, "bold"),
                     text_color=C["text_secondary"]).pack(anchor="w", padx=14, pady=(10, 4))
        return card

    def _toggle_row(self, parent, label: str, desc: str, cfg_key: str) -> ctk.CTkSwitch:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(2, 8))
        row.grid_columnconfigure(0, weight=1)

        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(text_col, text=label, font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(text_col, text=desc, font=(FONT_FAMILY, 10),
                     text_color=C["text_secondary"], anchor="w", wraplength=330).pack(anchor="w")

        var = ctk.BooleanVar(value=self._config.get(cfg_key, False))
        sw  = ctk.CTkSwitch(row, text="", variable=var, width=44,
                             progress_color=self.YT_RED,
                             button_color=C["text_primary"])
        sw.grid(row=0, column=1, padx=(8, 0))
        setattr(self, f"_var_{cfg_key}", var)
        return sw

    # ---------------------------------------------------------------- sections
    def _build_section_downloads(self, parent):
        card = self._section_card(parent, T("yt_sec_downloads"))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 8))
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=T("yt_concurrent_lbl"), font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"]).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self._conc_var = ctk.IntVar(value=self._config.get("yt_concurrent", 2))
        self._conc_lbl = ctk.CTkLabel(row, text=str(self._conc_var.get()),
                                       font=(FONT_FAMILY, 12, "bold"),
                                       text_color=self.YT_RED, width=20)
        self._conc_lbl.grid(row=0, column=2, padx=(8, 0))

        def _update_lbl(val):
            self._conc_lbl.configure(text=str(int(float(val))))

        ctk.CTkSlider(row, from_=1, to=5, number_of_steps=4,
                      variable=self._conc_var, width=200,
                      progress_color=self.YT_RED,
                      button_color=self.YT_RED,
                      command=_update_lbl).grid(row=0, column=1, sticky="ew")

        # Filename template
        fn_row = ctk.CTkFrame(card, fg_color="transparent")
        fn_row.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(fn_row, text=T("filename_template_lbl"), font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"]).pack(anchor="w")
        ctk.CTkLabel(fn_row, text=T("filename_template_desc"), font=(FONT_FAMILY, 10),
                     text_color=C["text_secondary"]).pack(anchor="w", pady=(0, 4))
        from config import YT_FILENAME_TEMPLATES
        self._yt_tmpl_labels = [T(v) for v in YT_FILENAME_TEMPLATES.values()]
        self._yt_tmpl_keys   = list(YT_FILENAME_TEMPLATES.keys())
        cur = self._config.get("yt_filename_template", "{title}")
        cur_idx = self._yt_tmpl_keys.index(cur) if cur in self._yt_tmpl_keys else 0
        self._yt_tmpl_var = ctk.StringVar(value=self._yt_tmpl_labels[cur_idx])
        CustomDropdown(fn_row, variable=self._yt_tmpl_var,
                       values=self._yt_tmpl_labels, width=280,
                       accent=self.YT_RED, accent_dim="#3a0a0a").pack(anchor="w")

    def _build_section_media(self, parent):
        card = self._section_card(parent, T("yt_sec_media"))
        self._toggle_row(card, T("yt_embed_thumb_lbl"), T("yt_embed_thumb_desc"), "yt_embed_thumbnail")
        # Default for embed thumbnail is True, fix the var
        self._var_yt_embed_thumbnail.set(self._config.get("yt_embed_thumbnail", True))
        self._toggle_row(card, T("yt_sponsorblock_lbl"), T("yt_sponsorblock_desc"), "yt_sponsorblock")

    def _build_section_subtitles(self, parent):
        card = self._section_card(parent, T("yt_sec_subtitles"))
        sw = self._toggle_row(card, T("yt_subtitles_lbl"), T("yt_subtitles_desc"), "yt_write_subtitles")

        lang_row = ctk.CTkFrame(card, fg_color="transparent")
        lang_row.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(lang_row, text=T("yt_subtitle_langs_lbl"),
                     font=(FONT_FAMILY, 11), text_color=C["text_secondary"]).pack(anchor="w")
        self._subtitle_langs_var = ctk.StringVar(value=self._config.get("yt_subtitle_langs", "en"))
        self._lang_entry = ctk.CTkEntry(lang_row, textvariable=self._subtitle_langs_var,
                                         height=30, font=(FONT_FAMILY, 12),
                                         fg_color=C["bg_input"], border_color=C["border"],
                                         placeholder_text=T("yt_subtitle_langs_ph"))
        self._lang_entry.pack(fill="x", pady=(4, 0))

        # Show/hide lang entry based on switch
        def _toggle_lang(*_):
            state = "normal" if self._var_yt_write_subtitles.get() else "disabled"
            self._lang_entry.configure(state=state)
        self._var_yt_write_subtitles.trace_add("write", _toggle_lang)
        _toggle_lang()

    def _build_section_network(self, parent):
        card = self._section_card(parent, T("yt_sec_network"))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 12))
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=T("yt_rate_limit_lbl"), font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"]).grid(row=0, column=0, sticky="w", padx=(0, 12))

        rate_labels = [T(k) for k in self.RATE_LABELS]
        cur_val = self._config.get("yt_rate_limit", "")
        cur_idx = self.RATE_VALUES.index(cur_val) if cur_val in self.RATE_VALUES else 0
        self._rate_var = ctk.StringVar(value=rate_labels[cur_idx])
        CustomDropdown(row, variable=self._rate_var, values=rate_labels, width=200
                       ).grid(row=0, column=1, sticky="w")

    def _build_section_uninstall(self, parent):
        ctk.CTkLabel(parent, text=T("uninstall_section"),
                     font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["error"]).pack(anchor="w", padx=4, pady=(8, 4))
        self._uninstall_row(parent, "🗑", T("clear_data_btn"),      T("clear_data_desc"),      self._do_clear_data)
        self._uninstall_row(parent, "⚙", T("uninstall_ffmpeg_btn"), T("uninstall_ffmpeg_desc"), self._do_uninstall_ffmpeg)
        self._uninstall_row(parent, "✕", T("uninstall_app_btn"),    T("uninstall_app_desc"),    self._do_uninstall_app, danger=True)

    def _uninstall_row(self, parent, icon, title, desc, action, danger=False):
        row = ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=8)
        row.pack(fill="x", padx=14, pady=4)
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text=icon, font=(FONT_FAMILY, 18),
                     text_color=C["error"] if danger else C["text_secondary"],
                     width=36).grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=8)
        ctk.CTkLabel(row, text=title, font=(FONT_FAMILY, 12, "bold"),
                     text_color=C["text_primary"], anchor="w").grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(6, 0))
        ctk.CTkLabel(row, text=desc, font=(FONT_FAMILY, 10),
                     text_color=C["text_secondary"], anchor="w").grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 6))
        ctk.CTkButton(row, text=title, width=180, height=28, font=(FONT_FAMILY, 11),
                      fg_color=C["error"] if danger else C["bg_secondary"],
                      hover_color="#c0392b" if danger else C["border"],
                      command=action).grid(row=0, column=2, rowspan=2, padx=(0, 10))

    def _confirm(self, msg):
        return messagebox.askyesno(T("yt_settings_title"), msg, icon="warning", parent=self)

    def _do_clear_data(self):
        if not self._confirm(T("confirm_clear_data")):
            return
        import shutil
        from config import CONFIG_FILE
        shutil.rmtree(CONFIG_FILE.parent, ignore_errors=True)
        self.destroy()

    def _do_uninstall_ffmpeg(self):
        if not self._confirm(T("confirm_uninstall_ffmpeg")):
            return
        import subprocess
        subprocess.Popen(["winget", "uninstall", "yt-dlp.FFmpeg", "--accept-source-agreements"],
                         creationflags=subprocess.CREATE_NO_WINDOW)
        messagebox.showinfo(T("yt_settings_title"), T("uninstall_started"), parent=self)
        self.destroy()

    def _do_uninstall_app(self):
        if not self._confirm(T("confirm_uninstall_app")):
            return
        uninstaller = SettingsDialog._find_uninstaller()
        if not uninstaller:
            messagebox.showerror(T("yt_settings_title"), T("no_uninstaller"), parent=self)
            return
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(None, "runas", uninstaller, None, None, 1)
        self.destroy()
        if self._on_quit:
            self._on_quit()

    # ---------------------------------------------------------------- save
    def _save(self):
        self._config["yt_concurrent"]      = int(self._conc_var.get())
        self._config["yt_embed_thumbnail"] = self._var_yt_embed_thumbnail.get()
        self._config["yt_sponsorblock"]    = self._var_yt_sponsorblock.get()
        self._config["yt_write_subtitles"] = self._var_yt_write_subtitles.get()
        self._config["yt_subtitle_langs"]  = self._subtitle_langs_var.get().strip()
        label = self._rate_var.get()
        labels = [T(k) for k in self.RATE_LABELS]
        idx = labels.index(label) if label in labels else 0
        self._config["yt_rate_limit"] = self.RATE_VALUES[idx]
        lbl = self._yt_tmpl_var.get()
        tidx = self._yt_tmpl_labels.index(lbl) if lbl in self._yt_tmpl_labels else 0
        self._config["yt_filename_template"] = self._yt_tmpl_keys[tidx]
        self._on_save(self._config)
        self.destroy()


# ---------------------------------------------------------------------------
# YouTube Downloader App
# ---------------------------------------------------------------------------

class YouTubeDownloaderApp:
    def __init__(self, ffmpeg_available: bool = True, show_back: bool = False):
        self._ffmpeg_ok  = ffmpeg_available
        self._show_back  = show_back
        self._went_back  = False
        self._config     = load_config()
        self._manager    = YouTubeDownloadManager(
            self._config.get("yt_concurrent", 2), ffmpeg_available
        )
        self._task_widgets: Dict[str, YouTubeQueueItemWidget] = {}

        self._root = ctk.CTk()
        self._root.title(T("youtube_win_title"))
        _yt_geo = self._config.get("yt_win_geo", "")
        if not _yt_geo:
            _yt_geo = _center_geometry(self._root, 820, 720)
        self._root.geometry(_yt_geo)
        self._root.minsize(700, 600)
        self._root.configure(fg_color=C["bg_primary"])
        self._root.overrideredirect(True)
        self._root.attributes("-alpha", 0)

        self._drag_x = 0
        self._drag_y = 0
        self._maximized = False
        self._restore_geometry = _yt_geo

        self._build_ui()
        self._root.update()
        self._root.update()
        self._root.attributes("-alpha", 1)
        self._root.bind("<Destroy>", lambda e: self._save_yt_geo() if e.widget is self._root else None)
        self._root.after(10, lambda: _apply_win11_rounded(self._root.winfo_id()))
        self._root.after(10, lambda: _apply_taskbar_button(self._root))
        self._root.after(50, lambda: _bring_to_front(self._root))

    def run(self) -> bool:
        self._root.mainloop()
        return self._went_back

    def _save_yt_geo(self):
        geo = self._restore_geometry if self._maximized else self._root.geometry()
        self._config["yt_win_geo"] = geo
        save_config(self._config)

    def _go_back(self):
        self._went_back = True
        self._root.destroy()

    def _build_ui(self):
        self._root.grid_rowconfigure(3, weight=1)
        self._root.grid_rowconfigure(4, weight=1)
        self._root.grid_columnconfigure(0, weight=1)
        self._build_header()
        self._build_input_panel()
        self._build_options_panel()
        self._build_queue_panel()
        self._build_log_panel()

    def _build_header(self):
        YT_RED = "#FF4444"
        bar = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"],
                           corner_radius=0, height=46)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.bind("<ButtonPress-1>",   self._titlebar_press)
        bar.bind("<B1-Motion>",       self._titlebar_drag)
        bar.bind("<Double-Button-1>", self._toggle_maximize)

        col = 0
        if self._show_back:
            ctk.CTkButton(bar, text="←", width=36, height=28,
                          fg_color="transparent", hover_color=C["bg_card"],
                          font=(FONT_FAMILY, 15), text_color=C["text_secondary"],
                          command=self._go_back).grid(row=0, column=col, padx=(6, 0), pady=(6, 0))
            col += 1

        PY = (6, 0)

        dot = ctk.CTkLabel(bar, image=youtube_icon(22), text="", cursor="fleur")
        dot.grid(row=0, column=col, padx=(14, 4), pady=PY)
        dot.bind("<ButtonPress-1>", self._titlebar_press)
        dot.bind("<B1-Motion>",     self._titlebar_drag)
        col += 1

        title_lbl = ctk.CTkLabel(bar, text=T("youtube_win_title"),
                                  font=(FONT_FAMILY, 14, "bold"),
                                  text_color=C["text_primary"], cursor="fleur")
        title_lbl.grid(row=0, column=col, sticky="w", pady=PY)
        title_lbl.bind("<ButtonPress-1>",   self._titlebar_press)
        title_lbl.bind("<B1-Motion>",       self._titlebar_drag)
        title_lbl.bind("<Double-Button-1>", self._toggle_maximize)
        col += 1

        bar.grid_columnconfigure(col, weight=1)
        col += 1

        ffmpeg_color = C["success"] if self._ffmpeg_ok else C["error"]
        ffmpeg_text  = T("ffmpeg_ok") if self._ffmpeg_ok else T("ffmpeg_fail")
        ctk.CTkLabel(bar, text=ffmpeg_text, font=(FONT_FAMILY, 10),
                     text_color=ffmpeg_color).grid(row=0, column=col, padx=(0, 8), pady=PY)
        col += 1

        ctk.CTkButton(bar, text="⚙", width=36, height=28,
                      fg_color="transparent", hover_color=C["bg_card"],
                      font=(FONT_FAMILY, 14), text_color=C["text_secondary"],
                      command=self._open_settings).grid(row=0, column=col, padx=(0, 2), pady=PY)
        col += 1

        ctk.CTkButton(bar, text="─", width=36, height=28,
                      fg_color="transparent", hover_color=C["bg_card"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._minimize).grid(row=0, column=col, padx=0, pady=PY)
        col += 1

        self._max_btn = ctk.CTkButton(bar, text="□", width=36, height=28,
                      fg_color="transparent", hover_color=C["bg_card"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._toggle_maximize)
        self._max_btn.grid(row=0, column=col, padx=0, pady=PY)
        col += 1

        ctk.CTkButton(bar, text="✕", width=36, height=28,
                      fg_color="transparent", hover_color=C["error"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._root.destroy).grid(row=0, column=col, padx=(0, 6), pady=PY)

    def _open_settings(self):
        def on_save(cfg):
            self._config.update(cfg)
            save_config(self._config)
            # Recreate manager if concurrent setting changed
            self._manager = YouTubeDownloadManager(
                self._config.get("yt_concurrent", 2), self._ffmpeg_ok
            )
        YouTubeSettingsDialog(self._root, self._config, on_save,
                              on_quit=self._root.destroy)

    def _titlebar_press(self, event):
        self._drag_x = event.x_root - self._root.winfo_x()
        self._drag_y = event.y_root - self._root.winfo_y()

    def _titlebar_drag(self, event):
        if self._maximized:
            self._restore_maximize()
            self._drag_x = self._root.winfo_width() // 2
            self._drag_y = 20
        self._root.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _minimize(self):
        import ctypes
        child = self._root.winfo_id()
        hwnd  = ctypes.windll.user32.GetAncestor(child, 2) or child
        ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE

    def _toggle_maximize(self, event=None):
        if self._maximized:
            self._restore_maximize()
        else:
            self._restore_geometry = self._root.geometry()
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            self._root.geometry(f"{sw}x{sh}+0+0")
            self._maximized = True
            self._max_btn.configure(text="❐")

    def _restore_maximize(self):
        self._root.geometry(self._restore_geometry)
        self._maximized = False
        self._max_btn.configure(text="□")

    def _build_input_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(12, 6))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text=T("youtube_url"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=0, column=0, sticky="w",
                     padx=16, pady=(10, 2))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        inner.grid_columnconfigure(0, weight=1)

        self._url_var = ctk.StringVar()
        self._url_entry = ctk.CTkEntry(
            inner, textvariable=self._url_var, height=38,
            font=(FONT_FAMILY, 13), fg_color=C["bg_input"],
            placeholder_text="Paste a YouTube video or playlist URL…",
            border_color=C["border"],
        )
        self._url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._url_entry.bind("<Return>", lambda _: self._start_download())

        ctk.CTkButton(inner, text=T("paste"), width=72, height=38,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      command=self._paste_url).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(inner, text=T("clear"), width=66, height=38,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      command=lambda: self._url_var.set("")).grid(row=0, column=2)

    def _build_options_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=2, column=0, sticky="ew", padx=16, pady=6)
        frame.grid_columnconfigure(3, weight=1)

        # --- Row 0: Media type toggle + format dropdown ---
        ctk.CTkLabel(frame, text=T("type"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=0, column=0, padx=(16, 8), pady=(12, 4))

        saved_media = self._config.get("yt_media_type", "Audio")

        toggle_frame = ctk.CTkFrame(frame, fg_color=C["bg_card"], corner_radius=8)
        toggle_frame.grid(row=0, column=1, sticky="w", padx=(0, 16), pady=(12, 4))

        self._audio_btn = ctk.CTkButton(
            toggle_frame, text=T("audio_btn"), width=90, height=28,
            font=(FONT_FAMILY, 12), corner_radius=6,
            fg_color="transparent", hover_color=C["bg_secondary"],
            text_color=C["text_secondary"], command=lambda: self._set_media_type("Audio"),
        )
        self._audio_btn.pack(side="left", padx=3, pady=3)

        self._video_btn = ctk.CTkButton(
            toggle_frame, text=T("video_btn"), width=90, height=28,
            font=(FONT_FAMILY, 12), corner_radius=6,
            fg_color="transparent", hover_color=C["bg_secondary"],
            text_color=C["text_secondary"], command=lambda: self._set_media_type("Video"),
        )
        self._video_btn.pack(side="left", padx=(0, 3), pady=3)

        ctk.CTkLabel(frame, text=T("format"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=0, column=2, padx=(0, 8), pady=(12, 4))

        # Restore last format for the saved media type
        if saved_media == "Video":
            fmt_values = list(VIDEO_FORMATS.keys())
            saved_fmt  = self._config.get("yt_format_video", "MP4 1080p")
            if saved_fmt not in VIDEO_FORMATS:
                saved_fmt = "MP4 1080p"
        else:
            fmt_values = list(AUDIO_FORMATS.keys())
            saved_fmt  = self._config.get("yt_format_audio", "MP3 256 kbps")
            if saved_fmt not in AUDIO_FORMATS:
                saved_fmt = "MP3 256 kbps"

        self._format_var = ctk.StringVar(value=saved_fmt)
        self._format_var.trace_add("write", lambda *_: self._save_ui_prefs())
        self._format_dropdown = CustomDropdown(frame, variable=self._format_var,
                                               values=fmt_values, width=220,
                                               accent="#CC2222", accent_dim="#3a0a0a")
        self._format_dropdown.grid(row=0, column=3, sticky="w", padx=(0, 16), pady=(12, 4))

        # Apply saved media type appearance
        if saved_media == "Video":
            self._video_btn.configure(fg_color="#CC2222", text_color="white")
        else:
            self._audio_btn.configure(fg_color="#CC2222", text_color="white")

        # --- Row 1: Save to + Browse + Download ---
        ctk.CTkLabel(frame, text=T("save_to"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=1, column=0, padx=(16, 8), pady=(4, 12))

        self._outdir_var = ctk.StringVar(value=self._config.get("output_dir", ""))
        self._outdir_var.trace_add("write", lambda *_: self._save_ui_prefs())
        ctk.CTkEntry(frame, textvariable=self._outdir_var,
                     height=34, font=(FONT_FAMILY, 12),
                     fg_color=C["bg_input"], border_color=C["border"]
                     ).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=(4, 12))

        ctk.CTkButton(frame, text=T("browse"), width=80, height=34,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      command=self._browse_outdir).grid(row=1, column=3, sticky="w", padx=(0, 8), pady=(4, 12))

        self._dl_btn = ctk.CTkButton(
            frame, text=T("download"), width=130, height=38,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color="#CC2222", hover_color="#AA1111",
            command=self._start_download,
        )
        self._dl_btn.grid(row=0, column=4, rowspan=2, padx=(4, 16))

        # Store the saved media type (needed by _set_media_type)
        self._media_type = ctk.StringVar(value=saved_media)

    def _set_media_type(self, kind: str):
        self._media_type.set(kind)
        if kind == "Audio":
            self._audio_btn.configure(fg_color="#CC2222", text_color="white")
            self._video_btn.configure(fg_color="transparent", text_color=C["text_secondary"])
            self._format_dropdown._values = list(AUDIO_FORMATS.keys())
            saved = self._config.get("yt_format_audio", "MP3 256 kbps")
            if saved not in AUDIO_FORMATS:
                saved = "MP3 256 kbps"
            self._format_var.set(saved)
        else:
            self._video_btn.configure(fg_color="#CC2222", text_color="white")
            self._audio_btn.configure(fg_color="transparent", text_color=C["text_secondary"])
            self._format_dropdown._values = list(VIDEO_FORMATS.keys())
            saved = self._config.get("yt_format_video", "MP4 1080p")
            if saved not in VIDEO_FORMATS:
                saved = "MP4 1080p"
            self._format_var.set(saved)
        self._config["yt_media_type"] = kind
        save_config(self._config)

    def _build_queue_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=6)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(hdr, text=T("download_queue"), font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_primary"]).pack(side="left")
        self._queue_count_lbl = ctk.CTkLabel(hdr, text="", font=(FONT_FAMILY, 11),
                                              text_color=C["text_secondary"])
        self._queue_count_lbl.pack(side="left", padx=8)
        ctk.CTkButton(hdr, text=T("clear_done"), width=90, height=26,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      font=(FONT_FAMILY, 11),
                      command=self._clear_done).pack(side="right")

        self._queue_scroll = ctk.CTkScrollableFrame(
            frame, fg_color="transparent",
            scrollbar_button_color=C["bg_card"],
            scrollbar_button_hover_color=C["border"],
        )
        self._queue_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._queue_scroll.grid_columnconfigure(0, weight=1)
        self._queue_row = 0

    def _build_log_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=4, column=0, sticky="nsew", padx=16, pady=(6, 14))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        ctk.CTkLabel(hdr, text=T("log_panel"), font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_primary"]).pack(side="left")
        ctk.CTkButton(hdr, text=T("clear_log"), width=60, height=24,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      font=(FONT_FAMILY, 11),
                      command=self._clear_log).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            frame, font=("Consolas", 11), fg_color=C["bg_input"],
            text_color=C["text_secondary"], state="disabled",
            border_color=C["border"], border_width=1,
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{ts}] {msg}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _save_ui_prefs(self):
        fmt   = self._format_var.get()
        media = self._media_type.get() if hasattr(self, "_media_type") else "Audio"
        if media == "Audio":
            self._config["yt_format_audio"] = fmt
        else:
            self._config["yt_format_video"] = fmt
        self._config["yt_media_type"] = media
        self._config["output_dir"]    = self._outdir_var.get()
        save_config(self._config)

    def _paste_url(self):
        try:
            self._url_var.set(self._root.clipboard_get().strip())
        except Exception:
            pass

    def _browse_outdir(self):
        d = filedialog.askdirectory(title=T("select_outdir"),
                                    initialdir=self._outdir_var.get())
        if d:
            self._outdir_var.set(d)

    def _clear_done(self):
        done_ids = [tid for tid, w in list(self._task_widgets.items())
                    if w._task.status in (DownloadStatus.DONE, DownloadStatus.ERROR)]
        for tid in done_ids:
            self._task_widgets.pop(tid).destroy()
        for row, (_, w) in enumerate(self._task_widgets.items()):
            w.grid(row=row, column=0, sticky="ew", padx=4, pady=4)
        self._queue_row = len(self._task_widgets)
        self._update_queue_count()

    def _update_queue_count(self):
        n = len(self._task_widgets)
        self._queue_count_lbl.configure(
            text=f"({n} item{'s' if n != 1 else ''})" if n else ""
        )

    def _start_download(self):
        url = self._url_var.get().strip()
        if not url:
            messagebox.showwarning(T("mb_no_url_title"), T("mb_no_url_youtube"))
            return
        out_dir = self._outdir_var.get().strip()
        if not out_dir:
            messagebox.showwarning(T("mb_no_outdir_title"), T("mb_no_outdir"))
            return

        self._dl_btn.configure(state="disabled", text=T("loading"))
        self._url_var.set("")
        threading.Thread(target=self._resolve_and_queue, args=(url, out_dir), daemon=True).start()

    def _resolve_and_queue(self, url: str, out_dir: str):
        try:
            self._root.after(0, lambda: self._log(T("fetching_youtube")))
            entries = extract_youtube_entries(url)
            fmt = self._format_var.get()
            self._root.after(0, lambda: self._log(T("queued_n_videos").format(len(entries), fmt)))
            for entry in entries:
                self._root.after(0, lambda e=entry: self._queue_entry(e, out_dir, fmt))
        except Exception as exc:
            msg = str(exc)
            self._root.after(0, lambda m=msg: (
                self._log(T("err_resolving").format(m)),
                messagebox.showerror(T("mb_error_title"), m),
            ))
        finally:
            self._root.after(0, lambda: self._dl_btn.configure(
                state="normal", text=T("download")
            ))

    def _queue_entry(self, entry: dict, out_dir: str, fmt: str):
        task_id = str(uuid.uuid4())
        task = YouTubeTask(
            task_id    = task_id,
            url        = entry["url"],
            title      = entry["title"],
            output_dir = out_dir,
            format_name= fmt,
        )

        def on_progress(t: YouTubeTask):
            self._root.after(0, lambda: widget.update_progress(t.progress))

        def on_status(t: YouTubeTask):
            self._root.after(0, lambda: (
                widget.update_status(t.status, t.error_msg),
                self._log(_yt_status_log_line(t)),
            ))

        def on_done(t: YouTubeTask):
            self._root.after(0, lambda: (
                widget.update_status(t.status, t.error_msg),
                widget.update_progress(t.progress),
            ))

        task.on_progress = on_progress
        task.on_status   = on_status
        task.on_done     = on_done

        widget = YouTubeQueueItemWidget(self._queue_scroll, task)
        widget.grid(row=self._queue_row, column=0, sticky="ew", padx=4, pady=4)
        self._queue_row += 1
        self._task_widgets[task_id] = widget
        self._update_queue_count()

        self._log(T("log_queued").format(task.display_name()))
        self._manager.submit(task)


# ---------------------------------------------------------------------------
# TikTok queue item widget
# ---------------------------------------------------------------------------

class TikTokQueueItemWidget(ctk.CTkFrame):
    TT_PINK = "#EE1D52"
    STATUS_COLORS = {
        DownloadStatus.QUEUED:      C["text_secondary"],
        DownloadStatus.DOWNLOADING: "#EE1D52",
        DownloadStatus.CONVERTING:  C["warning"],
        DownloadStatus.DONE:        "#EE1D52",
        DownloadStatus.ERROR:       C["error"],
    }

    def __init__(self, parent, task: TikTokTask, **kwargs):
        super().__init__(parent, fg_color=C["bg_card"], corner_radius=8, **kwargs)
        self._task = task
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="♪", font=(FONT_FAMILY, 18),
                     text_color=self.TT_PINK, width=32).grid(row=0, column=0, rowspan=2,
                     padx=(12, 6), pady=10)

        cfg   = load_config()
        tmpl  = cfg.get("tt_filename_template", "{title}")
        raw   = self._task.display_name()
        parts = raw.split(" - ", 1) if " - " in raw else ["", raw]
        name  = _apply_template(tmpl, artist=parts[0].strip(), title=parts[1].strip())
        if len(name) > 60:
            name = name[:57] + "…"
        self._name_lbl = ctk.CTkLabel(self, text=name, font=(FONT_FAMILY, 13, "bold"),
                                       text_color=C["text_primary"], anchor="w")
        self._name_lbl.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(8, 2))

        self._status_lbl = ctk.CTkLabel(self, text=self._task.status.value,
                                         font=(FONT_FAMILY, 11),
                                         text_color=C["text_secondary"], anchor="w")
        self._status_lbl.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 4))

        self._bar = ctk.CTkProgressBar(self, height=6, corner_radius=3,
                                        fg_color=C["bg_secondary"],
                                        progress_color=self.TT_PINK)
        self._bar.set(0)
        self._bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 10))

    def update_status(self, status: DownloadStatus, error_msg: str = ""):
        color = self.STATUS_COLORS.get(status, C["text_secondary"])
        label = status.value
        if status == DownloadStatus.ERROR and error_msg:
            short_err = error_msg[:60] + ("…" if len(error_msg) > 60 else "")
            label = f"Error: {short_err}"
        self._status_lbl.configure(text=label, text_color=color)

    def update_progress(self, pct: float):
        self._bar.set(pct)
        if pct >= 1.0:
            self._bar.configure(progress_color=self.TT_PINK)


def _tt_status_log_line(task: TikTokTask) -> str:
    name = task.display_name()
    if task.status == DownloadStatus.DONE:
        return T("log_done").format(name)
    if task.status == DownloadStatus.ERROR:
        return T("log_error").format(name, task.error_msg)
    return f"{task.status.value}: {name}"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# TikTok Settings Dialog
# ---------------------------------------------------------------------------

class TikTokSettingsDialog(ctk.CTkToplevel):
    TT_PINK     = "#EE1D52"
    TT_PINK_HOV = "#C71542"

    RATE_LABELS = ["yt_rate_no_limit", "yt_rate_1m", "yt_rate_5m", "yt_rate_10m", "yt_rate_50m"]
    RATE_VALUES = ["", "1M", "5M", "10M", "50M"]

    def __init__(self, parent, config: dict, on_save: callable, on_quit: callable = None):
        super().__init__(parent)
        self.title(T("tt_settings_title"))
        self.geometry("520x480")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.configure(fg_color=C["bg_primary"])
        self._config  = dict(config)
        self._on_save = on_save
        self._on_quit = on_quit
        self._drag_x  = 0
        self._drag_y  = 0
        self.after(10,  lambda: _apply_win11_rounded(self.winfo_id()))
        self._build_titlebar()
        self._build()
        self.after(30,  self._center_on_parent)
        self.after(100, self.grab_set)

    def _center_on_parent(self):
        self.update_idletasks()
        px, py = self.master.winfo_x(), self.master.winfo_y()
        pw, ph = self.master.winfo_width(), self.master.winfo_height()
        w,  h  = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _build_titlebar(self):
        bar = ctk.CTkFrame(self, fg_color=C["bg_secondary"], corner_radius=0, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        bar.bind("<ButtonPress-1>", self._titlebar_press)
        bar.bind("<B1-Motion>",     self._titlebar_drag)

        icon = ctk.CTkLabel(bar, image=tiktok_icon(18), text="")
        icon.pack(side="left", padx=(12, 4))
        icon.bind("<ButtonPress-1>", self._titlebar_press)
        icon.bind("<B1-Motion>",     self._titlebar_drag)

        lbl = ctk.CTkLabel(bar, text=T("tt_settings_title"), font=(FONT_FAMILY, 13, "bold"),
                           text_color=C["text_primary"])
        lbl.pack(side="left")
        lbl.bind("<ButtonPress-1>", self._titlebar_press)
        lbl.bind("<B1-Motion>",     self._titlebar_drag)

        ctk.CTkButton(bar, text="✕", width=36, height=28,
                      fg_color="transparent", hover_color=C["error"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self.destroy).pack(side="right", padx=6)

    def _titlebar_press(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _titlebar_drag(self, event):
        self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _build(self):
        tabs = ctk.CTkTabview(self, fg_color=C["bg_secondary"],
                              segmented_button_fg_color=C["bg_card"],
                              segmented_button_selected_color=self.TT_PINK,
                              segmented_button_selected_hover_color=self.TT_PINK_HOV,
                              segmented_button_unselected_color=C["bg_card"],
                              segmented_button_unselected_hover_color=C["border"],
                              text_color=C["text_primary"])
        tabs.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        settings_tab  = tabs.add(T("tab_settings"))
        uninstall_tab = tabs.add(T("tab_uninstall"))

        scroll = ctk.CTkScrollableFrame(settings_tab, fg_color="transparent",
                                        scrollbar_button_color=C["bg_card"],
                                        scrollbar_button_hover_color=C["border"])
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)
        self._build_section_downloads(scroll)
        self._build_section_media(scroll)
        self._build_section_network(scroll)

        btn_frame = ctk.CTkFrame(settings_tab, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(8, 4))
        ctk.CTkButton(btn_frame, text=T("cancel_btn"), fg_color=C["bg_card"],
                      hover_color=C["bg_secondary"], command=self.destroy).pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text=T("save_btn"), fg_color=self.TT_PINK,
                      hover_color=self.TT_PINK_HOV, command=self._save).pack(side="right")

        self._build_section_uninstall(uninstall_tab)

    def _section_card(self, parent, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=C["bg_secondary"], corner_radius=10)
        card.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(card, text=title, font=(FONT_FAMILY, 12, "bold"),
                     text_color=C["text_secondary"]).pack(anchor="w", padx=14, pady=(10, 4))
        return card

    def _toggle_row(self, parent, label: str, desc: str, cfg_key: str) -> ctk.CTkSwitch:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(2, 8))
        row.grid_columnconfigure(0, weight=1)

        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(text_col, text=label, font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(text_col, text=desc, font=(FONT_FAMILY, 10),
                     text_color=C["text_secondary"], anchor="w", wraplength=330).pack(anchor="w")

        var = ctk.BooleanVar(value=self._config.get(cfg_key, False))
        sw  = ctk.CTkSwitch(row, text="", variable=var, width=44,
                             progress_color=self.TT_PINK,
                             button_color=C["text_primary"])
        sw.grid(row=0, column=1, padx=(8, 0))
        setattr(self, f"_var_{cfg_key}", var)
        return sw

    def _build_section_downloads(self, parent):
        card = self._section_card(parent, T("tt_sec_downloads"))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 12))
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=T("tt_concurrent_lbl"), font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"]).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self._conc_var = ctk.IntVar(value=self._config.get("tt_concurrent", 2))
        self._conc_lbl = ctk.CTkLabel(row, text=str(self._conc_var.get()),
                                       font=(FONT_FAMILY, 12, "bold"),
                                       text_color=self.TT_PINK, width=20)
        self._conc_lbl.grid(row=0, column=2, padx=(8, 0))

        def _update_lbl(val):
            self._conc_lbl.configure(text=str(int(float(val))))

        ctk.CTkSlider(row, from_=1, to=5, number_of_steps=4,
                      variable=self._conc_var, width=200,
                      progress_color=self.TT_PINK,
                      button_color=self.TT_PINK,
                      command=_update_lbl).grid(row=0, column=1, sticky="ew")

        # Filename template
        fn_row = ctk.CTkFrame(card, fg_color="transparent")
        fn_row.pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(fn_row, text=T("filename_template_lbl"), font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"]).pack(anchor="w")
        ctk.CTkLabel(fn_row, text=T("filename_template_desc"), font=(FONT_FAMILY, 10),
                     text_color=C["text_secondary"]).pack(anchor="w", pady=(0, 4))
        from config import TT_FILENAME_TEMPLATES
        self._tt_tmpl_labels = [T(v) for v in TT_FILENAME_TEMPLATES.values()]
        self._tt_tmpl_keys   = list(TT_FILENAME_TEMPLATES.keys())
        cur = self._config.get("tt_filename_template", "{title}")
        cur_idx = self._tt_tmpl_keys.index(cur) if cur in self._tt_tmpl_keys else 0
        self._tt_tmpl_var = ctk.StringVar(value=self._tt_tmpl_labels[cur_idx])
        CustomDropdown(fn_row, variable=self._tt_tmpl_var,
                       values=self._tt_tmpl_labels, width=280,
                       accent=self.TT_PINK, accent_dim="#3d0617").pack(anchor="w")

    def _build_section_media(self, parent):
        card = self._section_card(parent, T("tt_sec_media"))
        sw = self._toggle_row(card, T("tt_embed_thumb_lbl"), T("tt_embed_thumb_desc"), "tt_embed_thumbnail")
        self._var_tt_embed_thumbnail.set(self._config.get("tt_embed_thumbnail", True))

    def _build_section_network(self, parent):
        card = self._section_card(parent, T("tt_sec_network"))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 12))
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=T("tt_rate_limit_lbl"), font=(FONT_FAMILY, 12),
                     text_color=C["text_primary"]).grid(row=0, column=0, sticky="w", padx=(0, 12))

        rate_labels = [T(k) for k in self.RATE_LABELS]
        cur_val = self._config.get("tt_rate_limit", "")
        cur_idx = self.RATE_VALUES.index(cur_val) if cur_val in self.RATE_VALUES else 0
        self._rate_var = ctk.StringVar(value=rate_labels[cur_idx])
        CustomDropdown(row, variable=self._rate_var, values=rate_labels, width=200,
                       accent=self.TT_PINK, accent_dim="#3d0617"
                       ).grid(row=0, column=1, sticky="w")

    def _build_section_uninstall(self, parent):
        ctk.CTkLabel(parent, text=T("uninstall_section"),
                     font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["error"]).pack(anchor="w", padx=4, pady=(8, 4))
        self._uninstall_row(parent, "🗑", T("clear_data_btn"),      T("clear_data_desc"),      self._do_clear_data)
        self._uninstall_row(parent, "⚙", T("uninstall_ffmpeg_btn"), T("uninstall_ffmpeg_desc"), self._do_uninstall_ffmpeg)
        self._uninstall_row(parent, "✕", T("uninstall_app_btn"),    T("uninstall_app_desc"),    self._do_uninstall_app, danger=True)

    def _uninstall_row(self, parent, icon, title, desc, action, danger=False):
        row = ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=8)
        row.pack(fill="x", padx=14, pady=4)
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text=icon, font=(FONT_FAMILY, 18),
                     text_color=C["error"] if danger else C["text_secondary"],
                     width=36).grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=8)
        ctk.CTkLabel(row, text=title, font=(FONT_FAMILY, 12, "bold"),
                     text_color=C["text_primary"], anchor="w").grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(6, 0))
        ctk.CTkLabel(row, text=desc, font=(FONT_FAMILY, 10),
                     text_color=C["text_secondary"], anchor="w").grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 6))
        ctk.CTkButton(row, text=title, width=180, height=28, font=(FONT_FAMILY, 11),
                      fg_color=C["error"] if danger else C["bg_secondary"],
                      hover_color="#c0392b" if danger else C["border"],
                      command=action).grid(row=0, column=2, rowspan=2, padx=(0, 10))

    def _confirm(self, msg):
        return messagebox.askyesno(T("tt_settings_title"), msg, icon="warning", parent=self)

    def _do_clear_data(self):
        if not self._confirm(T("confirm_clear_data")):
            return
        import shutil
        from config import CONFIG_FILE
        shutil.rmtree(CONFIG_FILE.parent, ignore_errors=True)
        self.destroy()

    def _do_uninstall_ffmpeg(self):
        if not self._confirm(T("confirm_uninstall_ffmpeg")):
            return
        import subprocess
        subprocess.Popen(["winget", "uninstall", "yt-dlp.FFmpeg", "--accept-source-agreements"],
                         creationflags=subprocess.CREATE_NO_WINDOW)
        messagebox.showinfo(T("tt_settings_title"), T("uninstall_started"), parent=self)
        self.destroy()

    def _do_uninstall_app(self):
        if not self._confirm(T("confirm_uninstall_app")):
            return
        uninstaller = SettingsDialog._find_uninstaller()
        if not uninstaller:
            messagebox.showerror(T("tt_settings_title"), T("no_uninstaller"), parent=self)
            return
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(None, "runas", uninstaller, None, None, 1)
        self.destroy()
        if self._on_quit:
            self._on_quit()

    def _save(self):
        self._config["tt_concurrent"]      = int(self._conc_var.get())
        self._config["tt_embed_thumbnail"] = self._var_tt_embed_thumbnail.get()
        label = self._rate_var.get()
        labels = [T(k) for k in self.RATE_LABELS]
        idx = labels.index(label) if label in labels else 0
        self._config["tt_rate_limit"] = self.RATE_VALUES[idx]
        lbl = self._tt_tmpl_var.get()
        tidx = self._tt_tmpl_labels.index(lbl) if lbl in self._tt_tmpl_labels else 0
        self._config["tt_filename_template"] = self._tt_tmpl_keys[tidx]
        self._on_save(self._config)
        self.destroy()


# ---------------------------------------------------------------------------
# TikTok Downloader App
# ---------------------------------------------------------------------------

class TikTokDownloaderApp:
    TT_PINK      = "#EE1D52"
    TT_PINK_HOV  = "#C71542"

    def __init__(self, ffmpeg_available: bool = True, show_back: bool = False):
        self._ffmpeg_ok  = ffmpeg_available
        self._show_back  = show_back
        self._went_back  = False
        self._config     = load_config()
        self._manager    = TikTokDownloadManager(
            self._config.get("tt_concurrent", 2), ffmpeg_available
        )
        self._task_widgets: Dict[str, TikTokQueueItemWidget] = {}

        self._root = ctk.CTk()
        self._root.title(T("tiktok_win_title"))
        _tt_geo = self._config.get("tt_win_geo", "")
        if not _tt_geo:
            _tt_geo = _center_geometry(self._root, 820, 720)
        self._root.geometry(_tt_geo)
        self._root.minsize(700, 600)
        self._root.configure(fg_color=C["bg_primary"])
        self._root.overrideredirect(True)
        self._root.attributes("-alpha", 0)

        self._drag_x = 0
        self._drag_y = 0
        self._maximized = False
        self._restore_geometry = _tt_geo

        self._build_ui()
        self._root.update()
        self._root.update()
        self._root.attributes("-alpha", 1)
        self._root.bind("<Destroy>", lambda e: self._save_geo() if e.widget is self._root else None)
        self._root.after(10, lambda: _apply_win11_rounded(self._root.winfo_id()))
        self._root.after(10, lambda: _apply_taskbar_button(self._root))
        self._root.after(50, lambda: _bring_to_front(self._root))

    def run(self) -> bool:
        self._root.mainloop()
        return self._went_back

    def _save_geo(self):
        geo = self._restore_geometry if self._maximized else self._root.geometry()
        self._config["tt_win_geo"] = geo
        save_config(self._config)

    def _go_back(self):
        self._went_back = True
        self._root.destroy()

    def _build_ui(self):
        self._root.grid_rowconfigure(3, weight=1)
        self._root.grid_rowconfigure(4, weight=1)
        self._root.grid_columnconfigure(0, weight=1)
        self._build_header()
        self._build_input_panel()
        self._build_options_panel()
        self._build_queue_panel()
        self._build_log_panel()

    def _build_header(self):
        bar = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"],
                           corner_radius=0, height=46)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.bind("<ButtonPress-1>",   self._titlebar_press)
        bar.bind("<B1-Motion>",       self._titlebar_drag)
        bar.bind("<Double-Button-1>", self._toggle_maximize)

        col = 0
        if self._show_back:
            ctk.CTkButton(bar, text="←", width=36, height=28,
                          fg_color="transparent", hover_color=C["bg_card"],
                          font=(FONT_FAMILY, 15), text_color=C["text_secondary"],
                          command=self._go_back).grid(row=0, column=col, padx=(6, 0), pady=(6, 0))
            col += 1

        PY = (6, 0)

        dot = ctk.CTkLabel(bar, image=tiktok_icon(22), text="", cursor="fleur")
        dot.grid(row=0, column=col, padx=(14, 4), pady=PY)
        dot.bind("<ButtonPress-1>", self._titlebar_press)
        dot.bind("<B1-Motion>",     self._titlebar_drag)
        col += 1

        title_lbl = ctk.CTkLabel(bar, text=T("tiktok_win_title"),
                                  font=(FONT_FAMILY, 14, "bold"),
                                  text_color=C["text_primary"], cursor="fleur")
        title_lbl.grid(row=0, column=col, sticky="w", pady=PY)
        title_lbl.bind("<ButtonPress-1>",   self._titlebar_press)
        title_lbl.bind("<B1-Motion>",       self._titlebar_drag)
        title_lbl.bind("<Double-Button-1>", self._toggle_maximize)
        col += 1

        bar.grid_columnconfigure(col, weight=1)
        col += 1

        ffmpeg_color = C["success"] if self._ffmpeg_ok else C["error"]
        ffmpeg_text  = T("ffmpeg_ok") if self._ffmpeg_ok else T("ffmpeg_fail")
        ctk.CTkLabel(bar, text=ffmpeg_text, font=(FONT_FAMILY, 10),
                     text_color=ffmpeg_color).grid(row=0, column=col, padx=(0, 8), pady=PY)
        col += 1

        ctk.CTkButton(bar, text="⚙", width=36, height=28,
                      fg_color="transparent", hover_color=C["bg_card"],
                      font=(FONT_FAMILY, 14), text_color=C["text_secondary"],
                      command=self._open_settings).grid(row=0, column=col, padx=(0, 2), pady=PY)
        col += 1

        ctk.CTkButton(bar, text="─", width=36, height=28,
                      fg_color="transparent", hover_color=C["bg_card"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._minimize).grid(row=0, column=col, padx=0, pady=PY)
        col += 1

        self._max_btn = ctk.CTkButton(bar, text="□", width=36, height=28,
                      fg_color="transparent", hover_color=C["bg_card"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._toggle_maximize)
        self._max_btn.grid(row=0, column=col, padx=0, pady=PY)
        col += 1

        ctk.CTkButton(bar, text="✕", width=36, height=28,
                      fg_color="transparent", hover_color=C["error"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._root.destroy).grid(row=0, column=col, padx=(0, 6), pady=PY)

    def _titlebar_press(self, event):
        self._drag_x = event.x_root - self._root.winfo_x()
        self._drag_y = event.y_root - self._root.winfo_y()

    def _titlebar_drag(self, event):
        if self._maximized:
            self._restore_maximize()
            self._drag_x = self._root.winfo_width() // 2
            self._drag_y = 20
        self._root.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _minimize(self):
        import ctypes
        child = self._root.winfo_id()
        hwnd  = ctypes.windll.user32.GetAncestor(child, 2) or child
        ctypes.windll.user32.ShowWindow(hwnd, 6)

    def _toggle_maximize(self, event=None):
        if self._maximized:
            self._restore_maximize()
        else:
            self._restore_geometry = self._root.geometry()
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            self._root.geometry(f"{sw}x{sh}+0+0")
            self._maximized = True
            self._max_btn.configure(text="❐")

    def _restore_maximize(self):
        self._root.geometry(self._restore_geometry)
        self._maximized = False
        self._max_btn.configure(text="□")

    def _build_input_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(12, 6))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="TikTok URL", font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=0, column=0, sticky="w",
                     padx=16, pady=(10, 2))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        inner.grid_columnconfigure(0, weight=1)

        self._url_var = ctk.StringVar()
        self._url_entry = ctk.CTkEntry(
            inner, textvariable=self._url_var, height=38,
            font=(FONT_FAMILY, 13), fg_color=C["bg_input"],
            placeholder_text="Paste a TikTok video URL\u2026",
            border_color=C["border"],
        )
        self._url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._url_entry.bind("<Return>", lambda _: self._start_download())

        ctk.CTkButton(inner, text=T("paste"), width=72, height=38,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      command=self._paste_url).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(inner, text=T("clear"), width=66, height=38,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      command=lambda: self._url_var.set("")).grid(row=0, column=2)

    def _build_options_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=2, column=0, sticky="ew", padx=16, pady=6)
        frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(frame, text=T("type"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=0, column=0, padx=(16, 8), pady=(12, 4))

        saved_media = self._config.get("tt_media_type", "Video")

        toggle_frame = ctk.CTkFrame(frame, fg_color=C["bg_card"], corner_radius=8)
        toggle_frame.grid(row=0, column=1, sticky="w", padx=(0, 16), pady=(12, 4))

        self._audio_btn = ctk.CTkButton(
            toggle_frame, text=T("audio_btn"), width=90, height=28,
            font=(FONT_FAMILY, 12), corner_radius=6,
            fg_color="transparent", hover_color=C["bg_secondary"],
            text_color=C["text_secondary"], command=lambda: self._set_media_type("Audio"),
        )
        self._audio_btn.pack(side="left", padx=3, pady=3)

        self._video_btn = ctk.CTkButton(
            toggle_frame, text=T("video_btn"), width=90, height=28,
            font=(FONT_FAMILY, 12), corner_radius=6,
            fg_color=self.TT_PINK, hover_color=self.TT_PINK_HOV,
            text_color="white", command=lambda: self._set_media_type("Video"),
        )
        self._video_btn.pack(side="left", padx=(0, 3), pady=3)

        ctk.CTkLabel(frame, text=T("format"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=0, column=2, padx=(0, 8), pady=(12, 4))

        if saved_media == "Audio":
            fmt_values = list(AUDIO_FORMATS.keys())
            saved_fmt  = self._config.get("tt_format_audio", "MP3 256 kbps")
            if saved_fmt not in AUDIO_FORMATS:
                saved_fmt = "MP3 256 kbps"
            self._audio_btn.configure(fg_color=self.TT_PINK, text_color="white")
            self._video_btn.configure(fg_color="transparent", text_color=C["text_secondary"])
        else:
            fmt_values = list(VIDEO_FORMATS.keys())
            saved_fmt  = self._config.get("tt_format_video", "MP4 1080p")
            if saved_fmt not in VIDEO_FORMATS:
                saved_fmt = "MP4 1080p"

        self._format_var = ctk.StringVar(value=saved_fmt)
        self._format_var.trace_add("write", lambda *_: self._save_ui_prefs())
        self._format_dropdown = CustomDropdown(frame, variable=self._format_var,
                                               values=fmt_values, width=220,
                                               accent="#EE1D52", accent_dim="#3d0617")
        self._format_dropdown.grid(row=0, column=3, sticky="w", padx=(0, 16), pady=(12, 4))

        ctk.CTkLabel(frame, text=T("save_to"), font=(FONT_FAMILY, 12),
                     text_color=C["text_secondary"]).grid(row=1, column=0, padx=(16, 8), pady=(4, 12))

        self._outdir_var = ctk.StringVar(value=self._config.get("output_dir", ""))
        self._outdir_var.trace_add("write", lambda *_: self._save_ui_prefs())
        ctk.CTkEntry(frame, textvariable=self._outdir_var,
                     height=34, font=(FONT_FAMILY, 12),
                     fg_color=C["bg_input"], border_color=C["border"]
                     ).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=(4, 12))

        ctk.CTkButton(frame, text=T("browse"), width=80, height=34,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      command=self._browse_outdir).grid(row=1, column=3, sticky="w", padx=(0, 8), pady=(4, 12))

        self._dl_btn = ctk.CTkButton(
            frame, text=T("download"), width=130, height=38,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color=self.TT_PINK, hover_color=self.TT_PINK_HOV,
            command=self._start_download,
        )
        self._dl_btn.grid(row=0, column=4, rowspan=2, padx=(4, 16))

        self._media_type = ctk.StringVar(value=saved_media)

    def _set_media_type(self, kind: str):
        self._media_type.set(kind)
        if kind == "Audio":
            self._audio_btn.configure(fg_color=self.TT_PINK, text_color="white")
            self._video_btn.configure(fg_color="transparent", text_color=C["text_secondary"])
            self._format_dropdown._values = list(AUDIO_FORMATS.keys())
            saved = self._config.get("tt_format_audio", "MP3 256 kbps")
            if saved not in AUDIO_FORMATS:
                saved = "MP3 256 kbps"
            self._format_var.set(saved)
        else:
            self._video_btn.configure(fg_color=self.TT_PINK, text_color="white")
            self._audio_btn.configure(fg_color="transparent", text_color=C["text_secondary"])
            self._format_dropdown._values = list(VIDEO_FORMATS.keys())
            saved = self._config.get("tt_format_video", "MP4 1080p")
            if saved not in VIDEO_FORMATS:
                saved = "MP4 1080p"
            self._format_var.set(saved)
        self._config["tt_media_type"] = kind
        save_config(self._config)

    def _build_queue_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=6)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        ctk.CTkLabel(hdr, text=T("download_queue"), font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_primary"]).pack(side="left")
        self._queue_count_lbl = ctk.CTkLabel(hdr, text="", font=(FONT_FAMILY, 11),
                                              text_color=C["text_secondary"])
        self._queue_count_lbl.pack(side="left", padx=8)
        ctk.CTkButton(hdr, text=T("clear_done"), width=90, height=26,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      font=(FONT_FAMILY, 11),
                      command=self._clear_done).pack(side="right")

        self._queue_scroll = ctk.CTkScrollableFrame(
            frame, fg_color="transparent",
            scrollbar_button_color=C["bg_card"],
            scrollbar_button_hover_color=C["border"],
        )
        self._queue_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._queue_scroll.grid_columnconfigure(0, weight=1)
        self._queue_row = 0

    def _build_log_panel(self):
        frame = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"], corner_radius=10)
        frame.grid(row=4, column=0, sticky="nsew", padx=16, pady=(6, 14))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        ctk.CTkLabel(hdr, text=T("log_panel"), font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_primary"]).pack(side="left")
        ctk.CTkButton(hdr, text=T("clear_log"), width=60, height=24,
                      fg_color=C["bg_card"], hover_color=C["border"],
                      font=(FONT_FAMILY, 11),
                      command=self._clear_log).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            frame, font=("Consolas", 11), fg_color=C["bg_input"],
            text_color=C["text_secondary"], state="disabled",
            border_color=C["border"], border_width=1,
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{ts}] {msg}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _save_ui_prefs(self):
        fmt   = self._format_var.get()
        media = self._media_type.get() if hasattr(self, "_media_type") else "Video"
        if media == "Audio":
            self._config["tt_format_audio"] = fmt
        else:
            self._config["tt_format_video"] = fmt
        self._config["tt_media_type"] = media
        self._config["output_dir"]    = self._outdir_var.get()
        save_config(self._config)

    def _open_settings(self):
        def on_save(cfg):
            self._config.update(cfg)
            save_config(self._config)

        TikTokSettingsDialog(
            self._root, self._config,
            on_save=on_save,
            on_quit=self._root.destroy,
        )

    def _paste_url(self):
        try:
            self._url_var.set(self._root.clipboard_get().strip())
        except Exception:
            pass

    def _browse_outdir(self):
        d = filedialog.askdirectory(title=T("select_outdir"),
                                    initialdir=self._outdir_var.get())
        if d:
            self._outdir_var.set(d)

    def _clear_done(self):
        done_ids = [tid for tid, w in list(self._task_widgets.items())
                    if w._task.status in (DownloadStatus.DONE, DownloadStatus.ERROR)]
        for tid in done_ids:
            self._task_widgets.pop(tid).destroy()
        for row, (_, w) in enumerate(self._task_widgets.items()):
            w.grid(row=row, column=0, sticky="ew", padx=4, pady=4)
        self._queue_row = len(self._task_widgets)
        self._update_queue_count()

    def _update_queue_count(self):
        n = len(self._task_widgets)
        self._queue_count_lbl.configure(
            text=f"({n} item{'s' if n != 1 else ''})" if n else ""
        )

    def _start_download(self):
        url = self._url_var.get().strip()
        if not url:
            messagebox.showwarning(T("mb_no_url_title"), T("mb_no_url_tiktok"))
            return
        out_dir = self._outdir_var.get().strip()
        if not out_dir:
            messagebox.showwarning(T("mb_no_outdir_title"), T("mb_no_outdir"))
            return

        self._dl_btn.configure(state="disabled", text=T("loading"))
        self._url_var.set("")
        threading.Thread(target=self._resolve_and_queue, args=(url, out_dir), daemon=True).start()

    def _resolve_and_queue(self, url: str, out_dir: str):
        try:
            self._root.after(0, lambda: self._log(T("fetching_tiktok")))
            entries = extract_tiktok_entries(url)
            fmt = self._format_var.get()
            self._root.after(0, lambda: self._log(T("queued_n_videos").format(len(entries), fmt)))
            for entry in entries:
                self._root.after(0, lambda e=entry: self._queue_entry(e, out_dir, fmt))
        except Exception as exc:
            msg = str(exc)
            self._root.after(0, lambda m=msg: (
                self._log(T("err_resolving").format(m)),
                messagebox.showerror(T("mb_error_title"), m),
            ))
        finally:
            self._root.after(0, lambda: self._dl_btn.configure(
                state="normal", text=T("download")
            ))

    def _queue_entry(self, entry: dict, out_dir: str, fmt: str):
        task_id = str(uuid.uuid4())
        task = TikTokTask(
            task_id     = task_id,
            url         = entry["url"],
            title       = entry["title"],
            output_dir  = out_dir,
            format_name = fmt,
        )

        def on_progress(t: TikTokTask):
            self._root.after(0, lambda: widget.update_progress(t.progress))

        def on_status(t: TikTokTask):
            self._root.after(0, lambda: (
                widget.update_status(t.status, t.error_msg),
                self._log(_tt_status_log_line(t)),
            ))

        def on_done(t: TikTokTask):
            self._root.after(0, lambda: (
                widget.update_status(t.status, t.error_msg),
                widget.update_progress(t.progress),
            ))

        task.on_progress = on_progress
        task.on_status   = on_status
        task.on_done     = on_done

        widget = TikTokQueueItemWidget(self._queue_scroll, task)
        widget.grid(row=self._queue_row, column=0, sticky="ew", padx=4, pady=4)
        self._queue_row += 1
        self._task_widgets[task_id] = widget
        self._update_queue_count()

        self._log(T("log_queued").format(task.display_name()))
        self._manager.submit(task)


# ---------------------------------------------------------------------------
# Launcher – choose downloader on startup
# ---------------------------------------------------------------------------

class LauncherApp:
    def __init__(self):
        self._choice: Optional[str] = None
        self._cfg    = load_config()
        self._root   = ctk.CTk()
        self._root.title(T("launcher_title"))
        _lpos = self._cfg.get("launcher_pos", "")
        if _lpos:
            self._root.geometry(f"720x360{_lpos}")
        else:
            self._root.geometry(_center_geometry(self._root, 720, 360))
        self._root.resizable(False, False)
        self._root.configure(fg_color=C["bg_primary"])
        self._root.overrideredirect(True)
        self._root.attributes("-alpha", 0)

        self._drag_x = 0
        self._drag_y = 0

        self._build_ui()
        self._root.update()
        self._root.update()
        self._root.attributes("-alpha", 1)
        self._root.bind("<Destroy>", lambda e: self._save_pos() if e.widget is self._root else None)
        threading.Thread(target=warmup_icons, daemon=True).start()
        self._root.after(10, lambda: _apply_win11_rounded(self._root.winfo_id()))
        self._root.after(10, lambda: _apply_taskbar_button(self._root))
        self._root.after(50, lambda: _bring_to_front(self._root))

    def run(self) -> Optional[str]:
        self._root.mainloop()
        return self._choice

    def _save_pos(self):
        import re
        m = re.search(r"([+-]\d+[+-]\d+)$", self._root.geometry())
        if m:
            self._cfg["launcher_pos"] = m.group(1)
            save_config(self._cfg)

    def _choose(self, choice: str):
        self._choice = choice
        self._root.destroy()

    def _build_ui(self):
        bar = ctk.CTkFrame(self._root, fg_color=C["bg_secondary"],
                           corner_radius=0, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        bar.bind("<ButtonPress-1>", self._titlebar_press)
        bar.bind("<B1-Motion>",     self._titlebar_drag)

        ctk.CTkLabel(bar, text=T("launcher_title"), font=(FONT_FAMILY, 13, "bold"),
                     text_color=C["text_primary"]).pack(side="left", padx=14, pady=(6, 0))
        ctk.CTkButton(bar, text="✕", width=36, height=28,
                      fg_color="transparent", hover_color=C["error"],
                      font=(FONT_FAMILY, 13), text_color=C["text_secondary"],
                      command=self._root.destroy).pack(side="right", padx=6, pady=(6, 0))

        body = ctk.CTkFrame(self._root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(body, text=T("choose_downloader"),
                     font=(FONT_FAMILY, 18, "bold"),
                     text_color=C["text_primary"]).pack(pady=(0, 20))

        cards = ctk.CTkFrame(body, fg_color="transparent")
        cards.pack(fill="both", expand=True)
        cards.grid_columnconfigure(0, weight=1)
        cards.grid_columnconfigure(1, weight=1)
        cards.grid_columnconfigure(2, weight=1)

        self._build_card(cards, col=0,
                         icon=spotify_icon(44),
                         icon_color=C["accent"],
                         title="Spotify",
                         desc=T("spotify_desc"),
                         btn_color=C["accent"],
                         btn_hover=C["accent_hover"],
                         btn_text=T("open_spotify"),
                         choice="spotify")

        self._build_card(cards, col=1,
                         icon=youtube_icon(44),
                         icon_color="#FF4444",
                         title="YouTube",
                         desc=T("youtube_desc"),
                         btn_color="#CC2222",
                         btn_hover="#AA1111",
                         btn_text=T("open_youtube"),
                         choice="youtube")

        self._build_card(cards, col=2,
                         icon=tiktok_icon(44),
                         icon_color="#EE1D52",
                         title="TikTok",
                         desc=T("tiktok_desc"),
                         btn_color="#EE1D52",
                         btn_hover="#C71542",
                         btn_text=T("open_tiktok"),
                         choice="tiktok")

    def _build_card(self, parent, col: int, icon, icon_color: str,
                    title: str, desc: str, btn_color: str, btn_hover: str,
                    btn_text: str, choice: str):
        card = ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0 if col == 0 else 8, 0))

        if isinstance(icon, ctk.CTkImage):
            ctk.CTkLabel(card, image=icon, text="").pack(pady=(24, 4))
        else:
            ctk.CTkLabel(card, text=icon, font=(FONT_FAMILY, 36),
                         text_color=icon_color).pack(pady=(24, 4))
        ctk.CTkLabel(card, text=title, font=(FONT_FAMILY, 16, "bold"),
                     text_color=C["text_primary"]).pack()
        ctk.CTkLabel(card, text=desc, font=(FONT_FAMILY, 11),
                     text_color=C["text_secondary"],
                     justify="center").pack(pady=(4, 16))
        ctk.CTkButton(card, text=btn_text, height=36,
                      fg_color=btn_color, hover_color=btn_hover,
                      font=(FONT_FAMILY, 13, "bold"),
                      command=lambda c=choice: self._choose(c)).pack(padx=20, pady=(0, 20))

    def _titlebar_press(self, event):
        self._drag_x = event.x_root - self._root.winfo_x()
        self._drag_y = event.y_root - self._root.winfo_y()

    def _titlebar_drag(self, event):
        self._root.geometry(
            f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}"
        )
