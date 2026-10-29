# Persistence and deployment review

Runtime uses only `DATABASE_URL`, a migrated Postgres Psycopg URL. SQLite is
supported by the store solely for isolated tests and read-only legacy import.
There is no runtime fallback to SQLite or application filesystem storage.

| Data | Durable location | Restart behavior |
|---|---|---|
| Private Bloc/member/seller state | Postgres `bloc_documents`, CAS revision | Preserved; public views exclude floors, personas and private state |
| Confirmed demand | `demand_signals` | Preserved |
| Price evidence | `price_cache`, six-hour deadline | Preserved but never reused at/after expiry; identity includes variant, quantity, currency and retail/history purpose |
| Negotiation work | `negotiation_jobs` | Queued jobs atomically claimed; running jobs interrupted by process restart fail and release all simulated commitments |
| Public events | `negotiation_events` keyed by Bloc/generation/event | Append-only within generation, written with snapshot/job transaction; SSE replays from durable cursor; seeded reset replaces that seed's generation/history |
| Model-call metadata | `model_calls` | Preserved; API returns latest 200 allowlisted records. No prompts, API keys, screenshots or private seller inputs |
| Screenshot / scan result | RAM during synchronous request / browser state | Upload not retained; user rescans after reload. Images aren't queued. Synthetic repository fixtures are public demo assets |

One API instance and one Uvicorn worker are required: in-process locks coordinate
reset/start, and restart recovery assumes exclusive ownership. This is a deliberate
demo limitation, not a horizontally scalable lease-based worker implementation.
The dispatcher retries transient database errors. Persisted close deadlines are
processed when the worker is running; an asleep host processes overdue Blocs on
wake. An interrupted scan must be retried. No real merchant orders or money move.

Uploaded images require no persistent storage in this synchronous flow. If retained
uploads or asynchronous scans are added, use private S3-compatible object storage
(e.g. R2/S3), random keys, short-lived signed access, MIME/size validation, and
lifecycle deletion within seven days. Never use public buckets or the Render local
filesystem. That future feature needs its own configuration and retention tests;
it is not implemented here. Provider-side screenshot retention needs live account
verification separately.

`deploy/compose.yaml` persists only Postgres's Docker volume. API containers run
Alembic before Uvicorn and fail startup if migration fails. `render.yaml` prepares
the free API service and an external Postgres secret; it has no paid disk or
provisioned database. The web app runs on Vercel.

Render free services stop after 15 minutes without inbound traffic, take about a
minute to start on the next request, and use ephemeral filesystems; free Render
Postgres expires after 30 days. Use an external durable Postgres account, such as
Neon, rather than treating an expiring database as durable hosting. There is no
keep-alive pinger (Render discourages them): `apps/web/proxy.ts` sends a background
wake request on page requests, and `ServerWakeBanner` tells the visitor while the API
starts and holds back actions that need it.
[Render free-service constraints](https://render.com/docs/free),
[Render blueprint reference](https://render.com/docs/blueprint-spec).

No paid application disk or image bucket is unavoidable for this milestone. Free
hosting remains conditional on account allowances, two-service usage, storage,
bandwidth and outbound traffic; it cannot guarantee continuous countdown execution.
Always-on compute requires a suitable paid host, and external database usage beyond
free allowances may cost money. Live Nebius/Tavily calls require credits or billing.
The configured model cost is an estimate from observed input/output tokens and
operator-supplied dated per-million rates; it excludes Tavily charges, hosting,
storage and account-specific discounts. Missing usage/rates remain unmeasured.
No dollar amount or $0 operating guarantee is inferred from fixtures.
