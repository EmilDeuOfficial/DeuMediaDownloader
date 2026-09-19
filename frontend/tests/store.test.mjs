import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../js/store.js";

test("get returns initial state", () => {
  const s = createStore({ a: 1 });
  assert.deepEqual(s.get(), { a: 1 });
});

test("set merges a patch and notifies subscribers", () => {
  const s = createStore({ a: 1, b: 2 });
  const seen = [];
  s.subscribe((st) => seen.push(st));
  s.set({ b: 3 });
  assert.deepEqual(s.get(), { a: 1, b: 3 });
  assert.deepEqual(seen, [{ a: 1, b: 3 }]);
});

test("unsubscribe stops notifications", () => {
  const s = createStore();
  let n = 0;
  const off = s.subscribe(() => n++);
  s.set({ x: 1 });
  off();
  s.set({ x: 2 });
  assert.equal(n, 1);
});

test("state objects are replaced, not mutated", () => {
  const s = createStore({ a: 1 });
  const before = s.get();
  s.set({ a: 2 });
  assert.equal(before.a, 1);
});
