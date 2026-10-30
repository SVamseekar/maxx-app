# Deployment

The public demo at **https://maxx.souravamseekar.com** runs entirely on free plans:

| Part | Where | Notes |
|---|---|---|
| Web (Next.js) | Vercel, Hobby plan | Server-side proxy to the API; the browser never talks to the API directly and never sees a provider key. |
| API (FastAPI) | Render, free plan, Docker (`deploy/Dockerfile.api`) | One service, one worker, no disk. Settings in [`render.yaml`](../render.yaml). |
| Database | Neon Postgres, free plan | The single `DATABASE_URL`; the API migrates it with Alembic before it accepts traffic. |
| AI | Nebius Token Factory | Nemotron 3.5 Super VL, Nemotron 3.5 Lightning, Nemotron 3 Super, Nemotron 3 Ultra, Qwen3 embeddings. |
| Web search | Tavily | Search and Extract, called from the API only. |
| Email | Brevo SMTP relay on port 2525 | Render's free plan blocks outbound ports 25, 465 and 587. |

## What the free plans mean for visitors

- **Cold start.** A free Render instance stops after 15 idle minutes and takes about a minute to
  start. Every page request sends one background wake request, and pages show a banner with a
  progress bar until the API answers. Buttons that need the API wait and say "Waking server…".
  Nothing pings the API to keep it awake.
- **Timers.** A Bloc's countdown is stored in Postgres. While the API sleeps no deadline fires; on
  wake the worker closes anything that is due.
- **Streaming.** Negotiation rounds stream over server-sent events through a Vercel function
  (300-second limit). A negotiation is capped at 90 seconds, and a dropped stream resumes from its
  last event (`Last-Event-ID`).

## State

All durable state lives in Postgres through one `DATABASE_URL`: Blocs, members, jobs, the event
journal, the money ledger, the six-hour price cache, demand signals and model-call metadata (model
id, tokens, latency, cost; never prompts, images or keys). Screenshots are processed in memory and
discarded. Run exactly one API worker (`WEB_CONCURRENCY=1`): rate limits and the job runner are
in-process. Back up the database with Neon's point-in-time restore or `pg_dump`, and test a restore
before relying on it.

## Production settings

The API refuses to start in `ENVIRONMENT=production` unless these are safe:

- `SECRET_KEY` set; `ALLOWED_HOSTS` is the API's own host name, not `*`.
- `PUBLIC_BASE_URL` is the web app's `https://` address (cookies, links in emails, OAuth).
- `EMAIL_MODE=smtp` with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`.
- The local development database password is rejected.

Also set:

- `NEBIUS_API_KEY`, `TAVILY_API_KEY`; `SCAN_MODE`, `MATCH_MODE`, `NEGOTIATION_MODE` = `live`.
- `JUDGE_ACCESS_CODE` (12+ characters) to turn on one-tap judge entry at `/judge`.
- `PROXY_CLIENT_IP_SECRET` (32+ characters), the **same value on Vercel and Render**. The web app
  sends the visitor's address to the API signed with it; without it every visitor shares one
  allowance.
- The AI spending caps (`AI_BUDGET_USD`, `AI_DAILY_BUDGET_USD` and the per-person, per-address and
  per-negotiation caps) and Tavily credit caps (`TAVILY_DAILY_CREDITS`, `TAVILY_MONTHLY_CREDITS`).
  See [AI guardrails](ai-guardrails.md) and `.env.example`.

On Vercel set `API_BASE_URL` (the Render URL), `PUBLIC_BASE_URL`, `PAYPAL_MODE` and
`PROXY_CLIENT_IP_SECRET`, with the project's root directory set to `apps/web`.

## Deploying

1. Create a Neon project and copy its connection string as
   `postgresql+psycopg://…?sslmode=require`.
2. Create the Render service from `render.yaml` (or with the same settings) and fill the
   `sync: false` values. Automatic deploys are off: deploy a commit on purpose.
3. Check `https://<api>/health/ready` returns `{"status":"ok","database":"ok"}`.
4. Deploy `apps/web` to Vercel with the variables above and attach the domain.
5. Open `/judge`, enter the code, run **Try successful deal**, and confirm the room streams rounds
   and **Under the hood** lists Nemotron calls with their cost.

## Docker

`deploy/compose.yaml` runs Postgres, the API and the web app locally with the same Dockerfiles.
Only Postgres has a volume. Builds exclude `.env`, local databases and caches.
