# Reviewed Nebius implementation checkpoint

8 October 2026. Work stays local on `main`; no push, publication, provider call,
new charge or PayPal work. Active requirements read from
`../nebius-nvidia-hackathon/01-PRD.md` (Approved for build) and `02-tech-spec.md`.
`apps/web/AGENTS.md` is the only applicable repository AGENTS file found; no web
implementation was edited during this review.

## Inventory and preservation

Starting baseline: `a601d11` (application foundation). The working tree contained
**14 modified tracked files and 99 untracked files**, about 1.38 MB of untracked
content. The exact starting paths are preserved in `review-inventory.json`.

| Area | Original untracked files | Disposition |
|---|---:|---|
| API | 40 | Scan, market/cache, matching, auction/adapters/runner, durable storage, probes, migration and tests retained |
| Web | 22 | Proxies, Bloc/room/judge/transparency flows, state tests, icon and public synthetic samples retained |
| Deployment | 4 | API/web Dockerfiles, local Compose and deployment README retained; runtime remains unverified |
| Docs | 15 | PRD/operator/test/storage/provider reviews, plan and six prior screenshots retained |
| Evals | 16 | Synthetic fixtures/generator, five images, runners and labelled historical reports retained |
| Root | 2 | `.dockerignore` and unpublished Render blueprint retained |

The modified files connect these additions to the foundation: config/main,
Alembic metadata, dependency lock, package scripts, homepage/styles and setup/docs.
The generated `next-env.d.ts` production type paths are intentional build output
already tracked by the foundation. Synthetic images in `evals/screenshots/` and
`apps/web/public/samples/` are intentional copies: all five files, manifest hashes
and public copies match. All required local runtime files were found by build,
tests, migration and fixture execution. The PRD's proposed separate `llm.py`, prompt
files and seller modules are implemented through `providers.py`, `flow.py` and
`negotiate/adapters.py`; their proposed filenames are not missing dependencies.
Planning source documents remain outside this application repository.

Accidental/local artifacts are excluded: `.DS_Store`, root `.env`, `.local/`
(legacy SQLite files, Postgres cluster, logs and temporary restart snapshots),
node_modules, `.next`, virtualenvs, Python/pytest/Ruff/Hypothesis caches and
TypeScript build info. Added explicit Hypothesis and SQLite/DB ignore patterns so
these exclusions also cover files outside `.local/`. No existing application work
was removed. Historical fixture reports remain labelled; `core-live.json` remains
an incomplete **unverified** report, not live evidence.

New review artifacts are this report, the inventory, safe restart results, two
browser captures and refreshed fixture evaluation results.

## Core review and confirmed fixes

Reviewed scan validation/grounding/score, matcher exclusions/confirmation, public
Bloc contracts, seller/buyer contexts and tool screening, deterministic clearing,
runner timeout/release, transaction/CAS/job claim, normalized journal/SSE cursor
replay, cache expiry, cost metadata, proxies and deployment storage configuration.

**P1 — expired OPEN Bloc reused during catalogue creation.** Product matching
returned a matching `OPEN` Bloc even when its persisted close deadline had passed.
Joining then rejected the buyer, trapping subsequent demand in an unusable Bloc
if the worker slept or preflight failed. The new API regression test failed on
reused ID before the fix. Reuse now also checks the deadline, with the existing
zero-deadline legacy behavior preserved. The test passes afterward, exercises a
join into the new Bloc and subsequent reuse, and confirms the expired record is
preserved.

**P2 — closing ignored a changed reserve.** Independent read-only review found
that a plan could lower the reserve and close while the runner finalized its
previous allocation above that reserve. The new test reproduced a $170 reserve /
$140 offers followed by $130 + close: it incorrectly SETTLED before the fix.
Closing now re-clears the retained submitted offers under the closing reserve,
without another seller round. The test passes with FAILED, zero allocations and
all commitments released. Initializing retained offers also handles a first-round
close safely. The independent reviewer checked this fix and found no new material
issue. These are the only two application-code changes made during review.

| Dimension | Assessment within the reviewed demo scope |
|---|---|
| Correctness | Confirmed expiry and closing-reserve defects fixed. Decimal floor/max/stock constraints and terminal commitment conservation covered by tests. Accepted-seller-price allocation follows C3/spec; uniform-price summary conflict remains explicit. |
| Security/privacy | No other material defect found in reviewed public/context paths. Prompts/images/keys excluded from audit fields; floors/stock/personas excluded from buyer contexts and public snapshots. Fixed demo identity and unauthenticated demo controls remain intentional constraints; provider retention is unverified. |
| Persistence | Snapshots, event appends and job changes share a transaction; revisions use CAS and job claim is atomic. Real Postgres probe and process restart/replay passed. Single instance/worker and no hosted backup evidence remain constraints. |
| Performance | Bounded five-round runner, retries and metadata listing reviewed; local timings below are fixture plumbing only. Live 813-buyer performance and host wake delays remain unverified. |
| Maintainability | Existing modules and tests preserved; no refactor or speculative provider changes. Two targeted regression tests added. |

