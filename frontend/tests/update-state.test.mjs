import test from "node:test";
import assert from "node:assert/strict";
import { parseNotes, inlineSegments, formatSize, createUpdates } from "../js/update-state.js";

const plain = (block) => block.segments.map((s) => s.text).join("");

test("release notes become titles, headings, items and text", () => {
  const blocks = parseNotes("## Release v7.3\n\n### Neu\n- erstens\n* zweitens\n\nEin Absatz");
  assert.deepEqual(
    blocks.map((b) => [b.type, plain(b)]),
    [
      ["title", "Release v7.3"],
      ["heading", "Neu"],
      ["item", "erstens"],
      ["item", "zweitens"],
      ["text", "Ein Absatz"],
    ],
  );
});

test("windows line endings are handled", () => {
  const blocks = parseNotes("### Fix\r\n- eins\r\n- zwei\r\n");
  assert.equal(blocks.length, 3);
  assert.equal(plain(blocks[2]), "zwei");
});

test("tables and rules are dropped, and so are headings left without content", () => {
  const blocks = parseNotes("### Neu\n- etwas\n\n### Download\n| Datei | Beschreibung |\n|---|---|\n| Setup | Installer |\n---\n");
  assert.deepEqual(blocks.map((b) => [b.type, plain(b)]), [["heading", "Neu"], ["item", "etwas"]]);
});

test("empty and missing notes give no blocks", () => {
  assert.deepEqual(parseNotes(""), []);
  assert.deepEqual(parseNotes(null), []);
  assert.deepEqual(parseNotes("### Nur eine Ueberschrift"), []);
});

test("bold parts are marked, links keep their label, code loses its backticks", () => {
  assert.deepEqual(inlineSegments("**yt-dlp** aktualisiert sich [selbst](https://x.test) mit `Pruefsumme`"), [
    { text: "yt-dlp", bold: true },
    { text: " aktualisiert sich selbst mit Pruefsumme", bold: false },
  ]);
});

test("markup is never turned into HTML: tags stay plain text", () => {
  const [block] = parseNotes("- <img src=x onerror=alert(1)>");
  assert.equal(plain(block), "<img src=x onerror=alert(1)>");
});

test("download size in MB", () => {
  assert.equal(formatSize(0, "en"), "");
  assert.equal(formatSize(50634244, "en"), "48 MB");
  assert.equal(formatSize(5 * 1024 * 1024 + 300000, "en"), "5.3 MB");
  assert.equal(formatSize(50634244, "de"), "48 MB");
});

function fakeApi(result) {
  return {
    calls: 0,
    check_app_update() {
      this.calls++;
      return typeof result === "function" ? result() : Promise.resolve(result);
    },
  };
}

test("a newer release sets the phase to available", async () => {
  const api = fakeApi({ available: true, version: "7.3", current: "7.2", notes: "x" });
  const updates = createUpdates(api);
  assert.equal(updates.store.get().phase, "idle");
  const pending = updates.check();
  assert.equal(updates.store.get().phase, "checking");
  await pending;
  assert.equal(updates.store.get().phase, "available");
  assert.equal(updates.store.get().info.version, "7.3");
  assert.equal(updates.isAvailable(), true);
});

test("no newer release sets the phase to current", async () => {
  const updates = createUpdates(fakeApi({ available: false, version: "7.2", current: "7.2" }));
  await updates.check();
  assert.equal(updates.store.get().phase, "current");
  assert.equal(updates.isAvailable(), false);
});

test("a failed check shows the error, a failed quiet check shows nothing", async () => {
  const failing = () => Promise.reject(new Error("Keine Verbindung"));
  const loud = createUpdates(fakeApi(failing));
  await loud.check();
  assert.deepEqual([loud.store.get().phase, loud.store.get().error], ["error", "Keine Verbindung"]);

  const quiet = createUpdates(fakeApi(failing));
  await quiet.check({ quiet: true });
  assert.deepEqual([quiet.store.get().phase, quiet.store.get().error], ["idle", ""]);
});

test("a check that is already running is not started twice", async () => {
  const api = fakeApi({ available: false, version: "7.2", current: "7.2" });
  const updates = createUpdates(api);
  await Promise.all([updates.check(), updates.check()]);
  assert.equal(api.calls, 1);
  await updates.check();
  assert.equal(api.calls, 2);
});
