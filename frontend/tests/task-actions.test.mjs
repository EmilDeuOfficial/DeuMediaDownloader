import test from "node:test";
import assert from "node:assert/strict";
import { actionsFor } from "../js/task-actions.js";

test("waiting and running tasks can be paused and cancelled", () => {
  for (const status of ["QUEUED", "SEARCHING", "DOWNLOADING"]) {
    assert.deepEqual(actionsFor(status), { toggle: "pause", cancel: true, disabled: false }, status);
  }
});

test("a paused task offers resume and cancel", () => {
  assert.deepEqual(actionsFor("PAUSED"), { toggle: "resume", cancel: true, disabled: false });
});

test("buttons are disabled while ffmpeg converts or embeds", () => {
  for (const status of ["CONVERTING", "EMBEDDING"]) {
    assert.equal(actionsFor(status).disabled, true, status);
  }
});

test("a recording can be cancelled but not paused", () => {
  assert.deepEqual(actionsFor("RECORDING", false), { toggle: null, cancel: true, disabled: false });
  assert.deepEqual(actionsFor("RECORDING"), { toggle: "pause", cancel: true, disabled: false });
  assert.equal(actionsFor("CONVERTING", false).toggle, null);
});

test("finished tasks show no buttons", () => {
  for (const status of ["DONE", "ERROR", "CANCELLED", "SOMETHING_NEW"]) {
    assert.equal(actionsFor(status), null, status);
  }
});
