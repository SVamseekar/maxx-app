# Test audit

Reviewed 2026-10-08. Automated provider transports are mocks; no live provider is verified.

| Category | Evidence | Scope / limitation |
|---|---|---|
| Backend unit | `uv --directory services/api run --locked pytest -m unit -q`: 22 tests | Pure parse/score, target median, cost arithmetic, matching, persona clamps and allocation rules. Hypothesis: two sets of 200 allocation examples and 200 private seller-context isolation examples. Fixtures injected into test setup are isolated SQLite stores, not a runtime fallback. |
| Backend integration | Same command with `-m integration`: 42 tests | In-process HTTP, temporary SQLite transactions/CAS, mock HTTP/tool providers, safe metadata/cost logging, retries/timeouts, cache TTL/refetch/copy isolation, queue/restart/replay, mode-change failure, deadline auto-close, score-to-Bloc and SSE. Added expired catalogue Bloc reuse and changed-reserve close regressions: both failed before their fix and passed afterward. No live Nebius/Tavily or real Postgres in pytest. |
| Actual Postgres integration | `make verify-persistence`: passed | Temporary schema on real local Postgres; independent store/engine restart, queued job dispatch/atomic claim, interrupted release, normalized event replay, exact six-hour expiry, metadata persistence. Not a hosted failover/backup test. |
| Frontend unit | `npm run test --workspace @maxx/web`: 7 tests | SSE/HTTP race ordering, enrichment, revision/reset generations, uncertain/custom confirmation. Not browser tests. |
| Static / production build | Ruff check/format, ESLint, TypeScript, production webpack | Passing compilation/lint; no live quality claim. |
| HTTP system | `make smoke`; `make evaluate` through production Next proxy | Actual local HTTP, real Postgres and incremental SSE. Five fixture scans, 60 synthetic identity cases, 200 random auctions/188 partial, 3 streamed negotiations, zero provider calls. |
| Browser | Previous desktop/360px evidence retained; 8 Oct in-app browser on production web | Fresh post-API-restart settlement reload, judge reset/one-tap entry/close, incremental success and no-deal release, countdown/committed totals, target reasoning and fixture transparency. New captures: `review-restart.jpg`, `review-judge.jpg`. No fresh 360px sweep or CI browser suite claimed. |
| Deployment | Compose syntax check passed; Render configuration reviewed against official schema/docs | Docker daemon stopped: image build/run UNVERIFIED. Hosted readiness/SSE/durability/backup UNVERIFIED; nothing published. |
| Live providers / benchmarks | Probes + `make evaluate-live` | UNVERIFIED: keys missing; provisional models/image/tools/embedding support, real Tavily sources, token costs, representative accuracy/latency not claimed. |

Current full suite: **64 backend + 7 frontend** tests. The fixture evaluator is
separate from unit/integration tests: its 200 random auctions are engine checks,
not 200 model negotiation trials. Mode mismatch fails the live evaluator; it
cannot relabel fixtures as live evidence. Mock audit metadata is isolated from
application records. Actual Postgres verification has no model calls and destroys
only its own temporary schema. Pending actions live only in `operator-actions.md`.
