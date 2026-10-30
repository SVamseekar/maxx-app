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
and Tavily; live negotiation requires Nebius. The configured model IDs were checked with live calls
on Token Factory (see [AI guardrails](docs/ai-guardrails.md)). Keep keys
server-side. Payments run in the PayPal simulator unless sandbox keys are set.

## Project context and license

Built from the active `../README.md`, `../_shared/`, and
`../nebius-nvidia-hackathon/` planning files. `_archive-v1/` was excluded.
Source: https://github.com/SVamseekar/maxx-app. MIT licensed; see `LICENSE`.

## Core demo

Live is the default: with `NEBIUS_API_KEY` and `TAVILY_API_KEY` set, `make api` scans with
Nemotron 3.5 Super VL and Lightning plus Tavily, and negotiates with Nemotron 3 Ultra (negotiator)
against seller agents on Nemotron 3 Super, all on Nebius Token Factory. If the day's AI budget
runs out or Token Factory is unreachable, a negotiation runs the deterministic replay instead and
the room says so (`NEGOTIATION_REPLAY_FALLBACK`). `SCAN_MODE=fixture NEGOTIATION_MODE=fixture
MATCH_MODE=fixture make api` runs fully offline on the five synthetic samples (made-up brands).

**Scan price search.** A live scan searches Tavily once with full page text, preferring US
retailers and makers' own stores. Only stores whose pages can be read can confirm stock and
shipping, so when fewer than two stores confirm an offer, a second search asks only those. At most
two pages are read in full with Extract. Code, not the model, decides which offers count: product
pages only, a price quoted from the page, the same brand, model, colour and pack size, new rather
than refurbished or open box, no card-signup or coupon prices, and not on backorder. A score needs
two such stores, or the maker's own store with a warning; otherwise the verdict names the lowest
price it saw. A scan uses 1 to 4 Tavily credits, results are cached for six hours, and daily and
monthly credit caps stop runaway spend. Details: [scan verification](docs/scan-verification.md).
The `/scan` samples replay recorded demo prices even in live mode; its live example (a real
headphones cart) runs the full live pipeline.

[Blocs](http://localhost:3001/blocs) lists three shared demo scenarios: successful deal (600
simulated buyers), no deal and seller withdrawal (100 each), each with eight simulated sellers.
Simulated buyers and sellers are labelled everywhere, place no PayPal holds and are never
charged; only real people's holds count as money. Someone else's finished Bloc leaves the list.

Bloc state, jobs, events, demand signals, six-hour Tavily cache and model-call
metadata persist in Postgres through the single `DATABASE_URL`. Run one API worker;
process locks do not coordinate multiple workers. Screenshots are processed in RAM
and discarded after synchronous scanning. No paid application disk is needed.

See [test audit](docs/test-audit.md), [core verification](docs/nebius-core-verification.md),
the [AI guardrails](docs/ai-guardrails.md) and the [sole operator checklist](docs/operator-actions.md).

## Judge path and evaluation

Set `JUDGE_ACCESS_CODE` (12+ characters) and share it in the judging notes. Open `/judge`
(or `/judge?code=...`) and choose **Enter as a judge**: each judge gets a fresh guest account at
once, with no email or password. Each scenario button opens the judge's own private, unlisted
copy, so judges never share seats and nothing needs a reset. Join with a PayPal hold (simulated),
choose **Close Bloc & negotiate**, and follow the rounds; the conversation stays on screen beside
the outcome. **Start the seller tour** shows the seller side and can be replayed: each start
refunds leftover tour orders quietly and clears strikes the tour caused. `/under-the-hood` lists
every model call with its model id, latency and cost. For a judging window raise the daily AI
budget (see `.env.example`); `AI_BUDGET_USD` still caps the total.

The hosted API runs on a free instance that sleeps after 15 idle minutes. The first visit wakes
it, which takes about a minute: every page shows a banner with a progress bar, and buttons that
need the API wait and say "Waking server…". Open `/judge` first so it is awake by the time you scan.

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
