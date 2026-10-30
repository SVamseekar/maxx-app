# Deployment files

- `Dockerfile.api`: the FastAPI service (one worker). Startup migrates Postgres before it accepts
  traffic.
- `Dockerfile.web`: a production Next.js server.
- `compose.yaml`: Postgres, API and web together for a local production-like run.

The hosted demo uses Vercel for the web app, Render's free plan for the API (`../render.yaml`) and
Neon Postgres. Setup, required settings and what the free plans mean for visitors are in
[`docs/deployment.md`](../docs/deployment.md).
