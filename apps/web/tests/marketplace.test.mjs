import assert from "node:assert/strict";
import test from "node:test";
const { deadlineText, CASE_KINDS, STATUS_LABEL } = await import("../app/lib/orders.ts");
const { countryName, COUNTRIES } = await import("../app/lib/countries.ts");
const { validationText } = await import("../app/lib/client.ts");

test("deadlines read as plain time left and never hide an overdue one", () => {
  const now = 1_000_000;
  assert.equal(deadlineText(now - 1, now), "now overdue");
  assert.equal(deadlineText(now + 30, now), "in 1 min");
  assert.equal(deadlineText(now + 20 * 60, now), "in 20 min");
  assert.equal(deadlineText(now + 5 * 3600, now), "in 5 h");
  assert.equal(deadlineText(now + 3 * 86400, now), "in 3 days");
});

test("every order state has a label a person can read", () => {
  for (const status of ["AWAITING_ADDRESS", "AWAITING_SHIPMENT", "SHIPPED", "DELIVERED", "CANCELLED", "REFUNDED"]) assert.ok(STATUS_LABEL[status], status);
  assert.ok(CASE_KINDS.not_received && CASE_KINDS.not_as_described && CASE_KINDS.return_request && CASE_KINDS.other);
});

test("country codes map to names and unknown codes are shown as given", () => {
  assert.equal(countryName("GB"), "United Kingdom");
  assert.equal(countryName("ZZ"), "ZZ");
  assert.ok(Object.keys(COUNTRIES).every(code => /^[A-Z]{2}$/.test(code)));
});

test("validation errors from the API are shown as one readable sentence", () => {
  assert.equal(validationText([{ loc: ["body", "support_email"], msg: "Value error, Enter a valid email address." }]), "Support email: Enter a valid email address.");
  assert.equal(validationText([{ loc: ["body", "return_days"], msg: "Input should be greater than or equal to 14" }]), "Return days: Input should be greater than or equal to 14");
  assert.equal(validationText([{ loc: ["body"], msg: "Companies in the EU must give their trade register number." }]), "Companies in the EU must give their trade register number.");
  assert.equal(validationText("nope"), null);
  assert.equal(validationText([]), null);
});
