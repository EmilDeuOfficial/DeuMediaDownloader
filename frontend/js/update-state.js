import { createStore } from "./store.js";

// State and text helpers of the app update (GitHub release check). No DOM in here, so the
// node tests can run it; the dialog is components/update-modal.js.

/** Inline markdown -> [{text, bold}]. Links keep their label, code loses its backticks. */
export function inlineSegments(text) {
  const plain = text
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/<br\s*\/?>/gi, " ");
  const segments = [];
  let bold = false;
  for (const part of plain.split(/\*\*|__/)) {
    if (part) segments.push({ text: part, bold });
    bold = !bold;
  }
  return segments;
}

/**
 * Release notes (GitHub markdown) -> flat list of blocks:
 *   {type: "title" | "heading" | "item" | "text", segments: [{text, bold}]}
 * Tables and rules are dropped (the download table is of no use in the app) and so are
 * headings that end up without any content.
 */
export function parseNotes(markdown) {
  const blocks = [];
  for (const raw of String(markdown || "").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("|") || /^([-*_])\1{2,}$/.test(line)) continue;
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ type: heading[1].length <= 2 ? "title" : "heading", segments: inlineSegments(heading[2]) });
      continue;
    }
    const item = /^[-*+]\s+(.*)$/.exec(line);
    blocks.push({ type: item ? "item" : "text", segments: inlineSegments(item ? item[1] : line) });
  }
  const isHead = (b) => b && (b.type === "title" || b.type === "heading");
  return blocks.filter((block, i) => {
    if (block.type === "title") return blocks.slice(i + 1).some((b) => !isHead(b));
    if (block.type === "heading") return !isHead(blocks[i + 1]) && blocks[i + 1] !== undefined;
    return true;
  });
}

export function formatSize(bytes, locale) {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  const text = new Intl.NumberFormat(locale, { maximumFractionDigits: mb < 10 ? 1 : 0 }).format(mb);
  return `${text} MB`;
}

/**
 * Update state shared by the title bars and the dialog.
 *   phase: "idle" (not checked or the quiet check failed) | "checking" | "available" | "current" | "error"
 *   info:  answer of api.check_app_update ({available, version, current, notes, size, page, ...})
 *   error: message to show in the dialog
 */
export function createUpdates(api) {
  const store = createStore({ phase: "idle", info: null, error: "" });
  let running = null;

  // `quiet`: the check at app start. A failure (no internet) shows nothing at all.
  function check({ quiet = false } = {}) {
    if (running) return running;
    store.set({ phase: "checking", error: "" });
    running = api
      .check_app_update()
      .then((info) => {
        store.set({ phase: info.available ? "available" : "current", info, error: "" });
        return info;
      })
      .catch((err) => {
        store.set(quiet ? { phase: "idle", error: "" } : { phase: "error", error: err.message });
        return null;
      })
      .finally(() => {
        running = null;
      });
    return running;
  }

  return {
    store,
    check,
    isAvailable: () => store.get().phase === "available",
  };
}
