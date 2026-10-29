import assert from "node:assert/strict";
import test from "node:test";
import { callSummary } from "../app/lib/call-summary.ts";

const call = (provider, model, cost_usd = null) => ({ provider, model, cost_usd });

test("a live negotiation names its Nemotron models, count and cost", () => {
  const calls = [
    call("nebius", null),
    ...Array.from({ length: 3 }, () => call("nebius", "nvidia/Nemotron-3-Ultra-550b-a55b", "0.0021")),
    ...Array.from({ length: 5 }, () => call("nebius", "nvidia/nemotron-3-super-120b-a12b", "0.0004")),
    call("tavily", null),
  ];
  assert.equal(
    callSummary(calls),
    "8 Nemotron calls on Nebius Token Factory (nemotron-3-super-120b-a12b ×5, Nemotron-3-Ultra-550b-a55b ×3) · 1 Tavily search · about $0.008",
  );
});

test("a replay says it made no model calls", () => {
  assert.equal(callSummary([]), "No model calls");
  assert.equal(callSummary([call("tavily", null), call("tavily", null)]), "2 Tavily searches, no model calls");
});
