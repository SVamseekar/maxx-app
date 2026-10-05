# Foundation milestone — 5 October 2026

Scope: local Next.js/TypeScript/Tailwind, FastAPI, Postgres configuration, MIT
license, environment template, setup tooling, and health connection only.
No product features, model calls, payments, publication, or pushes.

## Verified

- `npm ci`: clean lockfile installation.
- `npm audit`: zero vulnerabilities across runtime and development dependencies.
- `make check`: frontend ESLint, TypeScript, production build; Python Ruff lint,
  formatting, and 3 passing API tests.
- `docker compose config --quiet`: Compose validates. Docker daemon was stopped,
  so a container was not started in this environment.
- Native PostgreSQL **15.15**: isolated cluster at `.local/postgres`, password
  authentication, loopback port 55432; Alembic connection verified with
  `make migrate`. Compose is configured for Postgres 17.
- Production HTTP smoke: `/health`, `/health/ready`, frontend `/api/health`, and
  the frontend page all return HTTP 200. Readiness executes a real `SELECT 1`.
- Browser: automatic check shows `Connected · API healthy · Postgres ready`.
- Failure check: stop native DB; `node scripts/smoke.mjs --expect-unavailable`
  confirms API liveness stays HTTP 200 while API readiness and Next.js proxy
  return HTTP 503. Browser's Check again displays unavailable status.
- Recovery: restart native DB and rerun the smoke checker and browser retry.
- Development command `make web` starts the Next.js page successfully.
- `.env`, `.local/`, dependencies, build outputs, and Python caches are ignored.
- Local Git repository on `main`; no Git remote configured.

## Dependency decisions

Planning docs proposed Next.js 15. Its current patch still pulled in an affected
PostCSS version, so this foundation uses Next.js 16.3.8 and compatible React 19.3.
Next's ESLint preset pulled in an unpatched `braces` advisory and its React plugin
failed on ESLint 10. We use ESLint 10.12 with TypeScript ESLint and React Hooks
rules; all their installed peer ranges support ESLint 10. The root pins the same
ESLint version so npm does not hoist an older peer.

Next dev/build use supported Webpack mode. Turbopack's worker failed to bind a
local port in this environment, including on retry with process permissions.

The new Starlette test client uses `httpx2`, avoiding its older httpx deprecation.
Python resolution is recorded in `services/api/uv.lock`; frontend versions are
pinned in the workspace package and `package-lock.json`.

## Remaining external validation

The Nebius model IDs in `.env.example` are provisional from the planning docs.
They require an account API key and `/v1/models` verification in the next
milestone. No third-party keys are needed to run the foundation.
