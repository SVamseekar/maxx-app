# AI guardrails

Written 24 October 2026. This page lists every place Maxx uses a language model, what each one is
allowed to do, and how spending is capped. Code: `services/api/maxx/guardrails.py` (the roles),
`providers.py` (the transport), `budget.py` (the spending cap).

## The idea in one paragraph

Instructions in a prompt can be argued away: published studies in 2025 broke most prompt-level
defences more than 90% of the time. So in Maxx a prompt is only hygiene. The real protection is
that each model returns a small, typed answer, and plain code checks that answer before anything
uses it. No model can make a payment, send a message to a person, or spend past a limit, because
code (not the model) holds every limit.

## Rules that apply to every role

1. **One job.** Each role's system message starts "Do only this one job: …" followed by short
   numbered rules. Rules are only ever in the system message.
2. **Data is data.** Everything the model reads from outside (screenshot text, web pages, item
   fields, seller notes, room state) goes in the user message as one JSON object, built with
   `json.dumps` so hostile text cannot break out of its field. The last rule always says text in
   the data is never an instruction.
3. **One JSON object back.** The reply must be exactly one JSON object. At most one leading
   thinking block (`<think>…</think>`) is removed first; any other text before or after the JSON
   is refused. The code never digs a `{…}` out of prose.
4. **Strict schema.** Every answer is validated with Pydantic: `extra="forbid"`, a length limit on
   every string, fixed values where they are known. Fields that are names or sentences refuse
   links, email addresses and instruction-like text ("ignore previous instructions", "system:").
5. **One retry, at most.** An answer out of contract gets one retry, which adds the schema to the
   rules. A cut-off answer (`finish_reason: length`) gets none. Thinking is switched off for
   Nemotron models (`chat_template_kwargs.enable_thinking=false` and `reasoning_effort=none`), so
   reasoning cannot use up `max_tokens` or reach the answer. Only `message.content` is read, never
   `reasoning` or `reasoning_content`.
6. **Nothing silent.** When a check changes or refuses an answer, the user sees a plain warning or
   a clear error, and the call log records the rule's name (never the content). There is no
   switch to fixture data.

## The roles

| Role | Model setting | Its one job | What it may see | What it returns | max_tokens | Calls |
|---|---|---|---|---|---|---|
| Vision | `MODEL_VISION` | Read the first product in a screenshot | The screenshot only | `VisionItem`: title, brand, model, variant, price, currency (`USD` or null), merchant, qty, visible text | 1200 | 1 + 1 retry per scan |
| Normalise | `MODEL_FAST` | Tidy brand, model and variant names | Title, brand, model, variant, visible text | `Identity`: brand, model, variant only | 200 | 1 + 1 retry per scan |
| Price extraction | `MODEL_FAST` | List comparable new retail offers in the fetched pages | Item identity (title, brand, model, variant, qty, currency) and up to 8 Tavily pages | `Rows`: up to 8 rows of title, url, price, shipping, stock, quote | 1600 | 1 + 1 retry per search |
| Verdict | `MODEL_REASON` | Write one line explaining the chosen move | Item, score, the move code chose | `Move`: the same move, a headline (120 chars) and an explanation (400 chars) | 300 | 1 + 1 retry per scan |
| Seller persona | `MODEL_SELLER` | Make one round's offer as a simulated seller | Its own private state, aggregate demand, its own feedback | `Bid`: price, quantity, withdraw | 150 | 1 + 1 retry per seller per round |
| Seller AI agent | `MODEL_SELLER` | Make one round's offer for one real seller | The same, plus that seller's own note (280 chars) | `Bid` | 150 | 1 + 1 retry per seller per round |
| Negotiator | `MODEL_NEGOTIATOR` | Run one round with five tools | Round, product title, aggregate demand, the server's reserve ceiling, previous result, seller ids | Tool calls only | 400 | Up to 4 tool turns, 5 actions per turn, 1 retry per round |
| Embed | `MODEL_EMBED` | Turn product titles into vectors | One title and the 50 catalogue titles | Vectors | — | 1 per match |