## Fresh verification

The full local check passed: ESLint, TypeScript, seven frontend tests, production
webpack build, Ruff lint/format and **64 backend tests**. Separate category runs
passed **22 unit + 42 integration** tests. These backend suites use isolated SQLite
and mock transports; they make no authenticated provider calls.

Default uv cache access was blocked by the sandbox; a temporary cache resolved it
without changing application code. Native Postgres shared memory and localhost
TCP required approved sandbox escalation. Those restrictions were environmental.
Migration completed against the existing localhost-only Postgres cluster.

The actual Postgres temporary-schema probe passed queued-job restart, atomic
claim, interrupted-job release, normalized event replay, exact six-hour expiry
and metadata restart; its schema was removed. HTTP smoke passed real readiness
and web → API → Postgres. Final fixture evaluation through production Next.js:

| Evidence | Result |
|---|---|
| Scan replay | 25/25 fields over five synthetic screenshots; p50 8.29 ms |
| Matching | 50/50 automatic identities in 60 cases; ten confirmations |
| Random auction invariants | 0 violations in 200 cases; 188 partial allocations |
| Reset | 91.24 ms, one run |
| Streamed success | SETTLED; 451 allocated / 150 unserved; 1694.97 ms |
| Streamed failure | FAILED; 0 / 101; 1538.16 ms; commitments released |
| Streamed withdrawal | SETTLED; 77 / 24; 1516.51 ms; seller A excluded |

All three streamed negotiations used zero providers. Timings are individual local
fixture runs, not representative live latency or quality/cost measurements.
Machine-readable results: `evals/core-fixture.json` and
`evals/core-fixture-negotiations.json`.

Saved all three terminal public snapshots, stopped/restarted the API process and
compared them through the production proxy: exact equality of generation,
revision, member outcomes and full events. Both `after` query and `Last-Event-ID`
replayed the last two events exactly, with no seller-private fields or HELD
commitments. Evidence: `evals/review-restart.json`. This is API-process restart on
local Postgres, not a database failover, container or hosted recovery claim.

Fresh browser checks confirmed settlement after restart, judge reset → one-tap
join → close → incremental negotiation → $144 outcome under the $150 maximum,
451/150 totals, failure with 101 releases, countdown/held totals/target reasoning,
and transparency showing three fixture modes with zero calls. Captures:
`review-restart.jpg`, `review-judge.jpg`. Prior desktop/360px captures are retained;
no new mobile sweep is claimed. Withdrawal was rechecked through HTTP/SSE.

Review-created API/web/Postgres processes were stopped, and temporary browser tab
closed. Database files and custom Blocs are preserved. Initial localhost service
state is restored; the unrelated system Postgres was untouched.

## Checkpoint and provider handoff

Checkpoint commit is recorded after creation below. It includes reviewed source,
tests, lockfiles, migration, synthetic assets, deployment preparation and evidence;
secrets, caches and local databases are excluded.

Both Nebius and Tavily keys are currently absent (presence checked without printing
values). Resume **Session 2** in `next-chat-sessions.md`, using the sole executable
checklist in `operator-actions.md`. Before any actual provider calls, configure
server-only credentials and available credits with explicit authorization for the
bounded verification run. Keep all three modes fixture until their probes pass.

The next operator must verify authenticated exact vision/fast/reason/embed/seller/
negotiator IDs and base64 image input, embedding dimensions/exclusions, seller JSON
and negotiator tools, real Tavily Search/Extract with delivered-price/variant/
stock grounding and cache behavior, dated model rates against observed usage, and
account screenshot-retention policy. Record live evidence separately; failures
must stay unverified with no fixture substitution. Representative 40-image,
50-multi-round and large-Bloc benchmarks follow provider verification with an
agreed spending ceiling.

Minor confirmed UI gap: another client leaving an OPEN Bloc emits a persisted
`commitment_released(reason=left)` event, but a watching room refreshes snapshots
only on join or terminal events. Its member/HELD totals remain stale until refresh
or reconnect. Server state is correct; the promised two-second observer update
needs a focused UI fix in Session 4. No frontend work was expanded in this checkpoint.

Other remaining gaps: custom creations do not emit demand signals; scan-time
demand recording, URL/text scan, exact "$X short" outcome wording, chart/allocation
bar, confidence/persona quality, container execution, hosted SSE/cold starts,
external Postgres backup/restore and uniform-price spec reconciliation. Optional
features and PayPal remain deferred. No push, publishing or new hosting/payment
work is authorized by this checkpoint. Full requirement status remains in
`nebius-prd-audit.md`.
