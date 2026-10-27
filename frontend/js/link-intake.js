import { h } from "./dom.js";
import { T } from "./i18n.js";
import { firstUrl, urlFromShortcut } from "./links.js";
import { alertModal } from "./components/modal.js";

// A link dragged from a browser (or an Internet shortcut file) onto a downloader window goes
// into its URL field. Which downloader it is stays the user's choice, nothing is detected.
//   isActive()  true while a downloader (not the launcher) is showing
//   onLink(url) puts the link into the field of that downloader

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

export function installDropTarget({ onLink, isActive }) {
  const overlay = h("div", { class: "drop-overlay", hidden: true, "aria-hidden": "true" }, h("div", { class: "drop-box" }, T("drop_hint")));
  document.body.append(overlay);
  let depth = 0;   // dragenter/dragleave also fire for every child element

  const show = (on) => {
    overlay.hidden = !on;
    if (!on) depth = 0;
  };
  const accepting = () => isActive() && !modalOpen();

  document.addEventListener("dragenter", (ev) => {
    if (!fromOutside(ev.dataTransfer)) return;
    ev.preventDefault();
    depth++;
    if (accepting()) show(true);
  });
  document.addEventListener("dragover", (ev) => {
    if (!fromOutside(ev.dataTransfer)) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = accepting() ? "copy" : "none";
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
    if (!accepting()) return;
    try {
      const url = firstUrl(await textOfDrop(ev.dataTransfer));
      if (url) onLink(url);
      else await alertModal(T("mb_error_title"), T("link_unsupported"), "warning");
    } catch (err) {
      console.error("drop failed", err);
    }
  });
}
