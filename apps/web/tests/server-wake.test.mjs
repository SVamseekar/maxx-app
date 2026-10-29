import assert from "node:assert/strict";
import test from "node:test";
import { nextWakeState, wakeDue, WAKE_GAP_MS, WAKE_GIVE_UP_MS } from "../app/lib/server-wake.ts";

test("a healthy answer is ready at once, however long the wait was", () => {
  assert.equal(nextWakeState(true, 0), "ready");
  assert.equal(nextWakeState(true, WAKE_GIVE_UP_MS + 1), "ready");
});

test("a quick miss stays quiet, a longer one shows the banner, and a very long one gives up", () => {
  assert.equal(nextWakeState(false, 500), "checking");
  assert.equal(nextWakeState(false, 5_000), "waking");
  assert.equal(nextWakeState(false, WAKE_GIVE_UP_MS), "stuck");
});

test("page requests send one wake request per gap", () => {
  assert.equal(wakeDue(1_000_000, 0), true);
  assert.equal(wakeDue(1_000_000, 1_000_000 - WAKE_GAP_MS + 1), false);
  assert.equal(wakeDue(1_000_000, 1_000_000 - WAKE_GAP_MS), true);
});
