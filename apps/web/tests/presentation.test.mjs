import assert from "node:assert/strict";
import test from "node:test";
// Missing implementation yields an ordinary assertion failure during the first red run.
const presentation = await import("../app/presentation.ts").catch(() => ({}));

test("price comparison excludes unknown shipping, different variants and unconfirmed stock", () => {
  assert.equal(typeof presentation.priceComparison, "function");
  const result = presentation.priceComparison("349.99", "USD", [
    { price: "299.99", shipping: "0", same_item: true, in_stock: true },
    { price: "250", shipping: null, same_item: true, in_stock: true },
    { price: "100", shipping: "0", same_item: false, in_stock: true },
    { price: "200", shipping: "0", same_item: true, in_stock: false },
    { price: "290", shipping: "20", same_item: true, in_stock: true },
  ]);
  assert.deepEqual(result, { best: 299.99, difference: 50, trustedCount: 2 });
});

test("unsupported currency and absent evidence cannot display fabricated savings", () => {
  assert.equal(typeof presentation.priceComparison, "function");
  const row = { price: "299.99", shipping: "0", same_item: true, in_stock: true };
  assert.equal(presentation.priceComparison("349.99", "EUR", [row]), null);
  assert.equal(presentation.priceComparison(null, "USD", [row]), null);
  assert.equal(presentation.priceComparison("349.99", "USD", []), null);
});

test("a higher comparable price preserves the negative difference rather than inventing savings", () => {
  assert.equal(typeof presentation.priceComparison, "function");
  assert.deepEqual(presentation.priceComparison("100", "USD", [
    { price: "120", shipping: "5", same_item: true, in_stock: true },
  ]), { best: 125, difference: -25, trustedCount: 1 });
});

test("withdrawn sellers disappear from latest offers even when their older offers remain in history", () => {
  assert.equal(typeof presentation.latestOffers, "function");
  assert.deepEqual(presentation.latestOffers([
    { type: "seller_offer", data: { seller: "A", price: "140", qty: 2, round: 1 } },
    { type: "seller_offer", data: { seller: "B", price: "150", qty: 3, round: 1 } },
    { type: "seller_offer", data: { seller: "B", price: "135", qty: 3, round: 2 } },
    { type: "seller_withdrew", data: { seller: "A", round: 2 } },
  ]), [{ seller: "B", price: "135", qty: 3, round: 2 }]);
});

test("another buyer leaving triggers a fresh snapshot of room totals", () => {
  assert.equal(typeof presentation.needsRoomSnapshot, "function");
  assert.equal(presentation.needsRoomSnapshot("commitment_released"), true);
  assert.equal(presentation.needsRoomSnapshot("member_joined"), true);
  assert.equal(presentation.needsRoomSnapshot("cleared"), true);
  assert.equal(presentation.needsRoomSnapshot("seller_offer"), false);
});
