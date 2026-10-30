# Maxx

**Buy together. Pay less.** Screenshot what you're about to buy and Maxx tells you the smartest
move. When many people want the same product, they join a **Bloc**: each sets a private maximum,
and AI agents bargain with sellers for all of them at once. Everyone pays the price they were
allocated, never more than their maximum, and nothing if no deal closes.

**Live demo:** https://maxx.souravamseekar.com · **Judges:** start at
[`/judge`](https://maxx.souravamseekar.com/judge) · MIT licensed

Built for the Nebius × NVIDIA Global AI Hackathon (Best Apps & Agents, Best Use of Tavily). Every
model runs on **Nebius Token Factory**, and every reasoning step uses an **NVIDIA Nemotron** model.

## Try it (judges)

1. Open [`/judge`](https://maxx.souravamseekar.com/judge) first. The free API sleeps when idle;
   the first visit takes about a minute while a banner shows it waking.
2. Enter the judge access code from the submission notes. You get your own guest account at once:
   no email, no password.
3. **Try successful deal** opens your private copy of a Bloc with 600 simulated buyers and eight
   seller agents. Set your maximum and **Join with a PayPal hold** (simulated).
4. **Close Bloc & negotiate** and watch the rounds stream in: Nemotron 3 Ultra negotiates for the
   group, Nemotron 3 Super runs each seller agent, and a deterministic engine sets every price.
5. **Start the seller tour** for the seller side: your own seller agent, orders, shipping with a
   test tracking number, payout on delivery.
6. **Scan**: the **Live example** runs the full live pipeline (vision, Tavily, verdict); you can
   also upload a screenshot of your own cart or product page.
7. **Under the hood** lists every model call with its model id, latency and cost.

Simulated buyers, sellers and PayPal are labelled everywhere. They place no real holds and nobody
is charged for them.

## How Maxx uses Nebius and Nemotron

| Job | Model (Nebius Token Factory) |
|---|---|
| Read a cart or product screenshot | `nvidia/Nemotron-3.5-Super-VL` |
| Normalise the product; pull prices out of web pages | `nvidia/Nemotron-3_5-Lightning` |
| Write the verdict; run each seller's agent | `nvidia/nemotron-3-super-120b-a12b` |
| Negotiate for the group, with tool calls | `nvidia/Nemotron-3-Ultra-550b-a55b` |
| Match a screenshot to an existing Bloc | `Qwen/Qwen3-Embedding-8B` |

- **Models never set money.** The negotiator chooses a reserve price and which seller to press;
  seller agents bid within floors and stock enforced in code; a deterministic clearing engine
  allocates units and sets every price.
- **Strict contracts.** Each role has a JSON schema sent with every call (in the prompt and as
  `response_format`), post-checks in code, and a bounded set of tools.
- **Spending caps.** A Postgres ledger caps AI spend in total, per day, per person, per address and
  per negotiation. If a cap is hit or Token Factory is down, the negotiation runs a labelled replay
  instead of failing.
- **Transparency.** Every call is logged with model id, tokens, latency and cost (no prompts,
  images or keys) and shown on Under the hood.

Details: [AI guardrails](docs/ai-guardrails.md).

## How Maxx uses Tavily

A live scan searches Tavily once with full page text (1 credit), preferring US retailers and
makers' own stores and excluding news, review, video and deal sites. Only stores whose pages can be
read can confirm stock and shipping, so when fewer than two stores confirm an offer, a second search
asks only those stores. At most two pages are read in full with Extract.

Code, not the model, decides which offers count: product pages only, a price quoted from the page,
the same brand, model, colour and pack size, new rather than refurbished or open box, no
card-signup or coupon prices, not on backorder. A Money Score needs two such stores, or the maker's
own store with a warning; otherwise the verdict names the lowest price it saw and says the evidence
is thin. A scan costs 1–4 credits, results are cached for six hours, and daily and monthly credit
caps stop runaway spend.

## What's in it

- **Scan → verdict:** screenshot upload, editable fields, Money Score (0–100), one recommended move,
  and links to the offers found.
- **Blocs and negotiation:** commitments with a maximum price, a countdown, live streamed rounds,
  partial fills, and a clear outcome for every member.
- **Payments** (`PAYPAL_MODE=simulator` or `sandbox`): a PayPal hold on joining, capture of only
  the allocated price, release for everyone else, seller payouts, agentic checkout and PYUSD.
  See [payments](docs/payments.md).
- **Marketplace:** seller onboarding with identity and sanctions checks, standing offers and
  listings, a bounded seller AI agent, orders, carrier tracking, payout on delivery, refunds and
  cases. Maxx is the platform, not the seller. See [marketplace](docs/marketplace.md).
- **Accounts:** emailed link, Google, Apple, Microsoft or GitHub; passkeys or an authenticator app;
  security alerts. See [accounts](docs/accounts.md) and [security](docs/security.md).

## Architecture

```text
apps/web/        Next.js 16: pages, and a server-side proxy to the API (streams included)
services/api/    FastAPI: scan, price search, Blocs, auction engine, agents, money, marketplace
evals/           fixture and live evaluation scripts and their results
deploy/          Dockerfiles and a production-like Compose file
render.yaml      the hosted API's settings
```

Postgres holds everything durable through one `DATABASE_URL`: Blocs, jobs, an append-only event
journal, a hash-chained money ledger, the price cache and model-call metadata. Screenshots are
processed in memory and never stored.

Stack: Next.js 16.3, React 19.3, TypeScript 5.9, Tailwind 4.3; Python 3.12, FastAPI 0.142,
Pydantic 2.13, SQLAlchemy 2.0, Alembic; Postgres 17.

## Run it locally

Needs Node.js 22+, Python 3.12, [uv](https://docs.astral.sh/uv/), and Docker (or a native
Postgres 15+).

```bash
cp .env.example .env     # first time only; add NEBIUS_API_KEY and TAVILY_API_KEY for live mode
make setup               # npm ci + uv sync --locked
make db                  # Postgres on 127.0.0.1:55432 (or: make db-native)
make migrate
make api                 # terminal 1: http://localhost:8000
make web                 # terminal 2: http://localhost:3001
```

Live mode is the default. With no keys, run fully offline on the five synthetic samples:

```bash
SCAN_MODE=fixture MATCH_MODE=fixture NEGOTIATION_MODE=fixture make api
```

Set `JUDGE_ACCESS_CODE` (12+ characters) in `.env` to turn on the judge entry at `/judge`. Every
other setting, with its default, is in `.env.example`.

Checks:

```bash
make check               # web lint, typecheck, tests and build; API lint, format and tests
make smoke               # HTTP checks through web → API → database
make verify-guardrails   # live: each model's contract against Token Factory (spends a few cents)
make evaluate            # fixture evaluation, writes evals/core-fixture.json
```

## Hosting

The demo runs on free plans: the web app on Vercel, the API on Render, Postgres on Neon, email
through Brevo. See [deployment](docs/deployment.md).

## Docs

- [Verification](docs/verification.md): what was measured, live and offline, and what was not
- [AI guardrails](docs/ai-guardrails.md) · [Payments](docs/payments.md) ·
  [Marketplace](docs/marketplace.md) · [Accounts](docs/accounts.md) ·
  [Security](docs/security.md) · [Performance](docs/performance.md) ·
  [Market and compliance research](docs/market-research.md) · [Deployment](docs/deployment.md)

## Disclosure

New project, started 5 October 2026. In the demo scenarios the eight seller agents and the crowds
of buyers (600 in the successful deal, 100 in each of the others) are simulated and labelled; they
place no holds and nobody is charged for them. PayPal, carrier tracking and identity checks run in
labelled simulators unless real keys are set. The 15 policy pages under `/legal` are drafts.

## License

MIT. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).
