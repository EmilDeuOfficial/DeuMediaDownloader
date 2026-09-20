import test from "node:test";
import assert from "node:assert/strict";
import { findSelection, initialSelection, resolveQuality, qualityText } from "../js/formats.js";

const groups = [
  { format: "MP3", qualities: [
    { label: "320 kbps", name: "MP3 (320 kbps)" },
    { label: "256 kbps", name: "MP3 (256 kbps)" },
    { label: "192 kbps", name: "MP3 (192 kbps)" },
  ] },
  { format: "FLAC", qualities: [{ label: "Lossless", name: "FLAC (Lossless)" }] },
  { format: "MKV", qualities: [
    { label: "Best", name: "MKV (Best)", label_key: "quality_best" },
    { label: "720p", name: "MKV (720p)" },
  ] },
];

test("findSelection maps a flat name to format and quality", () => {
  const sel = findSelection(groups, "MP3 (256 kbps)");
  assert.equal(sel.group.format, "MP3");
  assert.equal(sel.quality.label, "256 kbps");
});

test("findSelection returns null for an unknown name", () => {
  assert.equal(findSelection(groups, "MP3 (128 kbps)"), null);
  assert.equal(findSelection(groups, undefined), null);
});

test("initialSelection prefers the saved name", () => {
  assert.equal(initialSelection(groups, "MKV (720p)", "MP3 (320 kbps)").quality.name, "MKV (720p)");
});

test("initialSelection falls back to the default when the saved format was removed", () => {
  assert.equal(initialSelection(groups, "MP3 (128 kbps)", "MP3 (320 kbps)").quality.name, "MP3 (320 kbps)");
});

test("initialSelection falls back to the first entry when even the default is unknown", () => {
  assert.equal(initialSelection(groups, "nope", "nope too").quality.name, "MP3 (320 kbps)");
});

test("resolveQuality keeps the wanted quality when the new format offers it", () => {
  assert.equal(resolveQuality(groups[0], "192 kbps").name, "MP3 (192 kbps)");
});

test("resolveQuality picks the first (best) quality when it does not", () => {
  assert.equal(resolveQuality(groups[0], "720p").name, "MP3 (320 kbps)");
  assert.equal(resolveQuality(groups[1], "320 kbps").name, "FLAC (Lossless)");
});

test("qualityText translates Best and leaves other labels alone", () => {
  const T = (key) => ({ quality_best: "Beste" })[key] || key;
  assert.equal(qualityText(groups[2].qualities[0], T), "Beste");
  assert.equal(qualityText(groups[2].qualities[1], T), "720p");
});
