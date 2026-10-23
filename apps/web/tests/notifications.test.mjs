import assert from "node:assert/strict";
import test from "node:test";
import { KIND_LABEL, safeLink } from "../app/lib/notifications.ts";

test("only links into the site are followed from a notification", () => {
  for (const ok of ["/orders", "/sell", "/blocs/abc/room", "/notifications", "/account"]) assert.equal(safeLink(ok), ok);
  for (const bad of ["https://evil.example", "//evil.example/orders", "javascript:alert(1)", "/ordersx", "/sellers/S1", "", "/admin"]) assert.equal(safeLink(bad), null);
});

test("every notification kind has a human label", () => {
  for (const label of Object.values(KIND_LABEL)) assert.ok(label.length > 3 && !label.includes("."));
});
