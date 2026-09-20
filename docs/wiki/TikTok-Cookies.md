# TikTok cookies / TikTok-Cookies

*English first, deutsche Version weiter unten.*

TikTok blocks most anonymous downloads and DeuMediaDownloader then shows an
"Unexpected response" error. Give the app your logged-in TikTok session and it works
again. There are two ways.

## Option 1: Firefox (easiest)

1. Install Firefox, open <https://www.tiktok.com> and log in.
2. In DeuMediaDownloader open **TikTok**, click the gear icon and go to **Authentication**.
3. Set **Browser Cookies** to **Firefox (recommended)** and click **Save**.

## Option 2: cookie file (Chrome, Edge, Brave, ...)

Since 2024 Chrome and Edge encrypt their cookies so that other programs cannot read
them ("App-Bound Encryption"). Choosing Chrome or Edge under **Browser Cookies** then
fails with a "Failed to decrypt" message. Use an exported cookie file instead:

1. Install the browser extension **Get cookies.txt LOCALLY**.
2. Open <https://www.tiktok.com> and log in.
3. Click the extension and export the cookies of the page as a `.txt` file
   (Netscape format), for example `tiktok-cookies.txt`.
4. In DeuMediaDownloader: **TikTok**, gear icon, **Authentication**, **Cookie File
   (alternative)**, click **Browse**, pick the file and click **Save**.

A cookie file takes priority over **Browser Cookies**. To stop using it, click
**Remove** next to the file field.

## Good to know

- The cookie file contains your TikTok login. Keep it private, never share it and
  delete it when you no longer need it.
- If downloads start failing again after some weeks, the cookies have expired. Export
  the file again.

---

# Deutsch

TikTok blockiert die meisten anonymen Downloads, DeuMediaDownloader zeigt dann den
Fehler "Unexpected response". Mit deiner eingeloggten TikTok-Sitzung funktioniert es
wieder. Dafür gibt es zwei Wege.

## Variante 1: Firefox (am einfachsten)

1. Firefox installieren, <https://www.tiktok.com> öffnen und einloggen.
2. In DeuMediaDownloader **TikTok** öffnen, auf das Zahnrad klicken und zu **Anmeldung** gehen.
3. **Browser-Cookies** auf **Firefox (empfohlen)** stellen und **Speichern** klicken.

## Variante 2: Cookie-Datei (Chrome, Edge, Brave, ...)

Chrome und Edge verschlüsseln ihre Cookies seit 2024 so, dass andere Programme sie
nicht lesen können ("App-Bound Encryption"). Wählst du bei **Browser-Cookies** Chrome
oder Edge, kommt deshalb "Failed to decrypt". Nutze stattdessen eine exportierte
Cookie-Datei:

1. Die Browser-Erweiterung **Get cookies.txt LOCALLY** installieren.
2. <https://www.tiktok.com> öffnen und einloggen.
3. Auf die Erweiterung klicken und die Cookies der Seite als `.txt`-Datei exportieren
   (Netscape-Format), zum Beispiel `tiktok-cookies.txt`.
4. In DeuMediaDownloader: **TikTok**, Zahnrad, **Anmeldung**, **Cookie-Datei
   (Alternative)**, **Durchsuchen** klicken, Datei wählen und **Speichern**.

Die Cookie-Datei hat Vorrang vor den **Browser-Cookies**. Zum Abschalten neben dem
Dateifeld auf **Entfernen** klicken.

## Gut zu wissen

- Die Cookie-Datei enthält deinen TikTok-Login. Halte sie privat, gib sie nicht weiter
  und lösche sie, wenn du sie nicht mehr brauchst.
- Schlagen Downloads nach einigen Wochen wieder fehl, sind die Cookies abgelaufen.
  Exportiere die Datei dann neu.
