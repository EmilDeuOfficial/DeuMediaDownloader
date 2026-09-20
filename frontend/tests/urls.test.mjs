import test from "node:test";
import assert from "node:assert/strict";
import { splitUrls } from "../js/urls.js";

const wiki = "https://github.com/o/r/wiki/TikTok-Cookies";

test("text without a URL stays one text part", () => {
  assert.deepEqual(splitUrls("No link here."), [{ type: "text", value: "No link here." }]);
});

test("a URL in the middle is split out", () => {
  assert.deepEqual(splitUrls(`See ${wiki} for help`), [
    { type: "text", value: "See " },
    { type: "url", value: wiki },
    { type: "text", value: " for help" },
  ]);
});

test("sentence punctuation after a URL is not part of it", () => {
  assert.deepEqual(splitUrls(`Tutorial: ${wiki}.`), [
    { type: "text", value: "Tutorial: " },
    { type: "url", value: wiki },
    { type: "text", value: "." },
  ]);
});

test("a URL at the very end and several URLs work", () => {
  const parts = splitUrls(`a ${wiki} b http://x.de/y`);
  assert.deepEqual(parts.filter((p) => p.type === "url").map((p) => p.value), [wiki, "http://x.de/y"]);
});

test("only http and https are recognised", () => {
  assert.equal(splitUrls("javascript:alert(1) file:///c:/x").every((p) => p.type === "text"), true);
});

test("newlines end a URL", () => {
  const parts = splitUrls(`Line one\n\nTutorial: ${wiki}`);
  assert.equal(parts[0].value, "Line one\n\nTutorial: ");
  assert.equal(parts[1].value, wiki);
});
