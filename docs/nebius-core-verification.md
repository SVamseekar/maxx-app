# Nebius core local verification

2026-10-05. Production Next.js :3001, FastAPI :8000, **actual local Postgres**
:55432. All three provider modes fixture, fixture round pacing 0.4 seconds.
No provider calls or real money. Live benchmarks remain **UNVERIFIED**.

This pass checked the active PRD/spec before implementing: six-hour Tavily cache,
historical/deal median Bloc target and demand reasoning; open-Bloc score bonus;
persisted countdown/committed totals; eight private personas; dated model cost
arithmetic; unified Postgres state/jobs/events/audit and disk-free deployment.

62 backend tests passed (22 unit, 40 integration), seven frontend tests passed.
Ruff check/format, ESLint, TypeScript and production build passed. Property suites
cover 400 allocation examples and 200 seller-context isolation cases. Buyer-context
spies verify that private floor/stock/persona data never reaches the buyer agent.
Cache tests cover the exact six-hour boundary, refetch, purpose/variant isolation,
reopened storage and mutation isolation. Scoring tests require lower/fresh/open
matching targets. Cost transport test verifies $0.00450000 from synthetic usage and
synthetic dated rates; this is arithmetic evidence, not current provider pricing.

`make migrate` created all application tables. Legacy import preserved five Blocs
and one demand record, source files untouched. `make verify-persistence` against
actual Postgres returned `status=verified`: queued_job_restart,
running_job_recovery, event_replay, cache_expiry and metadata_restart passed.
Interrupted RUNNING jobs release commitments; queued mode changes fail safely.
The API was stopped/restarted, then the browser reloaded the previous terminal
success: 451 allocated / 150 unserved, own $144.00 ≤ $150.00 maximum, three price
history rows and persisted event transcript. `make smoke` passed actual DB
readiness and web-to-API-to-Postgres. Its stale foundation-page assertion was fixed.

Last `make evaluate` writes separate fixture evidence in `evals/core-fixture.json`
and `evals/core-fixture-negotiations.json`:

| Metric | Observed | Limit |
|---|---|---|
| Extraction | 25/25 fields, 5 synthetic images | Replay consistency, not model accuracy |
| Upload-to-verdict p50 | 16.25 ms, one run/image | Local fixture plumbing |
| Matching | 50/50 automatic matches over 60 cases; 10 confirmations | Synthetic rules, not calibrated live precision |
| Auction invariants | 0 violations / 200 random auctions; 188 partial fills | Pure deterministic engine |
| Seed reset | 98.55 ms, one run | Local HTTP/Postgres |

| Streamed scenario | Allocated / unserved | Close-to-stream-complete ms | First event ms |
|---|---|---|---|
| Success | 451 / 150 | 1860.67 | 344.74 |
| Failure | 0 / 101 | 1361.24 | 41.48 |
| Withdrawal | 77 / 24 | 1526.40 | 43.57 |

Each streamed run used zero providers. These are individual timings, not latency
percentiles or PRD performance targets. Three price rows reflect closing in round
four using round-three offers. Different deterministic concession personas changed
allocation totals compared with the previous milestone.

Browser evidence this pass: reset → success entry rendered 601 buyers, $99,150.00
HELD commitments, $150.00 reference median, 451/601 affordability, simulated source
links and a decrementing countdown. Post-restart history was verified before reset.
The room fits a 360px viewport. Under-the-hood labels fixture modes and unmeasured
costs when no real usage/rates exist. Existing full scan/matching/failed-outcome
browser evidence is retained in earlier verification artifacts; no live token data
is fabricated. Current captures: `completion-mobile.png`.

Compose syntax validation passes. Container execution remains UNVERIFIED because
Docker's daemon is stopped. Render blueprint now has free API/web, external
Postgres, migration-before-start, auto deploy off and no disk. No deployment,
account creation, hosting expenditure or PayPal work occurred. Free sleep delays
countdown execution until wake; always-on compute/allowance excess and provider
usage can cost money. Uploaded images are synchronous RAM-only, so retained object
storage isn't required for this milestone.

Live provider IDs/image/tools, source quality, current rates, 40-image/50-run
benchmarks, hosted SSE/durability and backups remain UNVERIFIED. See PRD audit,
storage review and the sole operator checklist for exact outstanding actions.

## 8 October checkpoint re-verification

The reviewed implementation now passes 64 backend tests (22 unit, 42 integration)
and seven frontend tests, ESLint/TypeScript, production build and Ruff lint/format.
Two confirmed bugs were corrected: catalogue creation no longer reuses an
OPEN Bloc whose deadline has passed, and closing re-clears retained offers under
a changed reserve. Both new tests failed before the fix and pass afterward;
existing expired state remains preserved. Independent read-only review confirmed
the reserve fix; a minor watching-room stale-totals issue after another client's
leave is documented in the handoff.

Fresh actual Postgres probe passed all five restart/cache/event/metadata checks.
Final production HTTP smoke and fixture evaluation passed again: 25/25 scan fields,
50/50 automatic matches over 60 cases, zero violations over 200 auctions (188
partial). Final streamed success/failure/withdrawal allocated 451/0/77 buyers;
durations 1694.97/1538.16/1516.51 ms, zero provider calls. Three terminal snapshots
were identical after stopping/restarting the API, and query/header cursors replayed
the expected events through Next.js. Safe results: `evals/review-restart.json`.

Browser checked restart settlement, judge reset/join/close/success, no-deal releases
and fixture transparency. Captures: `review-restart.jpg`, `review-judge.jpg`.
No new 360px sweep, container execution or hosted backup is claimed. Starting
inventory, review scope, checkpoint and provider handoff: `checkpoint-review.md`.
