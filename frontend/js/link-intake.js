import { h } from "./dom.js";
import { api } from "./bridge.js";
import { T } from "./i18n.js";
import { findLink, urlFromShortcut } from "./links.js";
import { alertModal } from "./components/modal.js";
import { showLinkBanner } from "./components/link-banner.js";

// Two ways a link reaches the app without being typed: dropped on the window, and copied
// somewhere else (the clipboard is checked when the window is used again).
//   onLink({url, service}) opens the downloader of that site with the link in its field.

const modalOpen = () => document.querySelector(".modal-overlay:not(.leaving)") !== null;

async function textOfDrop(data) {
  const text = data.getData("text/uri-list") || data.getData("text/plain");
  if (text) return text;
  // An Internet shortcut (.url file) or a text file dragged from the desktop.
  for (const file of data.files || []) {
    if (!/\.(url|txt)$/i.test(file.name) || file.size > 64 * 1024) continue;
    const content = await file.text();
    return file.name.toLowerCase().endsWith(".url") ? urlFromShortcut(content) : content;
  }
  return "";
}

const carriesLink = (data) => !!data && ["text/uri-list", "text/plain", "Files"].some((type) => data.types?.includes(type));

// Text the user drags around inside the app (selected log lines, the URL field) is not a drop from outside.
let draggingInside = false;
document.addEventListener("dragstart", () => { draggingInside = true; });
document.addEventListener("dragend", () => { draggingInside = false; });
const fromOutside = (data) => !draggingInside && carriesLink(data);

export function installDropTarget({ onLink }) {
  const overlay = h("div", { class: "drop-overlay", hidden: true, "aria-hidden": "true" }, h("div", { class: "drop-box" }, T("drop_hint")));
  document.body.append(overlay);
  let depth = 0;   // dragenter/dragleave also fire for every child element

  const show = (on) => {
    overlay.hidden = !on;
    if (!on) depth = 0;
  };

  document.addEventListener("dragenter", (ev) => {
    if (!fromOutside(ev.dataTransfer)) return;
    ev.preventDefault();
    depth++;
    if (!modalOpen()) show(true);
  });
  document.addEventListener("dragover", (ev) => {
    if (!fromOutside(ev.dataTransfer)) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = modalOpen() ? "none" : "copy";
  });
  document.addEventListener("dragleave", (ev) => {
    if (!fromOutside(ev.dataTransfer)) return;
    depth = Math.max(0, depth - 1);
    if (depth === 0) show(false);
  });
  document.addEventListener("drop", async (ev) => {
    if (!fromOutside(ev.dataTransfer)) return;
    ev.preventDefault();   // the webview would otherwise navigate to the dropped link
    show(false);
    if (modalOpen()) return;
    try {
      const link = findLink(await textOfDrop(ev.dataTransfer));
      if (link) onLink(link);
      else await alertModal(T("mb_error_title"), T("link_unsupported"), "warning");
    } catch (err) {
      console.error("drop failed", err);
    }
  });
}

/**
 * Offer a link that was copied outside the app. Checked at start and whenever the window gets
 * focus again. A link is offered once; it is never offered again just because the window was
 * focused again, and nothing of the clipboard is stored.
 *   isShown(url) tells whether a downloader already has this link in its field.
 */
export function watchClipboard({ onLink, isShown }) {
  let lastSeen = "";
  let checking = false;

  async function check() {
    if (checking || modalOpen()) return;
    checking = true;
    try {
      const text = await api.paste();
      if (!text || text === lastSeen) return;
      lastSeen = text;
      const link = findLink(text);
      if (!link || isShown(link.url)) return;
      showLinkBanner({ ...link, onUse: () => onLink(link) });
    } catch (err) {
      console.debug("clipboard not readable", err);
    } finally {
      checking = false;
    }
  }

  window.addEventListener("focus", check);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) check();
  });
  check();
}
