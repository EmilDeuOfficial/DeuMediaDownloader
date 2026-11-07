import test from "node:test";
import assert from "node:assert/strict";
import { actionsFor, statusText } from "../js/task-actions.js";

test("waiting and running tasks can be paused and cancelled", () => {
  for (const status of ["QUEUED", "SEARCHING", "DOWNLOADING"]) {
    assert.deepEqual(actionsFor(status), { toggle: "pause", cancel: true, disabled: false, cancelDisabled: false }, status);
  }
});

test("a paused task offers resume and cancel", () => {
  assert.deepEqual(actionsFor("PAUSED"), { toggle: "resume", cancel: true, disabled: false, cancelDisabled: false });
});

test("buttons are disabled while ffmpeg converts or embeds", () => {
  for (const status of ["CONVERTING", "EMBEDDING"]) {
    assert.equal(actionsFor(status).disabled, true, status);
  }
});

test("a recording can be cancelled but not paused", () => {
  assert.deepEqual(actionsFor("RECORDING", false), { toggle: null, cancel: true, disabled: false, cancelDisabled: false });
  assert.deepEqual(actionsFor("RECORDING"), { toggle: "pause", cancel: true, disabled: false, cancelDisabled: false });
  assert.equal(actionsFor("CONVERTING", false).toggle, null);
});

test("finished tasks show no buttons", () => {
  for (const status of ["DONE", "ERROR", "CANCELLED", "SOMETHING_NEW"]) {
    assert.equal(actionsFor(status), null, status);
  }
});

test("a conversion can be cancelled, writing the tags cannot", () => {
  assert.equal(actionsFor("CONVERTING").cancelDisabled, false);
  assert.equal(actionsFor("EMBEDDING").cancelDisabled, true);
});

test("running statuses show the progress in percent", () => {
  assert.equal(statusText("Converting…", "CONVERTING", 0.426), "Converting… 42 %");
  assert.equal(statusText("Downloading…", "DOWNLOADING", 1), "Downloading… 100 %");
  assert.equal(statusText("Done", "DONE", 1), "Done");
  assert.equal(statusText("Queued", "QUEUED", 0), "Queued");
});
