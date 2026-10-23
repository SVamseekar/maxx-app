# Maxx

Maxx will turn shopping screenshots into advice and collective buying power.
The core demo implements screenshot → comparable prices → deterministic Money Score →
confirmed product Bloc → maximum-price commitment → streamed negotiation → allocation
or failed outcome. With `PAYPAL_MODE=simulator` or `sandbox`, joining places a PayPal hold,
winners are charged only their winning price, everyone else is released, and sellers are paid
out; an agent can also check out a cheaper offer, and PYUSD can pay for it. See
[payments](docs/payments.md) for what is real, what is simulated and how to run it.

Live mode calls Nebius and Tavily from FastAPI; missing keys produce an explicit
error. Use `SCAN_MODE=fixture make api` to try the supplied synthetic samples with
clearly labelled replay results. The default is `SCAN_MODE=live`.

People sign up by emailed link or with Google, Apple, Microsoft or GitHub, secure the account with
a passkey or authenticator app, and join Blocs as themselves; see
[accounts and sign-in](docs/accounts.md) and [security](docs/security.md).

Sellers apply, confirm their payout email, pass an identity check and OFAC sanctions screening,
then publish standing offers or list products nobody has asked for yet, negotiated by fixed rules
or a bounded AI agent. Winning buyers give a delivery address; sellers ship with a tracking number
that is checked against the carrier's format and followed with the carrier, and are paid when the
parcel is delivered (at the first scan once trusted). Unshipped orders are refunded, and buyers and
sellers get in-app and email notifications. Tracking and identity run in labelled simulators until
EasyPost and Stripe keys are set. Maxx is the marketplace platform, not the seller: it does not
ship or handle goods. Every feature is listed at `/features`, and `/judge` has a four-minute seller
tour. See [marketplace](docs/marketplace.md),
[market and compliance research](docs/market-research.md), [performance](docs/performance.md), and
the 15 policy pages under `/legal`.

See [your configuration checklist](docs/operator-actions.md),
[provider verification evidence](docs/provider-verification.md), and
[scan verification measurements](docs/scan-verification.md).

## Stack

- Node.js 22.13+ LTS recommended (`.nvmrc`); Python 3.12; npm and uv.
- Next.js **16.3.8**, React **19.3.0**, TypeScript **5.9.3**, Tailwind **4.3.3**.
- FastAPI **0.142.2**, Pydantic **2.13.5**, SQLAlchemy **2.0.54**,
  Psycopg **3.3.6**, Alembic **1.20.0** (Python packages resolved in `uv.lock`).
- Docker Compose uses Postgres 17; an isolated native Postgres 15+ is also supported.
- npm dependencies are pinned with `package-lock.json`; Python is locked with
  `services/api/uv.lock`. Install with `npm ci` and `uv sync --locked`.

