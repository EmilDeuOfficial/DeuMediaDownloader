# Spotify API setup / Spotify-API einrichten

*English first, deutsche Version weiter unten.*

The Spotify downloader reads track, playlist and album information through the free
Spotify Web API. For that it needs a **Client ID** and a **Client Secret** of your own
(free, takes about two minutes).

## Steps

1. Open <https://developer.spotify.com/dashboard> and log in with your Spotify account.
2. Click **Create app**.
   - **App name** and **description**: anything you like.
   - **Redirect URI**: `http://127.0.0.1:8888/callback` (click **Add**). It must match
     exactly. The app shows the same value in its settings so you can copy it.
   - **Which API/SDKs**: tick **Web API**.
   - Accept the terms and click **Save**.
3. Open your new app, then **Settings**. Copy the **Client ID** and click **View client
   secret** to copy the **Client Secret**.
4. In DeuMediaDownloader open **Spotify**, click the gear icon and paste both values
   under **Spotify API Credentials**. Click **Save**.

The first time the app talks to Spotify, your browser opens once and asks you to allow
access to your playlists. Confirm it; the login is remembered afterwards.

## Troubleshooting

- **"Spotify auth error"**: check that Client ID and Client Secret have no spaces and
  that the Redirect URI is exactly `http://127.0.0.1:8888/callback`.
- Playlists of other users work as long as they are public.

---

# Deutsch

Der Spotify-Downloader liest Track-, Playlist- und Album-Infos über die kostenlose
Spotify-Web-API. Dafür braucht er eine eigene **Client-ID** und ein **Client-Secret**
(kostenlos, dauert etwa zwei Minuten).

## Schritte

1. <https://developer.spotify.com/dashboard> öffnen und mit deinem Spotify-Konto einloggen.
2. Auf **Create app** klicken.
   - **App name** und **Beschreibung**: beliebig.
   - **Redirect URI**: `http://127.0.0.1:8888/callback` (auf **Add** klicken). Sie muss
     genau stimmen. Die App zeigt denselben Wert in den Einstellungen zum Kopieren.
   - **Which API/SDKs**: **Web API** anhaken.
   - Bedingungen akzeptieren und **Save** klicken.
3. Deine neue App öffnen, dann **Settings**. Die **Client ID** kopieren und mit **View
   client secret** das **Client Secret** anzeigen und kopieren.
4. In DeuMediaDownloader **Spotify** öffnen, auf das Zahnrad klicken und beide Werte
   unter **Spotify-API-Zugangsdaten** einfügen. **Speichern** klicken.

Beim ersten Kontakt mit Spotify öffnet sich einmal dein Browser und fragt, ob die App auf
deine Playlists zugreifen darf. Bestätige das; der Login wird danach gemerkt.

## Probleme

- **"Spotify-Authentifizierungsfehler"**: Prüfe, dass Client-ID und Client-Secret keine
  Leerzeichen enthalten und die Redirect URI genau `http://127.0.0.1:8888/callback` ist.
- Playlists anderer Nutzer funktionieren, solange sie öffentlich sind.
