# CLAUDE.md — DeuDownloader

## Projektübersicht

DeuDownloader ist ein Spotify/Media-Downloader mit GUI (Python-basiert).
Repository: `https://github.com/EmilDeuOfficial/DeuDownloader.git`

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
  --name "DeuDownloader" \
  --icon "img/app.ico" \
  --add-data "img;img" \
  main.py
```

Output: `dist/DeuDownloader.exe`

### Schritt 3 — Installer bauen (Inno Setup)

Inno Setup ist unter `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` installiert.

```bash
"/c/Users/emilo/AppData/Local/Programs/Inno Setup 6/ISCC.exe" installer.iss
```

Output: `dist/DeuDownloader_Setup.exe`

### Schritt 4 — Git Commit & Tag

```bash
git add .
git commit -m "fix: v{VERSION} — {kurze Beschreibung}"   # Bugfix
git commit -m "feat: v{VERSION} — {kurze Beschreibung}"  # Feature
git tag -a "v{VERSION}" -m "Release v{VERSION}"
```

### Schritt 5 — Zu GitHub pushen

```bash
git push origin master
git push origin --tags
```

### Schritt 6 — GitHub Release erstellen (GitHub CLI)

> **Wichtig:** Es wird ausschließlich der Installer hochgeladen — die portable EXE wird NICHT als Release-Asset veröffentlicht.

#### Einheitliches Release-Format (PFLICHT)

**Für Bugfixes:**
```bash
gh release create "v{VERSION}" \
  "dist/DeuDownloader_Setup.exe" \
  --title "DeuDownloader v{VERSION}" \
  --notes "## DeuDownloader v{VERSION} — Bugfix

### Fix
- {Was wurde behoben}

### Download
| Datei | Beschreibung |
|-------|-------------|
| DeuDownloader_Setup.exe | Windows-Installer (empfohlen) |

### Systemvoraussetzungen
- Windows 10 / 11
- FFmpeg (wird vom Installer eingerichtet)"
```

**Für neue Features:**
```bash
gh release create "v{VERSION}" \
  "dist/DeuDownloader_Setup.exe" \
  --title "DeuDownloader v{VERSION}" \
  --notes "## DeuDownloader v{VERSION} — {Feature-Name}

### Neu in dieser Version
- {Was wurde hinzugefügt}

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
DeuDownloader/
├── main.py
├── downloader.py
├── converter.py
├── ui.py
├── config.py              ← APP_VERSION hier pflegen
├── img/
│   ├── app.ico            ← Windows-Icon (generiert aus app-icon.svg)
│   └── app-icon.svg       ← Quell-Icon
├── tools/
│   └── svg_to_ico.py      ← Icon-Konvertierung (SVG → ICO)
├── installer.iss          ← Inno Setup Script
├── requirements.txt
├── .claude/CLAUDE.md      ← diese Datei
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

---

## Voraussetzungen auf dem Build-System

| Tool | Zweck | Install |
|------|-------|---------|
| `pyinstaller` | EXE-Erstellung | `pip install pyinstaller` |
| `inno setup` | Installer-Build | `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` |
| `gh` (GitHub CLI) | Release erstellen | https://cli.github.com |

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
pyinstaller → dist/DeuDownloader.exe
    ↓
ISCC.exe installer.iss → dist/DeuDownloader_Setup.exe
    ↓
git add . && git commit -m "fix/feat: vX.X.X — Beschreibung" && git tag
    ↓
git push origin master && git push origin --tags
    ↓
gh release create vX.X.X (nur Installer: DeuDownloader_Setup.exe)
    ↓
Release-Format: "## DeuDownloader vX.X.X — {Bugfix|Feature-Name}"
```

**Dieser Ablauf ist nicht optional — er wird nach jedem Update automatisch ausgeführt.**