The planning docs proposed Next.js 15. The foundation uses a patched Next.js 16
release because the npm audit reported advisories in the 15 stack. React and
TypeScript satisfy the installed framework's peer requirements. ESLint 10 uses
TypeScript and React Hooks rules; Next's lint preset was excluded because its
transitive `braces` dependency has an unpatched advisory. Dev/build use the
supported Webpack mode because Turbopack's worker port binding failed in this
environment. See the official
[Next.js installation guide](https://nextjs.org/docs/app/getting-started/installation),
[Next.js 16 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-16), and
[Tailwind Next.js guide](https://tailwindcss.com/docs/installation/framework-guides/nextjs).

## Layout

```text
apps/web/           Scan/verdict, Blocs, negotiation room, streaming server-side proxy
services/api/       Typed scan, deterministic auction, injectable agents, durable events, audit logging
scripts/            live connection smoke check, optional native Postgres helper
docs/               foundation verification record
compose.yaml        localhost-only Postgres with a persistent Docker volume
.env.example        local configuration and optional future credential placeholders
```

## Local setup

Install Node.js 22, Python 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and either Docker Desktop with Compose or native PostgreSQL. macOS/Linux commands
below assume Bash and `make`. Docker Desktop must be running for the Docker path.

From the project folder:

```bash
cd /Users/souravamseekarmarti/Projects/hackathons-2026/maxx
cp .env.example .env           # only on first setup; do not overwrite your own keys
make setup                    # npm ci + uv sync --locked
make db                       # start Postgres; wait for it to be healthy
make migrate                  # create application/cache/job/event/audit tables
```

If Docker is unavailable, use native Postgres **instead of** `make db`:

```bash
# macOS with Homebrew's postgresql@15 already installed:
export PATH="$(brew --prefix postgresql@15)/bin:$PATH"
make db-native
make migrate
```

The native helper creates a new isolated cluster in ignored `.local/postgres`,
listening only on `127.0.0.1:55432`. It uses the defaults in `.env.example` and does
not alter an existing system database. It also works with other installed Postgres
versions if `initdb`, `pg_ctl`, `createdb`, and `psql` are on PATH. Run either the
Docker DB or the native DB, since both use port 55432. If using your own database,
set `DATABASE_URL` and skip both DB helpers. Use a Psycopg SQLAlchemy URL such as
`postgresql+psycopg://user:password@host:5432/database?sslmode=require` for Neon;
URL-encode special characters in usernames/passwords.

Run in **two separate terminals** from the `maxx/` directory:

```bash
# Terminal 1
make api
```

```bash
# Terminal 2
make web
```

Open [localhost:3001](http://localhost:3001). The page opens the screenshot scan flow. Select the sample or upload an image,
then choose **Get my verdict**. API docs: [localhost:8000/docs](http://localhost:8000/docs).

In a third terminal:

```bash
cd /Users/souravamseekarmarti/Projects/hackathons-2026/maxx
make smoke        # real HTTP checks, including Next.js → FastAPI → SELECT 1
make check        # frontend lint, typecheck, production build; backend lint + tests
```

Stop the web/API with Ctrl-C. Stop the database with `make db-stop` (Docker) or
`make db-native-stop` (native). Data is retained. Restart using the same DB target.
If running checks while using the frontend, restart `make web` after the production
build, since development and production share `.next/`.

To test production locally, stop `make web`, run `npm run build`, then
`npm run start:web`; keep the API and DB running, and run `make smoke` again.

## Health contract and configuration

- `GET /health`: API liveness, HTTP 200, `{"status":"ok","service":"maxx-api"}`.
- `GET /health/ready`: executes `SELECT 1`; HTTP 200 with `database: "ok"`, or
  HTTP 503 with a safe error when Postgres is unavailable.
- Browser `GET /api/health`: Next.js calls API readiness over HTTP. It returns
  HTTP 503 on database failure, network failure, bad upstream response, or timeout.
- No cross-origin browser request is needed. `API_BASE_URL` is server-only.
- Both services read the root `.env`; shell environment variables take precedence.
  Restart services after changing configuration. `.env` is ignored by Git.
- Local DB credentials: **user `maxx`, password `maxx_local`, database `maxx`,
  host `127.0.0.1`, port `55432`**. These are disposable localhost defaults.
- Default frontend port: 3001; API: 8000. When changing ports, also update
  `API_BASE_URL`, and use `SMOKE_API_URL` / `SMOKE_WEB_URL` for the smoke checker.
- Alembic manages all application, demand, cache, job, event and audit tables.
  Runtime requires migrated Postgres; it never falls back to a local database.

## Live configuration

All pending configuration and verification actions are maintained only in
[docs/operator-actions.md](docs/operator-actions.md). Live scan requires Nebius
and Tavily; live negotiation requires Nebius. Model IDs remain provisional until
the authenticated probes pass. Keep keys server-side. PayPal is deferred.

## Project context and license

Built from the active `../README.md`, `../_shared/`, and
`../nebius-nvidia-hackathon/` planning files. `_archive-v1/` was excluded.
This is a new, local Git repository on branch `main`; no remote or deployment
is configured. MIT licensed; see `LICENSE`.

## Core demo

Start the API with `SCAN_MODE=fixture NEGOTIATION_MODE=fixture make api`.
Select the sample screenshot, get its verdict, confirm its exact product/variant,
create a Bloc, join with your maximum and choose **Close Bloc & negotiate**.
[Blocs](http://localhost:3001/blocs) also provides success, no-deal and withdrawal
scenarios seeded with 800 buyers total. Reset restores only those three scenarios.
All commitments, sellers and stock are simulated; fixture offers are explicitly
labelled. Live Nebius adapters remain available via `NEGOTIATION_MODE=live`.

Bloc state, jobs, events, demand signals, six-hour Tavily cache and model-call
metadata persist in Postgres through the single `DATABASE_URL`. Run one API worker;
process locks do not coordinate multiple workers. Local Postgres restart/replay is
verified; hosted persistence/SSE remain unverified. Screenshots are processed in RAM
and discarded after synchronous scanning. No paid application disk is needed.
The demo uses the fixed identity `demo-you`; production authentication is deferred.

See [test audit](docs/test-audit.md), [core verification](docs/nebius-core-verification.md)
and the [sole operator checklist](docs/operator-actions.md).

## Judge path and evaluation

Open `/judge`, reset the scenarios, enter as `demo-you`, close a ready Bloc, watch
its stream and inspect `/under-the-hood`. Repeat with failure or withdrawal.
Alternatively scan the sample, follow its Bloc link, use **Find matching product**
and confirm an uncertain exact model/variant before joining. Matching uses 50 demo
identities; the live adapter uses Nebius embeddings with hard variant exclusions.

With fixture API/web running (`PAYPAL_MODE=off`, the core demo) and an administrator account from `make dev-account` exported as
`MAXX_EVAL_EMAIL` and `MAXX_EVAL_PASSWORD`, `make evaluate` writes `evals/core-fixture.json`.
Measured local results: 25/25 replayed fields on five synthetic images; 50/50
automatic identity matches on 60 synthetic cases, ten requiring confirmation;
zero invariant violations in 200 random auctions, including 188 partial fills.
These are fixture/rule consistency results, not measured live-model accuracy.
`make evaluate-live` writes a separate live report only with all modes live and
working credentials; otherwise it reports unverified and exits 2.

[PRD audit](docs/nebius-prd-audit.md) lists remaining requirements. Deployment files
are prepared in `deploy/` and `render.yaml`; nothing is published. All required
operator setup/verification is in the single checklist.

The [8 October checkpoint review](docs/checkpoint-review.md) records the starting
file inventory, the expired-Bloc and closing-reserve fixes, 64 backend / 7 frontend tests, fresh local
Postgres and fixture restart/replay evidence, and the provider-verification handoff.
