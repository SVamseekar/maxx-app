import assert from "node:assert/strict";
const api = process.env.SMOKE_API_URL ?? "http://127.0.0.1:8000";
const web = process.env.SMOKE_WEB_URL ?? "http://127.0.0.1:3000";
const unavailable = process.argv.includes("--expect-unavailable");
for (const [url, readiness] of [[`${api}/health`, false], [`${api}/health/ready`, true], [`${web}/api/health`, true]]) {
  const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
  assert.equal(response.status, unavailable && readiness ? 503 : 200, `${url}: unexpected HTTP status`);
  const body = await response.json();
  assert.equal(body.status, unavailable && readiness ? "unavailable" : "ok");
  if (!readiness) assert.equal(body.service, "maxx-api");
  if (readiness && !unavailable) {
    assert.equal(body.service, "maxx-api");
    assert.equal(body.database, "ok");
  }
  console.log(`PASS ${url}`, body);
}
const page = await fetch(web);
assert.equal(page.status, 200);
assert.match(await page.text(), /Ready to build/);
console.log(unavailable ? "PASS database outage propagates while API liveness stays healthy" : "PASS frontend page, API, Postgres, and frontend → API → Postgres connection");
