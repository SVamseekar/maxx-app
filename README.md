# Maxx

Maxx will turn shopping screenshots into advice and collective buying power.
This milestone contains **only the application foundation**: Next.js + TypeScript +
Tailwind, FastAPI, Postgres connectivity, and local tooling. Scanning, model calls,
Blocs, auth, payments, seeds, and deployment are future milestones.

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
apps/web/           Next.js App Router, health page, server-side API proxy
services/api/       FastAPI, typed settings, DB engine, Alembic, health tests
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
make migrate                  # verify Alembic connection; no product tables yet
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

Open [localhost:3000](http://localhost:3000). The page automatically checks the
connection and should display **Connected · API healthy · Postgres ready**.
Use **Check again** to retry. API docs: [localhost:8000/docs](http://localhost:8000/docs).

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
- Default frontend port: 3000; API: 8000. When changing ports, also update
  `API_BASE_URL`, and use `SMOKE_API_URL` / `SMOKE_WEB_URL` for the smoke checker.
- Alembic is configured with empty application metadata. No product schema has
  been invented yet. Future migrations belong in `services/api/alembic/versions/`.

## Credentials needed next

**No external credentials are required for this milestone.** For the next AI
integration milestone, obtain these and put them only in your ignored `.env`:

1. **Nebius Token Factory API key** → `NEBIUS_API_KEY`, with credits enabled.
   Keep `NEBIUS_BASE_URL` as the Token Factory endpoint. Confirm the available
   model IDs using `/v1/models`; the `MODEL_*` entries are provisional values from
   the planning docs, not verified with your account.
2. **Tavily API key** → `TAVILY_API_KEY`, for live search/extract in the scan flow.
3. **Neon Postgres connection string** → `DATABASE_URL` when moving to hosted
   Postgres. Local development can continue with the provided local database.

For the later PayPal spike, obtain a **sandbox app client ID and secret**
(`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`), sandbox business/seller and personal
buyer accounts, and later a webhook registration ID (`PAYPAL_WEBHOOK_ID`). Keep
`PAYPAL_ENV=sandbox`. None of these integrations is implemented here.
Render/GitHub accounts are only needed when you authorize hosting/publication.
Never put API keys, DB URLs, or PayPal secrets in a `NEXT_PUBLIC_*` variable.

## Project context and license

Built from the active `../README.md`, `../_shared/`, and
`../nebius-nvidia-hackathon/` planning files. `_archive-v1/` was excluded.
This is a new, local Git repository on branch `main`; no remote or deployment
is configured. MIT licensed; see `LICENSE`.