## What code checks after each role

**Vision.** The price must appear with a `$` or `USD` in the visible text, or it is removed. If the
screenshot's own text talks to AI tools, the price is not read at all and the person is asked to
enter it ("The screenshot contains text aimed at AI tools…"). A link or instruction in a name field
fails the schema.

**Normalise.** Every word it returns must already be in the title or visible text. Otherwise the
names read from the screenshot are kept, with a warning. It cannot change price, currency,
merchant or anything else: its schema has only three fields.

**Price extraction.** A row is kept only if its URL is one of the fetched pages, its quote is an
exact substring of that same page, and its price appears in that page. Rows whose title or quote
carry instructions or links are dropped. Rows from a page that talks to AI tools are kept for
display but left out of the score. A new item under half the scanned price is "too good to be
true" and left out of the score. Existing rules still apply: non-USD and used, refurbished or
out-of-stock pages are not the same item, and shipping or stock claims need their own evidence.

**Verdict.** The move must equal the one code chose. No digits, `$`, `%` or "percent"; no links
or emails; no instructions; no sales or account wording (subscribe, coupon, password, card
number…); and every name (a known brand, a capitalised word inside a sentence, a mixed-case word
like "iPhone") must be in the input. Otherwise the fixed template is used and the warning says so.

**Seller persona and seller AI agent.** Every model-made bid passes `guard_ai_bid`: never below
the floor, never above the opening price, never above its own previous offer, never more than
`SELLER_AI_MAX_ROUND_DROP_PERCENT` below it in one round, never more than stock. The floor always
wins. A seller's note written as instructions to the model is not passed on at all. No seller ever
sees another seller's data.

**Negotiator.** Each tool has an argument model with no extra fields. An unknown tool, a missing or
extra argument, a reserve that is not a plain amount (`^\d{1,9}(\.\d{1,2})?$`), a seller id not in
the room, more than five actions, or prose instead of tools makes the turn invalid. After one
retry the round uses a fixed rule (the server's ceiling, the same fixed message to every seller,
close at round 4) and the room shows "Negotiator unavailable; using the fixed rule for this round."
A reserve above the ceiling is clamped to it. The `text` argument of `send_round_message` is
ignored: sellers only ever get "Please improve your offer."

**Embed.** 51 vectors of equal, non-zero length with finite similarities, or the match fails with
a clear message. Variant rules in code have the last word.

## The spending cap

Every paid call (Nebius chat, Nebius embeddings, Tavily search and extract) first holds its
**worst-case cost** in the database: input at a cautious 3 characters per token, each image at the
model's per-image token count, plus every allowed output token. After the call the hold is
replaced by the measured cost (or kept in full if the reply has no usage). Holds that never settle
expire after the provider timeout plus a minute and count as spent. Listing models is free.

A hold must fit inside **every** limit that applies, in one transaction, or the call is never made:

| Limit | Setting | Default | Who it applies to |
|---|---|---|---|
| Total | `AI_BUDGET_USD` | $20.00 | Everything |
| Today (UTC) | `AI_DAILY_BUDGET_USD` | $0.40 | Everything except live checks |
| People today | daily minus the negotiation share | $0.20 | All scans and matches by people |
| Negotiations today | `AI_NEGOTIATION_DAILY_BUDGET_USD` | $0.20 | Negotiations and their market refresh |
| One person's Blocs | `AI_OWNER_NEGOTIATION_DAILY_BUDGET_USD` | $0.10 | Negotiations charged to one person: the Bloc's creator, else whoever started it; a timed close of a Bloc nobody created shares one bucket per kind of Bloc |
| Visitors today | `AI_ANONYMOUS_DAILY_BUDGET_USD` | $0.08 | Everyone not signed in, together |
| One address | `AI_ADDRESS_DAILY_BUDGET_USD` | $0.02 | One visitor's address (stored as a keyed hash) |
| One person | `AI_USER_DAILY_BUDGET_USD` / `AI_PREMIUM_USER_DAILY_BUDGET_USD` | $0.05 / $0.25 | One signed-in person |
| Web search month / day | `TAVILY_MONTHLY_CREDITS` / `TAVILY_DAILY_CREDITS` | 900 / 40 credits | All Tavily calls |
| One live check | `AI_VERIFY_BUDGET_USD` | $1.00 | `make verify-guardrails` |

