# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DeuMediaDownloader (built by build.py).
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("frontend", "frontend"),
    ("img/app.ico", "img"),
]
binaries = []
hiddenimports = []

# Packages that load code or data dynamically and need everything collected.
for package in ("webview", "yt_dlp", "curl_cffi", "spotipy"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("clr_loader")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "customtkinter", "PIL", "aggdraw", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DeuMediaDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="img/app.ico",
)
