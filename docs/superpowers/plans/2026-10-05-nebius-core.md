> Historical plan: persistence decisions below are superseded by the Postgres-only implementation and `docs/storage-and-deployment.md`.

# Nebius core demo implementation plan

Goal: complete a credential-free, clearly labelled scan → confirmed product Bloc →
join/leave → streamed negotiation → success or failed outcome demo, retaining
injectable real Nebius adapters beside fixtures.

Architecture: pure Decimal auction engine; Pydantic Bloc state with optimistic
versioned SQLAlchemy persistence; async provider protocols; durable event journal
and reconnectable SSE; Next.js streaming proxy and typed negotiation UI.

Spec: `../nebius-nvidia-hackathon/01-PRD.md` and `02-tech-spec.md`.

Constraints: USD only, no real money, maximum five rounds, no buyer above their
maximum, no seller beyond stock, private seller state never shared, all live AI
through server-side Nebius. External integrations remain unverified without keys.

Ruling: use explicit C3/tech-spec seller-specific allocation prices rather than
the contradictory uniform-price summary. UI says each buyer pays their seller's
accepted price. If wrong, the auction design needs a separate product decision.
Ruling: no automatic catalogue/embedding match yet. User confirms the exact
product/variant before joining its Bloc; no unmeasured match confidence.
Ruling: default local Bloc persistence is SQLite; `BLOC_DATABASE_URL` can select
Postgres using the same versioned document table. Existing scan audit remains
local SQLite. PostgreSQL and shared-host durability require live verification.
Ruling: continue the already-authorized build inline in the existing workspace;
keep existing uncommitted changes and do not publish or merge.

## Milestone 1: Blocs and deterministic auction

Files: `negotiate/contracts.py`, `engine.py`, `store.py`, `blocs.py`;
`tests/test_auction.py`, `tests/test_blocs.py`.

- [x] Write and run failing tests for priority, price/max/capacity, duplicate IDs,
  empty/no-deal inputs, joins/leaves, transition conflicts and persistent CAS.
- [x] Implement `clear(members, offers) -> Clearing`, `BlocStore`, typed state and
  simulated commitment events. Use immutable seller private fields in server state.
- [x] Run unit/integration tests and 200 generated invariant cases; record results
  and update the sole operator checklist before milestone 2.

## Milestone 2: injectable adapters and negotiation runner

Files: `negotiate/adapters.py`, `runner.py`, fixture personas;
`tests/test_negotiation.py`, `tests/test_adapters.py`.

- [x] Write and run failing tests for bounded retry, private prompts, floor/stock
  clamps, withdrawal/reclear, reserve ceiling, all-failed providers and terminal
  success/no-deal, including event order and conservation of commitments.
- [x] Implement seller/negotiator protocols, explicit fixture adapters and real
  Nebius JSON/tool-calling adapters with metadata logs and timeouts.
- [x] Runner uses a server-owned snapshot, at most five rounds, private aggregate
  seller feedback, journaled events, and terminal release/allocation on every path.
- [x] Run tests and update operator checklist before milestone 3.

## Milestone 3: HTTP/SSE and negotiation room

Files: `negotiate/routes.py`, `stream.py`, `/blocs` browser pages, proxy routes,
`tests/test_bloc_routes.py`, reproducible browser check script and test audit.

- [x] Write failing API tests for join/leave/start/repeat start, SSE replay cursors,
  reset isolation, failed outcomes and recovery of interrupted negotiations.
- [x] Add explicit demo reset/seed, scenario pages, confirmed scan-to-Bloc link,
  streaming room, round price history and per-member outcome with no-money label.
- [x] Run API tests, frontend lint/typecheck/build, browser success/failure/leave/
  reconnect/mobile checks; classify all verification and record measured fixtures.
- [x] Update operator checklist: every action has env variable(s), setup,
  verification command, expected result and blocked feature. Live checks stay open.

Review focus: concurrent membership mutations; repeat start/reset while running;
restart during negotiation; provider malformed/tool responses; disconnected stream
replay. Tests belong to the milestone that implements each behavior.
