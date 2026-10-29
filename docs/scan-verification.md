# Scan → verdict verification — 5 Oct 2026

Implemented Next.js upload → bounded server proxy → FastAPI image validation →
Nebius vision extraction → NVIDIA normalisation → Tavily Search / conditional
Extract → NVIDIA comparable-listing parsing → grounded price rows → Decimal
Money Score → NVIDIA verdict / deterministic template → source links, corrections,
warnings and per-request call metadata. Blocs and payments are deferred.

Keys remain server-side. PNG/JPG/WebP are decoded and MIME-checked, limited to
8 MB and 16 megapixels. Images are never persisted. Provider timeouts are 20s;
scan/proxy/browser deadlines are 100/105/110s. Invalid structured model responses
receive one repair retry. Live provider errors never silently switch to fixtures.

## Automated checks

15 backend tests passed, including foundation health tests. Ruff lint/format,
frontend ESLint, TypeScript, Next.js production build and Git whitespace checks
passed. Provider HTTP mocks cover image payloads, auth, JSON repair, timeout errors,
Tavily Extract/cache reuse, grounded prices, non-USD exclusions and verdict number
rejection. Audit logs include tokens/latency and exclude keys/images/prompts.
These are contract tests, not evidence of real provider integration success.

The provider probe reports missing keys, account IDs and base64 image support as
unverified; it exits nonzero instead of passing verification.

## Measured screenshot replay

Five synthetic screenshots: headphones, phone, vacuum, unreadable price and EUR.
Three runs each: **15/15 HTTP successes**, **75/75 exact field matches (100%)** for
title, unit price, currency, merchant and quantity. Fields are replayed by exact
image SHA256; this measures fixture consistency, **not extraction accuracy**.

| Mode / build | HTTP p50 | HTTP p90 | Runs |
|---|---:|---:|---:|
| Fixture / development | 11.68 ms | 15.79 ms | 15 |
| Fixture / production | 9.63 ms | 11.07 ms | 15 |

Measured wall-clock HTTP upload through Next.js → FastAPI on localhost, including
image decoding and deterministic scoring, with already-running services. Provider
work is absent in fixture mode. Raw records: `evals/latest-results.json` and
`evals/production-results.json`.

**Live extraction accuracy, live latency, match precision and scan cost remain
unmeasured.** No PRD accuracy, latency, cost or hackathon compliance target is
claimed as achieved. The five-image synthetic pilot is not the planned 40-image
extraction or 60-pair matching benchmark.

## Browser checks

Verified at `http://127.0.0.1:3001`:

- Sample upload → score 75/100 → CHEAPER → $50.00 derived saving.
- Fixture banner and two source links with `target=_blank`, `noopener noreferrer`.
- Score breakdown and per-request transparency details.
- 360px mobile viewport: document width 360px, no horizontal overflow.
- Unreadable price: em dash, no score, WAIT, edit control and warnings.
- Editing/rechecking returns updated details with fixture warnings retained.
- Missing live configuration: actionable error and retry button.
- Final production navigation/scan: no browser console errors. A missing favicon
  found during development was fixed; the expected missing-configuration 503 was
  separately observed and handled.

Screenshots: `docs/scan-mobile.png`, `docs/scan-desktop.png`.

## Remaining operational work

Follow `docs/operator-actions.md` to add real keys, verify exact model IDs and
base64 support, restart in live mode and rerun evaluations. The official provider
sources and their limits are recorded in `docs/provider-verification.md`.

This historical scan milestone is superseded by `nebius-core-verification.md`:
audit, Blocs, demand, cache, jobs and events now use Postgres; the transparency page
and dated cost calculator exist. Live calls/pricing remain unverified. Fixture
links are simulated. URL/text input and optional features/payments remain deferred.

## Web search (30 Oct 2026)

`maxx/price_search.py` follows Tavily's search and extract guidance and the usual price-comparison
matching rules:

- **Query.** Brand, model, variant and title, each word once, plus "price buy new". The search is
  boosted to the United States and leaves out news, finance, reference, review, video, social and
  deal sites. Price trackers are left out of offer searches.
- **Reading pages.** Up to 3 pages are read in full, with an extract query so the chunks sit next to
  the price. Priced pages that do not yet show both stock and shipping come first. Amazon and
  Walmart are never read in full: they answer automated readers with bot checks. Bot-check pages
  are discarded. A slow or failed read falls back to the search snippets.
- **Matching.** Code vetoes an offer for another brand, model code, model word (Pro, Max, Mini…) or
  pack size, whatever the model says. Renewed, used and out-of-stock wording counts only around the
  offer's quoted price. "Add to cart", "Ships within…" and "Pickup today" count as stock wording.
- **Samples.** The made-up sample screenshots replay their recorded result in live mode, labelled
  as demo prices, with no live calls.

Checked live on 29–30 Oct:
- Generic headphones: non-matching products were correctly rejected.
- Sony WH-1000XM5: sony.com's $228.00 sale price was found. The real page text is now a regression
  test.
- listenup.com shows In Stock, Back Order and Out of Stock side by side for different variants, so
  it is correctly left out.
