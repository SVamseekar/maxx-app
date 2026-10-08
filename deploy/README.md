# Prepared deployment configuration

Nothing is published. Locked Dockerfiles run a production Next server and one
FastAPI worker; secrets/local databases are excluded from builds. Web never
receives provider keys. API startup migrates Postgres before accepting traffic.

Compose persists only Postgres's volume. The single DATABASE_URL stores all
application state, jobs, normalized events, cache and model-call metadata.
Screenshots are processed in RAM without retention; no API disk is required.
Render blueprint prepares two free services, no disk, external Postgres secrets,
readiness health check and automatic deploys disabled. Free sleep can delay the
countdown worker until wake. Always-on compute and allowance excess may cost money.

Public judge/reset endpoints and fixed demo identity are intentional demo choices.
One API instance/worker is required. SSE must remain unbuffered. Docker execution
and hosted persistence/SSE are unverified; Compose syntax passes. Design:
[`storage-and-deployment.md`](../docs/storage-and-deployment.md).
All operator setup, commands and expected results are solely in
[`operator-actions.md`](../docs/operator-actions.md).
