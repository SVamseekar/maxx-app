import assert from "node:assert/strict";
import test from "node:test";
import { mergeSnapshot } from "../app/blocs/state.ts";

test("late HTTP response cannot erase a newer SSE terminal state", () => {
  const current = { revision: 4, status: "SETTLED", events: [{ id: 10 }, { id: 11 }], outcome: { price: "140" } };
  const delayed = { revision: 3, status: "NEGOTIATING", events: [{ id: 10 }], outcome: null };
  assert.equal(mergeSnapshot(current, delayed), current);
});
test("snapshot can enrich streamed terminal events with the saved outcome", () => {
  const current = { revision: 3, status: "SETTLED", events: [{ id: 11 }], outcome: null };
  const saved = { revision: 4, status: "SETTLED", events: [{ id: 11 }], outcome: { price: "140" } };
  assert.equal(mergeSnapshot(current, saved), saved);
});
test("equal cursor still rejects an older revision", () => {
  const current = { revision: 5, events: [{ id: 11 }] };
  assert.equal(mergeSnapshot(current, { revision: 4, events: [{ id: 11 }] }), current);
});
test("demo reset replaces old history and late responses from the old generation are ignored", () => {
  const old = { generation: 10, revision: 50, events: [{ id: 500 }], status: "SETTLED" };
  const reset = { generation: 20, revision: 0, events: [{ id: 1 }], status: "OPEN" };
  assert.equal(mergeSnapshot(old, reset), reset);
  assert.equal(mergeSnapshot(reset, old), reset);
});
