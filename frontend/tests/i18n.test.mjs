import test from "node:test";
import assert from "node:assert/strict";
import { setStrings, T } from "../js/i18n.js";

test("returns the string for a known key", () => {
  setStrings({ hello: "Hallo" });
  assert.equal(T("hello"), "Hallo");
});

test("returns the key for an unknown key", () => {
  setStrings({});
  assert.equal(T("missing_key"), "missing_key");
});

test("fills {} placeholders in order", () => {
  setStrings({ q: "Queued {} track(s)  [{}]" });
  assert.equal(T("q", 3, "MP3"), "Queued 3 track(s)  [MP3]");
});

test("leaves named braces and missing args untouched", () => {
  setStrings({ d: "Placeholders: {artist}, {title}", m: "a {} b {}" });
  assert.equal(T("d"), "Placeholders: {artist}, {title}");
  assert.equal(T("m", "x"), "a x b {}");
});

test("does not resolve inherited object keys", () => {
  setStrings({});
  assert.equal(T("constructor"), "constructor");
});
