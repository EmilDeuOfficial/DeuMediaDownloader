// Helpers for the format + quality dropdowns.
//
// `groups` comes from the backend: [{format: "MP3", qualities: [{label, name, label_key?}]}].
// `name` is the flat name the downloaders and the config use ("MP3 (320 kbps)").

/** Group and quality for a flat name, or null when the name is unknown (for example removed). */
export function findSelection(groups, name) {
  for (const group of groups) {
    const quality = group.qualities.find((q) => q.name === name);
    if (quality) return { group, quality };
  }
  return null;
}

/** Saved name if it still exists, else the fallback name, else the very first entry. */
export function initialSelection(groups, savedName, fallbackName) {
  return findSelection(groups, savedName) || findSelection(groups, fallbackName) || { group: groups[0], quality: groups[0].qualities[0] };
}

/** After a format change: keep the wanted quality label when the new format has it, else the best (first). */
export function resolveQuality(group, wantedLabel) {
  return group.qualities.find((q) => q.label === wantedLabel) || group.qualities[0];
}

/** Text shown for a quality; "Best" is translated. */
export function qualityText(quality, T) {
  return quality.label_key ? T(quality.label_key) : quality.label;
}
