"""
Build script: Python app -> EXE (PyInstaller) -> Installer (Inno Setup)
Run with: python build.py

Code signing (optional): set one of these environment variables and the build signs the
.exe, the setup and the uninstaller with signtool (Windows SDK):
  DMD_SIGN_THUMBPRINT   SHA-1 thumbprint of a certificate in the Windows certificate store
                        (also works for certificates on a USB token or HSM)
  DMD_SIGN_PFX          path to a .pfx file, password in DMD_SIGN_PFX_PASSWORD
  DMD_SIGN_TIMESTAMP    timestamp server (default: http://timestamp.digicert.com)
  DMD_SIGNTOOL          path to signtool.exe if it is not found automatically
Without these the build runs unsigned, as before.
"""
import glob
import subprocess
import sys
import os
import re
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


def app_version() -> str:
    text = (ROOT / "backend" / "config.py").read_text(encoding="utf-8")
    return re.search(r'^APP_VERSION = "([^"]+)"', text, re.M).group(1)


def check_version(version: str):
    """The README badge must show the version that is being built (release tag v<version>)."""
    badge = re.search(r"badge/version-v([\w.]+)-", (ROOT / "README.md").read_text(encoding="utf-8"))
    if not badge or badge.group(1) != version:
        found = badge.group(1) if badge else "none"
        print(f"[ERROR] README badge shows v{found}, backend/config.py says {version}.")
        sys.exit(1)


def run(cmd: list, secret: str = "", **kwargs):
    shown = " ".join(str(c) for c in cmd)
    if secret:
        shown = shown.replace(secret, "***")
    print(f"\n>>> {shown}\n")
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


def find_signtool() -> str | None:
    if os.environ.get("DMD_SIGNTOOL"):
        return os.environ["DMD_SIGNTOOL"]
    found = shutil.which("signtool")
    if found:
        return found
    kits = os.path.expandvars(r"%ProgramFiles(x86)%\Windows Kits\10\bin\*\x64\signtool.exe")
    candidates = sorted(glob.glob(kits))
    return candidates[-1] if candidates else None


def sign_args() -> tuple[list, str] | None:
    """signtool arguments (without the file) and the secret to hide in output, or None
    when no certificate is configured."""
    thumbprint = os.environ.get("DMD_SIGN_THUMBPRINT", "").replace(" ", "")
    pfx = os.environ.get("DMD_SIGN_PFX", "")
    if not (thumbprint or pfx):
        return None
    signtool = find_signtool()
    if not signtool:
        print("[ERROR] Code signing is configured but signtool.exe was not found.")
        print("        Install the Windows SDK (winget install Microsoft.WindowsSDK.10.0.26100)")
        print("        or set DMD_SIGNTOOL to the full path of signtool.exe.")
        sys.exit(1)
    timestamp = os.environ.get("DMD_SIGN_TIMESTAMP", "http://timestamp.digicert.com")
    args = [signtool, "sign", "/fd", "sha256", "/tr", timestamp, "/td", "sha256",
            "/d", "DeuMediaDownloader"]
    secret = ""
    if thumbprint:
        args += ["/sha1", thumbprint]
    else:
        args += ["/f", pfx]
        secret = os.environ.get("DMD_SIGN_PFX_PASSWORD", "")
        if secret:
            args += ["/p", secret]
    return args, secret


def sign(path: Path, signing: tuple[list, str]):
    args, secret = signing
    print(f"[*] Signing {path.name}...")
    run(args + [str(path)], secret=secret)


def inno_sign_option(signing: tuple[list, str]) -> list:
    """ISCC options that let Inno Setup sign the setup and the uninstaller itself
    ($q is a quote and $f the file name in Inno's sign tool syntax)."""
    args, _ = signing
    quoted = " ".join(f"$q{a}$q" if " " in a else a for a in args)
    return [f"/Sdmdsign={quoted} $f", "/DSIGN"]


def clean():
    print("[*] Cleaning previous build artifacts...")
    for d in [BUILD, ROOT / "__pycache__"]:
        if d.exists():
            shutil.rmtree(d)
    exe = DIST / "DeuMediaDownloader.exe"
    if exe.exists():
        exe.unlink()


def build_exe():
    print("[*] Building EXE with PyInstaller...")
    run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        str(ROOT / "DeuMediaDownloader.spec"),
    ], cwd=ROOT)
    exe = DIST / "DeuMediaDownloader.exe"
    if not exe.exists():
        print("[ERROR] PyInstaller output not found.")
        sys.exit(1)
    size_mb = exe.stat().st_size / 1024 / 1024
    print(f"[OK] DeuMediaDownloader.exe built ({size_mb:.1f} MB)")


def build_installer(iscc: str, signing=None):
    print("[*] Building installer with Inno Setup...")
    options = inno_sign_option(signing) if signing else []
    run([iscc, *options, str(ROOT / "installer.iss")], secret=signing[1] if signing else "", cwd=ROOT)
    installer = DIST / "DeuMediaDownloader_Setup.exe"
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
    print("  DeuMediaDownloader - Build Pipeline")
    print("=" * 60)

    version = app_version()
    check_version(version)
    print(f"[*] Version {version} (release tag v{version})")

    signing = sign_args()
    print("[*] Code signing: " + ("on" if signing else "off (no certificate configured)"))

    clean()
    build_exe()
    if signing:
        sign(DIST / "DeuMediaDownloader.exe", signing)

    iscc = find_inno()
    if not iscc:
        iscc = install_inno()

    build_installer(iscc, signing)
    print("[DONE] Build complete.")


if __name__ == "__main__":
    main()
