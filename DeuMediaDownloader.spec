# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DeuMediaDownloader (built by build.py).
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

APP_VERSION = re.search(r'^APP_VERSION = "([^"]+)"', Path("backend/config.py").read_text(encoding="utf-8"), re.M).group(1)
_numbers = tuple((list(map(int, APP_VERSION.split("."))) + [0, 0, 0, 0])[:4])
# Version resource of the .exe: shown in Explorer, read by installer.iss and by code signing.
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_numbers, prodvers=_numbers),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "DeuMediaDownloader"),
            StringStruct("FileDescription", "DeuMediaDownloader"),
            StringStruct("FileVersion", APP_VERSION),
            StringStruct("InternalName", "DeuMediaDownloader"),
            StringStruct("OriginalFilename", "DeuMediaDownloader.exe"),
            StringStruct("ProductName", "DeuMediaDownloader"),
            StringStruct("ProductVersion", APP_VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

datas = [
    ("frontend", "frontend"),
    ("img/app.ico", "img"),
]
binaries = []
hiddenimports = []

# Packages that load code or data dynamically and need everything collected.
for package in ("webview", "yt_dlp", "yt_dlp_ejs", "curl_cffi", "spotipy", "proctap"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("clr_loader")

# backend/updater.py compares the bundled versions with downloaded updates.
datas += copy_metadata("yt-dlp")
datas += copy_metadata("yt-dlp-ejs")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # scipy is only used by proc-tap for audio format conversion, which recorder.py does not need.
    excludes=["tkinter", "customtkinter", "PIL", "aggdraw", "pytest", "scipy"],
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
    version=version_info,
)
