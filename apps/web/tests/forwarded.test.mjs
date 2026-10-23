import assert from "node:assert/strict";
import test from "node:test";
import { clientAddress } from "../app/lib/forwarded.ts";

test("only the address the platform proxy appended is forwarded", () => {
  assert.equal(clientAddress(new Headers({ "x-forwarded-for": "1.1.1.1, 2.2.2.2, 203.0.113.9" })), "203.0.113.9");
  assert.equal(clientAddress(new Headers({ "x-real-ip": "198.51.100.4" })), "198.51.100.4");
  assert.equal(clientAddress(new Headers()), undefined);
});
