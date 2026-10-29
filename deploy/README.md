# Prepared deployment configuration

Nothing is published. Locked Dockerfiles run a production Next server and one
FastAPI worker; secrets/local databases are excluded from builds. Web never
receives provider keys. API startup migrates Postgres before accepting traffic.

Compose persists only Postgres's volume. The single DATABASE_URL stores all
application state, jobs, normalized events, cache and model-call metadata.
Screenshots are processed in RAM without retention; no API disk is required.
Hosting: the web app on Vercel, the API on Render's free plan (`render.yaml`: one
service, no disk, external Postgres such as Neon, readiness health check, automatic
deploys off). A free instance stops after 15 idle minutes and takes about a minute
to start; page requests wake it in the background and pages show a banner until it
answers. Countdown timers pause while it sleeps and resume from Postgres on wake.

Public judge/reset endpoints and fixed demo identity are intentional demo choices.
One API instance/worker is required. SSE must remain unbuffered. Docker execution
and hosted persistence/SSE are unverified; Compose syntax passes. Design:
[`storage-and-deployment.md`](../docs/storage-and-deployment.md).
All operator setup, commands and expected results are solely in
[`operator-actions.md`](../docs/operator-actions.md).
