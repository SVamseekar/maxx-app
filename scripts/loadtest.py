"""A small load test for the public read paths. Usage:

    uv --directory services/api run python ../../scripts/loadtest.py http://127.0.0.1:8000 200 20

Arguments: base URL, total requests per endpoint, concurrency. It measures latency percentiles and
errors for the routes a crowd of visitors hits: the Bloc list, one Bloc (with and without an ETag),
and the public configuration. It sends no writes.
"""

import asyncio
import statistics
import sys
import time

import httpx2 as httpx


async def hammer(client, path, total, concurrency, headers=None):
    latencies, errors = [], 0
    gate = asyncio.Semaphore(concurrency)

    async def one():
        nonlocal errors
        async with gate:
            started = time.perf_counter()
            try:
                response = await client.get(path, headers=headers)
                if response.status_code >= 500:
                    errors += 1
            except httpx.HTTPError:
                errors += 1
            latencies.append((time.perf_counter() - started) * 1000)

    began = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(total)))
    elapsed = time.perf_counter() - began
    latencies.sort()
    pick = lambda q: latencies[min(len(latencies) - 1, int(len(latencies) * q))]  # noqa: E731
    return {
        "path": path,
        "rps": round(total / elapsed),
        "p50_ms": round(statistics.median(latencies)),
        "p95_ms": round(pick(0.95)),
        "p99_ms": round(pick(0.99)),
        "errors": errors,
    }


async def main(base, total, concurrency):
    async with httpx.AsyncClient(base_url=base, timeout=30, limits=httpx.Limits(max_connections=concurrency)) as client:
        probe = await client.get("/blocs/demo-success")
        etag = probe.headers.get("etag", "")
        for path, headers in (
            ("/blocs", None),
            ("/blocs/demo-success", None),
            ("/blocs/demo-success", {"if-none-match": etag}),
            ("/money/config", None),
            ("/health", None),
        ):
            row = await hammer(client, path, total, concurrency, headers)
            tag = " (If-None-Match)" if headers else ""
            print(f"{row['path'] + tag:<40} {row['rps']:>5} req/s  p50 {row['p50_ms']:>4} ms  p95 {row['p95_ms']:>4} ms  p99 {row['p99_ms']:>4} ms  errors {row['errors']}")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    asyncio.run(main(base, int(sys.argv[2]) if len(sys.argv) > 2 else 200, int(sys.argv[3]) if len(sys.argv) > 3 else 20))
