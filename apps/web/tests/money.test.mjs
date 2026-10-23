import assert from "node:assert/strict";
import test from "node:test";
const { moneyLabel, shortId } = await import("../app/lib/money-format.ts");

test("the interface never lets test money pass for real money", () => {
  assert.equal(moneyLabel(null), "No real payments");
  assert.equal(moneyLabel({ enabled: false, simulated: false }), "No real payments");
  assert.match(moneyLabel({ enabled: true, simulated: true }), /Simulated PayPal/);
  assert.match(moneyLabel({ enabled: true, simulated: false }), /sandbox/i);
});

test("long PayPal ids are shortened at both ends and short ones are kept", () => {
  assert.equal(shortId(null), "—");
  assert.equal(shortId("5O190127TN364715T"), "5O190127TN364715T");
  assert.equal(shortId("0x51cb9435ba7c1f2d3e4a5b6c7d8e9f00112233445566778899aabbccddeeff00"), "0x51cb94…eeff00");
});
