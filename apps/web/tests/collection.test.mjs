import { test } from "node:test";
import assert from "node:assert/strict";
import { matchesQuery } from "../app/lib/collection.ts";

test("a buyer can find the model despite case, accents and pasted whitespace", () => {
  assert.equal(matchesQuery("Sony WH-1000XM5 · Café edition", "  SONY  cafe  "), true);
  assert.equal(matchesQuery("Sony WH-1000XM4 Black", "sony xm5"), false);
});
test("resetting search restores every item and payment IDs remain searchable", () => {
  assert.equal(matchesQuery("", "   "), true);
  assert.equal(matchesQuery("Headphones ORDER-123 CAPTURED", "order-123"), true);
  assert.equal(matchesQuery("Headphones ORDER-123 CAPTURED", "order-456"), false);
});
