import { splitUrls } from "./urls.js";

// Which downloader a link belongs to, decided by the host name of the link.
const SITES = [
  { id: "spotify", hosts: ["spotify.com", "spotify.link"] },
  { id: "youtube", hosts: ["youtube.com", "youtu.be", "youtube-nocookie.com"] },
  { id: "tiktok", hosts: ["tiktok.com"] },
  { id: "soundcloud", hosts: ["soundcloud.com", "snd.sc"] },
  { id: "instagram", hosts: ["instagram.com", "instagr.am"] },
];

/** Service id for an http(s) link, or null for anything else. */
export function serviceForUrl(url) {
  let host;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    host = parsed.hostname.toLowerCase();
  } catch {
    return null;
  }
  const site = SITES.find((s) => s.hosts.some((h) => host === h || host.endsWith(`.${h}`)));
  return site ? site.id : null;
}

/** The first link of a supported site in free text (a drop, the clipboard): {url, service} or null. */
export function findLink(text) {
  for (const part of splitUrls(text || "")) {
    if (part.type !== "url") continue;
    const service = serviceForUrl(part.value);
    if (service) return { url: part.value, service };
  }
  return null;
}

/** Text of an Internet shortcut (.url) file: the line "URL=...". */
export function urlFromShortcut(text) {
  const match = /^\s*URL\s*=\s*(\S+)/im.exec(text || "");
  return match ? match[1] : "";
}

/**
 * Should a link typed or pasted into the field of `view` move to the downloader of its own
 * site? The Spotify field also takes YouTube links (it finds the songs there), so those stay.
 */
export function belongsElsewhere(view, service) {
  if (!service || service === view) return false;
  return !(view === "spotify" && service === "youtube");
}
