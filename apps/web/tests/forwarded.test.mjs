import assert from "node:assert/strict";
import test from "node:test";
import { addressHeaders, clientAddress } from "../app/lib/forwarded.ts";

test("only the address the platform proxy appended is forwarded", () => {
  assert.equal(clientAddress(new Headers({ "x-forwarded-for": "1.1.1.1, 2.2.2.2, 203.0.113.9" })), "203.0.113.9");
  assert.equal(clientAddress(new Headers({ "x-real-ip": "198.51.100.4" })), "198.51.100.4");
  assert.equal(clientAddress(new Headers()), undefined);
});

test("with the shared secret the web names the browser for the API", () => {
  const browser = new Headers({ "x-forwarded-for": "6.6.6.6, 203.0.113.9" });
  assert.deepEqual(addressHeaders(browser, "s".repeat(40)), {
    "x-forwarded-for": "203.0.113.9",
    "x-maxx-client-ip": "203.0.113.9",
    "x-maxx-proxy-secret": "s".repeat(40),
  });
  assert.deepEqual(addressHeaders(browser, undefined), { "x-forwarded-for": "203.0.113.9" });
  assert.deepEqual(addressHeaders(new Headers(), "s".repeat(40)), {});
});
