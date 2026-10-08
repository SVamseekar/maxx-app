# Maxx next chat sessions

Reviewed 8 October 2026. Project: `/Users/souravamseekarmarti/Projects/hackathons-2026/maxx`.

## Current position

The local Nebius core is implemented: screenshot scan/verdict, matching and confirmation,
Blocs and simulated holds, deterministic allocation, eight simulated seller personas,
negotiation/SSE replay, judge scenarios, Tavily cache/target reasoning, score bonus,
cost metadata and unified Postgres persistence. It is a fixture-verified demo;
live providers and hosted behavior are not verified. The existing live evaluation
artifact reports `unverified` and an incomplete evaluation.

Session 1 completed on 8 October: starting inventory captured, core reviewed and
expired-Bloc reuse and changed-reserve close defects fixed with tests that failed
before the fixes. All static checks, production build, 64 backend tests (22 unit / 42 integration) and
7 frontend tests passed. The backend suite uses mocks and isolated SQLite stores.
Fresh actual Postgres persistence probe, production HTTP/SSE fixture evaluation
and exact three-scenario API-restart snapshot/cursor replay also passed. Browser
judge success/no-deal and fixture transparency were rechecked. The minor watching
room stale-totals issue after another client's leave is recorded for Session 4;
server persistence is correct. These results do not verify providers or hosted behavior.

The reviewed implementation is checkpointed locally on `main`; exact commit and
remaining gaps are recorded in `checkpoint-review.md`. Secrets, caches and local
databases are excluded. Review-created services were stopped and database files
retained. The parent planning folder is not a Git repository; `maxx/` is the
application repository. Nothing was pushed, published or sent to paid providers;
PayPal remains deferred. Proceed to Session 2 below. Both provider keys are absent;
configure server-only credentials, available credits and bounded-run authorization
before any actual provider calls.

The daily build plan is a schedule, not a completion checklist. Its checkmarks
mean “must ship that day.” Use `nebius-prd-audit.md` for actual implementation
status and `operator-actions.md` as the sole operational checklist.

## Session 1 — protect and validate the current milestone

Model: GPT-6.1 Sol, High. Start here.

Paste into a new chat in this project:

> Work in maxx/. Read docs/nebius-prd-audit.md, docs/operator-actions.md and the active Nebius PRD. Complete these five related tasks: (1) inventory the current modified/untracked implementation and identify missing or accidental files; (2) review the core diff for material correctness, privacy and persistence issues, preserving existing work; (3) rerun the local static checks, tests and production build, fixing only confirmed regressions; (4) check the existing fixture judge path and restart/replay evidence, rerunning relevant checks when services are available; (5) create a local Git checkpoint of the reviewed implementation, excluding secrets, caches and local databases, and record the commit and remaining gaps. Do not push, publish, call paid providers or start PayPal. Read any applicable AGENTS.md before edits. Stop with a concrete handoff for provider verification.

Done when: reviewed work is recoverable in Git, relevant checks pass, and gaps are explicit.

## Session 2 — verify real providers and costs

Model: GPT-6.1 Sol, High. Requires server-side credentials and available credits.

> Continue from docs/next-chat-sessions.md and follow docs/operator-actions.md. Complete these six related tasks: (1) verify authenticated Nebius model IDs and actual screenshot image support; (2) verify live embeddings and strict product/variant exclusions; (3) verify seller JSON and negotiator tool calling with floor/stock clamps; (4) verify real Tavily Search/Extract, comparable-price quality and cache behavior; (5) configure dated, sourced model rates and validate a sample cost estimate against usage; (6) check provider screenshot-retention policy and update the provider evidence and PRD audit. Keep keys server-side and out of logs/chat. Keep fixture and live results separate. Use bounded probes within available credits, and ask for a spending ceiling before any open-ended run or new charge. If credentials are absent, finish all independent preparation and report the exact missing setup without claiming live verification. Do not publish or start PayPal.

Done when: live capabilities have recorded evidence, or each blocked capability has a precise reason.

## Session 3 — representative evaluations and targeted fixes

Model: GPT-6 Astra, High for diagnosis across conflicting results; GPT-6.1 Sol, High is the balanced alternative.

> Use the verified provider configuration from Session 2. Complete these five related tasks: (1) assemble an annotated representative 40-screenshot set with permission to use the images; (2) run extraction and matching evaluations with honest denominators and variant-error analysis; (3) run the planned 50 multi-round negotiation trials and the large-Bloc performance scenario within an agreed provider-credit ceiling; (4) fix the highest-impact measured failures without changing deterministic numeric rules or exposing private seller state, then rerun affected cases; (5) report real accuracy, precision, savings, p50/p95 latency, token/cost estimates and remaining limitations, updating the PRD audit and README. Never count fixtures as live quality evidence. Do not publish or start PayPal.

Done when: representative evidence supports the demo claims, with failures and limits disclosed.

## Session 4 — judge experience and deployment readiness

Model: GPT-6.1 Sol, High. Follow Sessions 1–3; UI review can begin while provider setup is pending.

> Complete these six related tasks: (1) verify the full scan → confirmation → Bloc → room → outcome path at desktop and 360px widths; (2) improve confirmed loading/error/empty/source-link issues and test success, no-deal and withdrawal scenarios; (3) verify Docker image build/start, migration and API restart persistence; (4) prepare external Postgres connectivity and disposable backup/restore verification when credentials exist; (5) review hosting configuration, single-worker constraints, SSE proxy behavior, cold starts and countdown delays, explaining concrete costs; (6) reconcile the PRD's uniform-price summary with the accepted-seller-price algorithm and record the chosen behavior consistently in the demo/docs. Keep scope focused on the existing demo. Prepare a reviewable deployment handoff; publication still needs explicit authorization. Do not start PayPal.

Done when: the judge journey works and the deployment package has executable evidence and explicit hosting gaps.

## Session 5 — Nebius submission package

Model: GPT-6.1 Sol, Medium; High if reviewing technical compliance.

> Complete these five related tasks: (1) check the current official Nebius hackathon rules/deadline and entry requirements; (2) rewrite the Devpost draft using only implemented and measured claims; (3) update the under-three-minute video script and judge walkthrough around the working success/failure paths; (4) finish README setup, model/Tavily disclosures, simulated-seller/hold disclosures, feedback-form preparation and the compliance checklist; (5) verify all supplied repository/demo/video links and prepare the final submission handoff. If a public demo or video does not exist, mark its link pending rather than inventing it. Do not upload, publish or submit without explicit authorization. Leave PayPal for a later phase.

Done when: submission assets are ready for review and every missing external action is listed.

## Working order and model rationale

Run sessions sequentially when they edit the same checkout. Each session contains
five or six connected tasks and ends at a milestone; avoid creating one chat per
tiny fix. Begin each with the previous handoff and finish by refreshing this file's
current-position summary plus the audit/checklist as appropriate.

These model/effort choices are project recommendations, not a measured model
comparison. Official OpenAI guidance positions GPT-6.1 Sol for complex technical
work and Astra for demanding work needing broad context; keep the lightest setting
that meets the quality bar. Source:
https://developers.openai.com/api/docs/guides/model-selection