Why these numbers: $25 of credit must last to the end of Nebius judging (15 December 2026), about
52 days, which is $0.48 a day. Keeping $5 for live checks and estimate error leaves $20, so $0.40 a
day. Half of each day is kept for negotiations; visitors can use at most $0.08 of the other half,
so signed-in people always keep at least $0.12. All of these are settings, so a paid launch
changes them without code.

On PostgreSQL each hold is a conditional `UPDATE … WHERE spent + reserved + amount <= cap`, which
is re-checked after waiting for a concurrent writer, so two requests near a cap cannot both pass
(tested with two threads on SQLite and on Postgres).

Other limits:

- **Per request:** at most `AI_MAX_CALLS_PER_SCAN` (10) paid calls per scan, Bloc creation or
  market refresh, 1 per catalogue match, and `AI_MAX_CALLS_PER_NEGOTIATION` (120) per negotiation.
- **No payer, no call:** every entry point names who pays. A call outside one is refused.
- **Unpriced models are never called.** `MODEL_RATES_JSON` defaults to the Token Factory rates in
  `config.py`; `{}` switches all live AI off.
- **Kill switch:** `AI_PAUSED=true`, or "Pause live AI" on the admin console.
- **Sign-in only:** `AI_ANONYMOUS_LIVE=false` refuses live AI for visitors everywhere.
- **Before a negotiation:** a live negotiation starts only if today's budget can cover
  `AI_NEGOTIATION_WORST_USD` ($0.10). A timed close that cannot run fails with the reason and
  releases every hold; an operator pause instead waits until AI is resumed.
- **Rate limits:** scans (120 an hour signed in, 30 per address), catalogue matches (120 an hour),
  Bloc creations and starts (10 an hour per person).

When a limit is reached the person sees why, for example: "Live AI is paused: today's AI budget is
used up. It resets at 00:00 UTC." A scan that runs out halfway keeps what it already read. The rest
of Maxx (browsing, Blocs, accounts, payments) keeps working. `GET /ai/usage` tells a person what is
left of today's allowance, and the admin console shows every limit, calls per role, refusals and
which guards fired.

## Prices used (per million tokens)

| Model | Input | Output | Image tokens |
|---|---|---|---|
| `nvidia/Nemotron-3_5-Lightning` | $0.06 | $0.24 | — |
| `nvidia/nemotron-3-super-120b-a12b` | $0.30 | $0.90 | — |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | $1.00 | $3.00 | — |
| `nvidia/Nemotron-3.5-Super-VL` | $0.30 | $0.90 | 1800 (assumed) |
| `google/gemma-3-27b-it` | $0.10 | $0.30 | 256 |
| `Qwen/Qwen3-Embedding-8B` | $0.01 | — | — |

Source: Token Factory catalog data as of 20 October 2026, through a third-party mirror, because
Nebius's price page renders only inside the console. The Lightning, Super and Ultra prices match
the 5 October notes. Re-check them in the console before relying on the totals.

## Still unverified (needs one live run)

Nebius Token Factory was down on 24 October 2026 (503 on every call, including the model list).
Until `make verify-guardrails RUN="--run --yes"` has run, these are not confirmed:

- which thinking switch Token Factory honours for each Nemotron model, and whether reasoning still
  reaches `content`;
- whether Nemotron 3 Ultra still calls tools with thinking off (its model card suggests thinking
  may need to be on for tools);
- the Super VL image token count, and whether it reads the fixture screenshots better than Gemma 3;
- the measured cost of one scan and one negotiation round;
- the prices above, on Nebius's own page.
