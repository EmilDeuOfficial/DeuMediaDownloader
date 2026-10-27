import { splitUrls } from "./urls.js";

/** The first http(s) link in free text (a drop), or "". */
export function firstUrl(text) {
  const part = splitUrls(text || "").find((p) => p.type === "url");
  return part ? part.value : "";
}

/** Text of an Internet shortcut (.url) file: the line "URL=...". */
export function urlFromShortcut(text) {
  const match = /^\s*URL\s*=\s*(\S+)/im.exec(text || "");
  return match ? match[1] : "";
}
