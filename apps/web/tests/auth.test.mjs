import assert from "node:assert/strict";
import test from "node:test";
import { describeAgent, initials, loginPath, oauthErrorMessage, passwordChecks, passwordStrength, relativeTime, safeNext } from "../app/lib/auth-helpers.ts";

test("only same-site relative paths are followed after sign-in", () => {
  assert.equal(safeNext("/blocs/abc/room?x=1"), "/blocs/abc/room?x=1");
  for (const bad of ["//evil.com", "https://evil.com", "/\\evil.com", "javascript:alert(1)", "", null, undefined, "/a\u0000b", "/" + "a".repeat(400)]) assert.equal(safeNext(bad), "/");
  assert.equal(safeNext("nope", "/blocs"), "/blocs");
  assert.equal(loginPath("//evil.com"), "/login?next=%2F");
  assert.equal(loginPath("/account"), "/login?next=%2Faccount");
});

test("OAuth error codes become readable messages and unknown codes stay generic", () => {
  assert.match(oauthErrorMessage("oauth_denied"), /cancelled/);
  assert.match(oauthErrorMessage("who-knows"), /Something went wrong/);
  assert.equal(oauthErrorMessage(null), null);
});

test("password guidance reflects the server rules and strength grows with length and variety", () => {
  assert.equal(passwordChecks("short").find(c => c.id === "length").ok, false);
  assert.ok(passwordChecks("a perfectly fine passphrase").every(c => c.ok));
  assert.equal(passwordChecks("buyername", "buyername@example.com").find(c => c.id === "email").ok, false);
  assert.equal(passwordChecks("aaaaaaaaaaaa").find(c => c.id === "variety").ok, false);
  assert.equal(passwordStrength(""), 0);
  assert.equal(passwordStrength("abc"), 1);
  assert.ok(passwordStrength("abcdefghij") < passwordStrength("a perfectly fine passphrase"));
  assert.equal(passwordStrength("Correct-Horse-Battery-Staple-9"), 4);
});

test("display helpers are forgiving", () => {
  assert.equal(initials("Nova Q Lee"), "NL");
  assert.equal(initials("  gina "), "G");
  assert.equal(initials(""), "?");
  assert.equal(describeAgent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"), "Chrome on macOS");
  assert.equal(describeAgent(""), "Unknown device");
  assert.equal(relativeTime(1000, 1030), "just now");
  assert.equal(relativeTime(1000, 1000 + 7200), "2 h ago");
});

import { b64uToBuffer, bufferToB64u, creationOptions, passkeyErrorMessage, requestOptions } from "../app/lib/webauthn.ts";
import { hostOf, safeHref, safeLocation } from "../app/lib/safe-url.ts";

test("base64url conversion round-trips arbitrary bytes and survives missing padding", () => {
  const bytes = new Uint8Array([0, 1, 2, 250, 251, 252, 253, 254, 255, 62, 63]);
  const text = bufferToB64u(bytes);
  assert.match(text, /^[A-Za-z0-9_-]+$/);
  assert.deepEqual([...new Uint8Array(b64uToBuffer(text))], [...bytes]);
  assert.equal(bufferToB64u(new Uint8Array([251, 255]).buffer), "-_8");
  assert.equal(bufferToB64u(new TextEncoder().encode("hello")), "aGVsbG8");
});

test("server WebAuthn JSON becomes browser buffers without losing fields", () => {
  const creation = creationOptions({ challenge: "AQID", rp: { id: "localhost", name: "Maxx" }, user: { id: "BAUG", name: "a@b.co", displayName: "A" }, pubKeyCredParams: [{ type: "public-key", alg: -7 }], excludeCredentials: [{ id: "BwgJ", type: "public-key" }], authenticatorSelection: { residentKey: "required", userVerification: "required" } });
  assert.deepEqual([...new Uint8Array(creation.challenge)], [1, 2, 3]);
  assert.deepEqual([...new Uint8Array(creation.user.id)], [4, 5, 6]);
  assert.deepEqual([...new Uint8Array(creation.excludeCredentials[0].id)], [7, 8, 9]);
  assert.equal(creation.authenticatorSelection.userVerification, "required");
  const request = requestOptions({ challenge: "AQID", rpId: "localhost", userVerification: "required" });
  assert.deepEqual([...new Uint8Array(request.challenge)], [1, 2, 3]);
  assert.equal(request.allowCredentials, undefined);
});

test("cancelled passkey prompts are silent and real failures are readable", () => {
  assert.equal(passkeyErrorMessage({ name: "NotAllowedError" }), null);
  assert.equal(passkeyErrorMessage({ name: "AbortError" }), null);
  assert.match(passkeyErrorMessage({ name: "InvalidStateError" }), /already has a passkey/);
  assert.match(passkeyErrorMessage(new Error("boom")), /Something went wrong/);
});

test("only plain web links from provider data are ever rendered as links", () => {
  assert.equal(safeHref("https://shop.example/p?x=1"), "https://shop.example/p?x=1");
  for (const bad of ["javascript:alert(1)", "data:text/html,x", "ftp://x.test", "not a url", "", null, undefined]) assert.equal(safeHref(bad), null);
  assert.equal(hostOf("https://shop.example/p"), "shop.example");
  assert.equal(hostOf("nonsense"), "source");
});

test("redirects the account service asks for are only our paths or https providers", () => {
  assert.equal(safeLocation("/account?linked=google"), "/account?linked=google");
  assert.equal(safeLocation("https://accounts.google.com/o/oauth2/v2/auth?x=1"), "https://accounts.google.com/o/oauth2/v2/auth?x=1");
  assert.equal(safeLocation("//evil.example"), null);
  assert.equal(safeLocation("/\\evil.example"), null);
  assert.equal(safeLocation("javascript:alert(1)"), null);
  assert.equal(safeLocation("http://evil.example/x"), null);
  assert.equal(safeLocation("http://localhost:9099/authorize"), "http://localhost:9099/authorize");
});
