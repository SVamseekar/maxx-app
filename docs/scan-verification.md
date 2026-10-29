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

`maxx/price_search.py` decides how a scan finds comparable offers and which ones it trusts. It
follows Tavily's search and extract guidance, standard product-matching rules, and live tests on
real products.

**Retrieval (Tavily).**

1. **First search, biased toward shops.** One basic search with:
   - full page text included (`include_raw_content`, still 1 credit by Tavily's usage counter);
   - US retailers and brand stores preferred (`include_domains_mode: "prefer"`);
   - news, finance, review, video, social and deal sites excluded.

   For a Ninja AF101 this went from 2 results to 10.
2. **Second search, when needed.** The score needs two stores that confirm price, stock and
   shipping, and only stores whose pages can be read can confirm anything. So when fewer than two
   stores could confirm an offer, a second search asks only readable stores
   (`include_domains_mode: "restrict"`). For a Sony WH-1000XM5 it added Crutchfield.
3. **Reading pages in full.** At most 2 pages are read with a focused extract query, and only when
   the search gave neither their full text nor their stock and shipping. Amazon, Walmart, Target,
   Best Buy and Home Depot are never read in full: their reads came back empty or blocked.

**What was tried and dropped.**
- Quoting the model code with `exact_match` returned no results for the Sony.
- Freshly fetched pages (`max_age_hours`) cut one search to four unpriced results.

**Evidence.** For each page the model sees the title, the snippet, the passages around prices
(those naming the product first), and one passage each for stock and for shipping. Image and link
markup is stripped.

**Trust, decided in code.**
- An offer must come from a product page. Search and category pages are dropped, and so are
  "Access Denied" pages.
- Its price must be quoted from the page.
- These make it a different item: another brand, model code, model word, pack size or colour.
- These mark it as not new: Renewed, Open Box, Scratch & Dent or bids, written just before its
  price.
- These make the price conditional, so it is not a plain retail price: "after $25 off … upon
  opening a new card", coupons, trade-ins, member prices, monthly prices.
- "On backorder", "Notify me" or "Pre-order" near the price means not in stock.
- Free shipping is set from the page's own wording, and only when it covers the price and does
  not depend on a membership.
- A score needs two stores that confirm, or the maker's own store from a fixed list. When the
  maker's store is the only one, a warning says so.

**Verdicts.**
- With no score, a lower price is still named: "Seen for less elsewhere …".
- The verdict model is told what its move means for the shopper.

**Samples and live example.**
- The made-up sample screenshots replay their recorded result, labelled as demo prices.
- A live example (a Sony WH-1000XM5 cart) runs the full live pipeline.

**Checked live on 29–30 Oct 2026.**

| Product | Result |
|---|---|
| Sony WH-1000XM5 | sony.com $228.00 delivered and in stock, so a Money Score of 30 against the $399.99 cart. Crutchfield's $298 was correctly left unscored: on backorder. Abt's offer was the Silver model, so it was rejected. |
| Ninja AF101 | Home Depot's price needed a new store card, so it was rejected. SharkNinja's own store showed $129.99 with free shipping. |
| Generic headphones | Non-matching products were rejected. |
