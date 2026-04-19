"""
Build script: Python app -> EXE (PyInstaller) -> Installer (Inno Setup)
Run with: python build.py
"""
import subprocess
import sys
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"

INNO_PATHS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 5\ISCC.exe"),
]


def run(cmd: list, **kwargs):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}\n")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"[ERROR] Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def find_inno() -> str | None:
    for p in INNO_PATHS:
        if os.path.isfile(p):
            return p
    return shutil.which("ISCC")


def install_inno():
    print("[*] Inno Setup not found. Installing via winget...")
    result = subprocess.run(
        ["winget", "install", "JRSoftware.InnoSetup",
         "--accept-source-agreements", "--accept-package-agreements"],
        capture_output=False,
    )
    if result.returncode != 0:
        print("[ERROR] Could not install Inno Setup automatically.")
        print("        Please install it manually from https://jrsoftware.org/isdl.php")
        sys.exit(1)
    # Refresh search after install
    for p in INNO_PATHS:
        if os.path.isfile(p):
            return p
    print("[ERROR] Inno Setup installed but ISCC.exe not found at expected paths.")
    print("        Try running this script again in a new terminal.")
    sys.exit(1)


def clean():
    print("[*] Cleaning previous build artifacts...")
    for d in [BUILD, ROOT / "__pycache__"]:
        if d.exists():
            shutil.rmtree(d)
    exe = DIST / "DeuDownloader.exe"
    if exe.exists():
        exe.unlink()


def build_exe():
    print("[*] Building EXE with PyInstaller...")
    run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        str(ROOT / "DeuDownloader.spec"),
    ], cwd=ROOT)
    exe = DIST / "DeuDownloader.exe"
    if not exe.exists():
        print("[ERROR] PyInstaller output not found.")
        sys.exit(1)
    size_mb = exe.stat().st_size / 1024 / 1024
    print(f"[OK] DeuDownloader.exe built ({size_mb:.1f} MB)")


def build_installer(iscc: str):
    print("[*] Building installer with Inno Setup...")
    run([iscc, str(ROOT / "installer.iss")], cwd=ROOT)
    installer = DIST / "DeuDownloader_Setup.exe"
    if not installer.exists():
        print("[ERROR] Installer not found after Inno Setup.")
        sys.exit(1)
    size_mb = installer.stat().st_size / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"  Installer ready: {installer}")
    print(f"  Size: {size_mb:.1f} MB")
    print(f"{'='*60}\n")


def main():
    print("=" * 60)
    print("  DeuDownloader — Build Pipeline")
    print("=" * 60)

    clean()
    build_exe()

    iscc = find_inno()
    if not iscc:
        iscc = install_inno()

    build_installer(iscc)
    print("[DONE] Build complete.")


if __name__ == "__main__":
    main()
