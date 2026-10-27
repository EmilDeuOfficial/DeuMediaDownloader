// Logic of the "choose what to download" list, kept free of the DOM so it can be tested.

/** Entries whose title contains `text` (ignoring case and surrounding spaces). */
export function filterEntries(entries, text) {
  const needle = String(text || "").trim().toLowerCase();
  if (!needle) return entries;
  return entries.filter((entry) => entry.title.toLowerCase().includes(needle));
}

/** Entries between two positions of the visible list, both ends included (shift-click). */
export function rangeBetween(visible, fromIndex, toIndex) {
  const a = visible.findIndex((entry) => entry.index === fromIndex);
  const b = visible.findIndex((entry) => entry.index === toIndex);
  if (a < 0 || b < 0) return b < 0 ? [] : [visible[b]];
  return visible.slice(Math.min(a, b), Math.max(a, b) + 1);
}

/** Selected positions in list order. */
export function sortedSelection(selected) {
  return [...selected].sort((x, y) => x - y);
}
