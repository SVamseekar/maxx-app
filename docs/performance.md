# Performance under traffic

## What was wrong

A load test of the public read paths (`scripts/loadtest.py`, 300 requests, 30 concurrent, single dev process) found:

| Path | Before | After |
|---|---|---|
| `GET /blocs/{id}` for a 601-buyer Bloc | **21 req/s, p50 1,438 ms, p95 2,161 ms** | ~1,500 req/s, p50 23 ms, p95 28 ms |
| `GET /blocs` (browse list) | 715 req/s (and it returned every member of every Bloc) | ~1,700 req/s, a few KB instead of hundreds |
| Repeat poll with `If-None-Match` | not available | ~1,500 req/s, 304 with no body, no document read |

Other hot spots found by reading the code: every open live stream re-read and re-parsed the whole Bloc five times a second; the worker's one-second tick loaded every Bloc three times; account pages scanned every Bloc.

## What changed

- **Index columns on `bloc_documents`** (migration 0009): generation, status, product key, close time, owner, title, prices, buyer count, committed total, participants and seller codes are stored beside the document and kept in step on every write. Lists, polling, ETags, the worker and "my Blocs" no longer parse documents.
- **Light list.** `GET /blocs` returns a summary (no members, events or market rows) and is cached for about a second (`LIST_CACHE_SECONDS`).
- **Cached serialised room views.** A Bloc view is built once per revision and shared by everyone who is not a member; members get the same bytes with their own rows marked "me". The cache is bounded (64 entries).
- **ETag / `If-None-Match`** on `GET /blocs/{id}`, tagged with generation, revision and viewer. An unchanged room costs one tiny indexed query.
- **Streams poll cheaply.** Server-sent events read only the latest event id and status (two small queries, every 0.5 s) and fetch events only when something changed.
- **Worker.** Finds Blocs to close, negotiate or settle by indexed queries and payment tables, not by loading all Blocs. Slower housekeeping (shipping deadlines, payouts, purges) runs every 20 seconds.
- **Database pool** sized by `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`.
- **Front end:** the footer is rendered once in the layout, not per page; explanatory and policy pages are server components with no client JavaScript beyond the shared shell.

## Running the test

```bash
uv --directory services/api run python ../../scripts/loadtest.py http://127.0.0.1:8000 600 50
```

It sends no writes. `tests/test_performance.py` guards the properties that matter: the list is an order of magnitude smaller than a room, an unchanged room is a 304 that never reads the document, and index queries never select it.

## Known limits

- One API process. Rate limits and stream caps are per process; run more than one worker only after moving them to a shared store such as Redis.
- Pages render per request because the Content-Security-Policy carries a per-request nonce. Put a CDN in front for assets (they are fingerprinted and cacheable); HTML must stay uncached.
- The seller "opportunities" view loads open Blocs with their members to compute a demand curve. It is a low-traffic page, but a large catalogue should precompute the curve into the index columns.
- The numbers above are from a laptop dev server, not a production load test. Measure on the real deployment before launch.
