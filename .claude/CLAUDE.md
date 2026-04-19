# CLAUDE.md — DeuMediaDownloader

## Projektübersicht

DeuMediaDownloader ist ein Spotify/Media-Downloader mit GUI (Python-basiert).
Repository: `git@github.com:EmilDeuOfficial/DeuMediaDownloader.git`

---

## Pflichtverhalten nach jedem Update

> **Nach jeder inhaltlichen Änderung am Code (Features, Bugfixes, Refactoring)
> führst du automatisch den vollständigen Build- und Release-Prozess aus.**
> Kein manueller Aufruf nötig — dies ist ein fester Bestandteil jedes Commits.

---

## Automatischer Build-Prozess (Pflicht nach jedem Update)

### Schritt 1 — Version erhöhen

Erhöhe die Versionsnummer in `config.py` automatisch nach folgendem Schema:

- **Patch** (Bugfix, kleine Änderung): `1.0.0` → `1.0.1`
- **Minor** (neues Feature): `1.0.0` → `1.1.0`
- **Major** (Breaking Change / großes Rewrite): `1.0.0` → `2.0.0`

```python
# config.py
APP_VERSION = "1.0.0"  # <-- wird automatisch erhöht
```

### Schritt 2 — EXE bauen (PyInstaller)

```bash
pyinstaller --noconfirm --onefile --windowed \
  --name "DeuMediaDownloader" \
  --icon "assets/icon.ico" \
  --add-data "assets;assets" \
  main.py
```

Output: `dist/DeuDownloader.exe`

### Schritt 3 — Installer bauen (Inno Setup oder NSIS)

Verwende das vorhandene Installer-Script (`installer.iss` oder `installer.nsi`).

**Inno Setup (bevorzugt):**
```bash
iscc installer.iss
```

**Alternativ NSIS:**
```bash
makensis installer.nsi
```

Output: `dist/DeuDownloader_Setup_v{VERSION}.exe`

### Schritt 4 — Git Commit & Tag

```bash
git add .
git commit -m "release: v{VERSION} — {kurze Beschreibung der Änderung}"
git tag -a "v{VERSION}" -m "Release v{VERSION}"
```

### Schritt 5 — Zu GitHub pushen

```bash
git remote set-url origin git@github.com:EmilDeuOfficial/DeuMediaDownloader.git
git push origin main
git push origin --tags
```

### Schritt 6 — GitHub Release erstellen (GitHub CLI)

> **Wichtig:** Es wird ausschließlich der Installer hochgeladen — die portable EXE wird NICHT als Release-Asset veröffentlicht.

```bash
gh release create "v{VERSION}" \
  "dist/DeuDownloader_Setup.exe" \
  --title "DeuDownloader v{VERSION}" \
  --notes "## Was ist neu in v{VERSION}?

{automatisch generierte Änderungsliste aus dem Commit}

### Download
| Datei | Beschreibung |
|-------|-------------|
| DeuDownloader_Setup.exe | Windows-Installer (empfohlen) |

### Systemvoraussetzungen
- Windows 10 / 11
- FFmpeg (wird vom Installer eingerichtet)"
```

---

## Dateistruktur (Pflichtdateien für den Build)

```
DeuMediaDownloader/
├── main.py
├── downloader.py
├── converter.py
├── ui.py
├── config.py              ← APP_VERSION hier pflegen
├── assets/
│   └── icon.ico
├── installer.iss          ← Inno Setup Script
├── requirements.txt
├── CLAUDE.md              ← diese Datei
└── dist/                  ← Build-Output (nicht commiten!)
```

`.gitignore` muss `dist/` und `build/` ausschließen:
```
dist/
build/
*.spec
__pycache__/
```

---

## Inno Setup Template (`installer.iss`)

Falls noch nicht vorhanden, erstelle diese Datei:

```ini
[Setup]
AppName=DeuMediaDownloader
AppVersion={VERSION}
AppPublisher=EmilDeuOfficial
DefaultDirName={autopf}\DeuMediaDownloader
DefaultGroupName=DeuMediaDownloader
OutputDir=dist
OutputBaseFilename=DeuMediaDownloader_Setup_v{VERSION}
SetupIconFile=assets\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\DeuMediaDownloader.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\DeuMediaDownloader"; Filename: "{app}\DeuMediaDownloader.exe"
Name: "{commondesktop}\DeuMediaDownloader"; Filename: "{app}\DeuMediaDownloader.exe"

[Run]
Filename: "{app}\DeuMediaDownloader.exe"; Description: "Jetzt starten"; Flags: postinstall nowait
```

---

## Voraussetzungen auf dem Build-System

| Tool | Zweck | Install |
|------|-------|---------|
| `pyinstaller` | EXE-Erstellung | `pip install pyinstaller` |
| `inno setup` | Installer-Build | https://jrsoftware.org/isinfo.php |
| `gh` (GitHub CLI) | Release erstellen | https://cli.github.com |
| SSH-Key | GitHub Push | `ssh-keygen`, dann in GitHub Settings hinterlegen |

---

## Verhalten bei Fehlern im Build

- Schlägt PyInstaller fehl → Fehler ausgeben, **keinen Commit durchführen**
- Schlägt der Installer-Build fehl → Fehler ausgeben, trotzdem EXE-only releasen mit Hinweis
- Schlägt `git push` fehl → SSH-Key prüfen, Fehlermeldung ausgeben
- Schlägt `gh release` fehl → Manuellen Release-Link und Anleitung ausgeben

---

## Zusammenfassung des Pflicht-Workflows

```
Code ändern
    ↓
Version in config.py erhöhen
    ↓
pyinstaller → DeuDownloader.exe
    ↓
iscc installer.iss → DeuDownloader_Setup_vX.X.X.exe
    ↓
git add . && git commit && git tag
    ↓
git push origin main --tags
    ↓
gh release create vX.X.X (nur Installer: DeuDownloader_Setup.exe)
```

**Dieser Ablauf ist nicht optional — er wird nach jedem Update automatisch ausgeführt.**
